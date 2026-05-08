from __future__ import annotations

import mimetypes
import os
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid5, NAMESPACE_URL
from uuid import uuid4

from metamirror.db import connect_db
from metamirror.extractor import EXTRACTOR_VERSION, extract_summary_preview


EXCLUDED_DIR_NAMES = {
    ".git",
    ".metamirror",
    "node_modules",
    ".venv",
    "__pycache__",
}
EXCLUDED_FILE_NAMES = {".DS_Store"}
HASH_SIZE_LIMIT_BYTES = 100 * 1024 * 1024


@dataclass
class ScanResult:
    scanned_files: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_id_for_path(path: Path) -> str:
    return str(uuid5(NAMESPACE_URL, str(path.resolve())))


def _event_id() -> str:
    return str(uuid4())


def _iter_workspace_files(workspace: Path) -> Iterable[Path]:
    for root, dirs, files in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]
        for name in files:
            if name in EXCLUDED_FILE_NAMES:
                continue
            yield Path(root) / name


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def scan_workspace(workspace: str | Path) -> ScanResult:
    ws_path = Path(workspace).resolve()
    now = _utc_now()
    scanned = 0

    seen_paths: set[str] = set()

    with connect_db(ws_path) as conn:
        for file_path in _iter_workspace_files(ws_path):
            if not file_path.is_file():
                continue

            stat = file_path.stat()
            rel_path = str(file_path.relative_to(ws_path))
            seen_paths.add(rel_path)
            mime_type, _ = mimetypes.guess_type(file_path.name)
            extension = file_path.suffix.lower() if file_path.suffix else None
            existing = conn.execute(
                "SELECT file_id, modified_at, size_bytes FROM files WHERE path = ?",
                (rel_path,),
            ).fetchone()

            if existing:
                file_id = existing[0]
            else:
                file_id = _file_id_for_path(file_path)

            if stat.st_size > HASH_SIZE_LIMIT_BYTES:
                sha256_value = None
                metadata_status = "basic_only"
            else:
                sha256_value = _sha256_file(file_path)
                metadata_status = "basic_only"

            conn.execute(
                """
                INSERT INTO files (
                    file_id, path, filename, extension, mime_type, size_bytes,
                    sha256, created_at, modified_at, last_seen_at,
                    status, dirty, metadata_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, ?)
                ON CONFLICT(path) DO UPDATE SET
                    filename = excluded.filename,
                    extension = excluded.extension,
                    mime_type = excluded.mime_type,
                    size_bytes = excluded.size_bytes,
                    sha256 = excluded.sha256,
                    modified_at = excluded.modified_at,
                    last_seen_at = excluded.last_seen_at,
                    metadata_status = excluded.metadata_status,
                    status = 'active'
                """,
                (
                    file_id,
                    rel_path,
                    file_path.name,
                    extension,
                    mime_type,
                    stat.st_size,
                    sha256_value,
                    datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
                    datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    now,
                    metadata_status,
                ),
            )
            conn.execute(
                """
                INSERT INTO file_policy (file_id)
                VALUES (?)
                ON CONFLICT(file_id) DO NOTHING
                """,
                (file_id,),
            )

            summary_preview = extract_summary_preview(file_path)
            if summary_preview:
                conn.execute(
                    """
                    INSERT INTO file_metadata (
                        file_id, summary, summary_generated_at, extractor_version
                    )
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(file_id) DO UPDATE SET
                        summary = excluded.summary,
                        summary_generated_at = excluded.summary_generated_at,
                        extractor_version = excluded.extractor_version
                    """,
                    (file_id, summary_preview, now, EXTRACTOR_VERSION),
                )

            modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO file_events (
                        event_id, file_id, event_type, old_path, new_path,
                        actor, reason, evidence, created_at
                    )
                    VALUES (?, ?, 'created', NULL, ?, 'system', 'scan_discovery', NULL, ?)
                    """,
                    (_event_id(), file_id, rel_path, now),
                )
            else:
                was_modified_at = existing[1]
                was_size = existing[2]
                if was_modified_at != modified_at or was_size != stat.st_size:
                    conn.execute(
                        """
                        INSERT INTO file_events (
                            event_id, file_id, event_type, old_path, new_path,
                            actor, reason, evidence, created_at
                        )
                        VALUES (?, ?, 'modified', ?, ?, 'system', 'scan_change', NULL, ?)
                        """,
                        (_event_id(), file_id, rel_path, rel_path, now),
                    )
            scanned += 1

        missing_rows = conn.execute(
            """
            SELECT file_id, path
            FROM files
            WHERE status = 'active'
            """
        ).fetchall()
        for file_id, rel_path in missing_rows:
            if rel_path in seen_paths:
                continue
            conn.execute(
                """
                UPDATE files
                SET status = 'missing', last_seen_at = ?
                WHERE file_id = ?
                """,
                (now, file_id),
            )
            conn.execute(
                """
                INSERT INTO file_events (
                    event_id, file_id, event_type, old_path, new_path,
                    actor, reason, evidence, created_at
                )
                VALUES (?, ?, 'missing', ?, NULL, 'system', 'scan_missing', NULL, ?)
                """,
                (_event_id(), file_id, rel_path, now),
            )

        conn.commit()

    return ScanResult(scanned_files=scanned)
