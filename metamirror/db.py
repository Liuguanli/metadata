from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


METAMIRROR_DIRNAME = ".metamirror"
DB_FILENAME = "metadata.db"


def metamirror_dir(workspace: str | Path) -> Path:
    return Path(workspace).resolve() / METAMIRROR_DIRNAME


def metadata_db_path(workspace: str | Path) -> Path:
    return metamirror_dir(workspace) / DB_FILENAME


def _schema_statements() -> list[str]:
    return [
        """
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            mime_type TEXT,
            size_bytes INTEGER,
            sha256 TEXT,
            created_at TEXT,
            modified_at TEXT,
            last_seen_at TEXT,
            status TEXT DEFAULT 'active',
            dirty INTEGER DEFAULT 0,
            metadata_status TEXT DEFAULT 'basic_only'
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS file_metadata (
            file_id TEXT PRIMARY KEY,
            title TEXT,
            summary TEXT,
            tags TEXT,
            entities TEXT,
            topics TEXT,
            language TEXT,
            doc_type TEXT,
            summary_generated_at TEXT,
            extractor_version TEXT,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS file_policy (
            file_id TEXT PRIMARY KEY,
            sensitivity TEXT DEFAULT 'normal',
            ai_can_read_metadata INTEGER DEFAULT 1,
            ai_can_read_summary INTEGER DEFAULT 1,
            ai_can_read_full_content INTEGER DEFAULT 0,
            ai_can_create_derived INTEGER DEFAULT 1,
            ai_can_modify_original INTEGER DEFAULT 0,
            ai_can_delete_original INTEGER DEFAULT 0,
            raw_read_requires_approval INTEGER DEFAULT 1,
            delete_requires_approval INTEGER DEFAULT 1,
            retention_policy TEXT DEFAULT 'manual_approval',
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS file_events (
            event_id TEXT PRIMARY KEY,
            file_id TEXT,
            event_type TEXT NOT NULL,
            old_path TEXT,
            new_path TEXT,
            actor TEXT,
            reason TEXT,
            evidence TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS action_proposals (
            proposal_id TEXT PRIMARY KEY,
            action_type TEXT NOT NULL,
            file_id TEXT NOT NULL,
            proposed_target TEXT,
            reason TEXT,
            evidence TEXT,
            status TEXT DEFAULT 'pending',
            created_by TEXT DEFAULT 'ai',
            created_at TEXT,
            approved_at TEXT,
            executed_at TEXT,
            FOREIGN KEY(file_id) REFERENCES files(file_id)
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_events_created_at ON file_events(created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_events_file_id ON file_events(file_id);",
        "CREATE INDEX IF NOT EXISTS idx_proposals_status ON action_proposals(status);",
    ]


def connect_db(workspace: str | Path) -> sqlite3.Connection:
    db_path = metadata_db_path(workspace)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_db(workspace: str | Path) -> Path:
    db_path = metadata_db_path(workspace)
    with connect_db(workspace) as conn:
        for stmt in _schema_statements():
            conn.execute(stmt)
        conn.commit()
    return db_path


def fetch_status_summary(workspace: str | Path) -> dict[str, str | int | None]:
    with connect_db(workspace) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(status = 'active'), 0),
                COALESCE(SUM(status = 'missing'), 0),
                COALESCE(SUM(status = 'soft_deleted'), 0),
                COALESCE(SUM(status = 'deleted'), 0),
                MAX(last_seen_at)
            FROM files
            """
        ).fetchone()

    total_files, active_files, missing_files, soft_deleted_files, deleted_files, last_seen_at = row
    return {
        "total_files": total_files,
        "active_files": active_files,
        "missing_files": missing_files,
        "soft_deleted_files": soft_deleted_files,
        "deleted_files": deleted_files,
        "last_seen_at": last_seen_at,
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_files(workspace: str | Path, query: str, limit: int = 50) -> list[dict[str, str | None]]:
    like_query = f"%{_escape_like(query)}%"
    with connect_db(workspace) as conn:
        rows = conn.execute(
            r"""
            SELECT
                f.file_id,
                f.path,
                f.filename,
                fm.summary,
                fm.tags,
                f.status,
                f.metadata_status,
                COALESCE(fp.sensitivity, 'normal') AS sensitivity
            FROM files AS f
            LEFT JOIN file_metadata AS fm ON fm.file_id = f.file_id
            LEFT JOIN file_policy AS fp ON fp.file_id = f.file_id
            WHERE
                f.filename LIKE ? ESCAPE '\'
                OR f.path LIKE ? ESCAPE '\'
                OR COALESCE(fm.summary, '') LIKE ? ESCAPE '\'
                OR COALESCE(fm.tags, '') LIKE ? ESCAPE '\'
            ORDER BY f.modified_at DESC
            LIMIT ?
            """,
            (like_query, like_query, like_query, like_query, limit),
        ).fetchall()

    keys = [
        "file_id",
        "path",
        "filename",
        "summary",
        "tags",
        "status",
        "metadata_status",
        "sensitivity",
    ]
    return [dict(zip(keys, row)) for row in rows]


def find_duplicates(workspace: str | Path) -> list[dict[str, object]]:
    with connect_db(workspace) as conn:
        groups = conn.execute(
            """
            SELECT sha256, COUNT(*) AS cnt
            FROM files
            WHERE status = 'active'
              AND sha256 IS NOT NULL
            GROUP BY sha256
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC, sha256 ASC
            """
        ).fetchall()

        output: list[dict[str, object]] = []
        for sha256_value, count in groups:
            file_rows = conn.execute(
                """
                SELECT file_id, path, filename
                FROM files
                WHERE status = 'active' AND sha256 = ?
                ORDER BY path ASC
                """,
                (sha256_value,),
            ).fetchall()
            files = [
                {"file_id": r[0], "path": r[1], "filename": r[2]}
                for r in file_rows
            ]
            output.append({"sha256": sha256_value, "count": count, "files": files})

    return output


def fetch_recent_events(
    workspace: str | Path,
    days: int,
    limit: int = 200,
) -> list[dict[str, str | None]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with connect_db(workspace) as conn:
        rows = conn.execute(
            """
            SELECT event_id, file_id, event_type, old_path, new_path, actor, reason, evidence, created_at
            FROM file_events
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (cutoff.isoformat(), limit),
        ).fetchall()

    keys = [
        "event_id",
        "file_id",
        "event_type",
        "old_path",
        "new_path",
        "actor",
        "reason",
        "evidence",
        "created_at",
    ]
    return [dict(zip(keys, row)) for row in rows]


def list_proposals(
    workspace: str | Path,
    status: str | None = None,
    limit: int = 200,
) -> list[dict[str, str | None]]:
    with connect_db(workspace) as conn:
        rows = conn.execute(
            """
            SELECT
                proposal_id, action_type, file_id, proposed_target, reason, evidence,
                status, created_by, created_at, approved_at, executed_at
            FROM action_proposals
            WHERE (? IS NULL OR status = ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status, status, limit),
        ).fetchall()

    keys = [
        "proposal_id",
        "action_type",
        "file_id",
        "proposed_target",
        "reason",
        "evidence",
        "status",
        "created_by",
        "created_at",
        "approved_at",
        "executed_at",
    ]
    return [dict(zip(keys, row)) for row in rows]
