from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
from uuid import uuid4

from metamirror.db import connect_db, metamirror_dir


@dataclass
class DeleteProposalResult:
    proposal_id: str
    file_id: str
    path: str
    status: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_delete_proposal(
    workspace: str | Path,
    file_id: str,
    reason: str,
    evidence: str,
) -> DeleteProposalResult:
    ws_path = Path(workspace).resolve()
    proposal_id = str(uuid4())
    event_id = str(uuid4())
    now = _utc_now()

    with connect_db(ws_path) as conn:
        row = conn.execute(
            "SELECT path FROM files WHERE file_id = ?",
            (file_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"file_id not found: {file_id}")
        file_path = row[0]

        conn.execute(
            """
            INSERT INTO action_proposals (
                proposal_id, action_type, file_id, proposed_target,
                reason, evidence, status, created_by, created_at,
                approved_at, executed_at
            )
            VALUES (?, 'delete', ?, NULL, ?, ?, 'pending', 'ai', ?, NULL, NULL)
            """,
            (proposal_id, file_id, reason, evidence, now),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'ai_proposed_delete', ?, NULL, 'ai', ?, ?, ?)
            """,
            (event_id, file_id, file_path, reason, evidence, now),
        )
        conn.commit()

    return DeleteProposalResult(
        proposal_id=proposal_id,
        file_id=file_id,
        path=file_path,
        status="pending",
    )


@dataclass
class ApproveProposalResult:
    proposal_id: str
    file_id: str
    old_path: str
    new_path: str
    proposal_status: str
    file_status: str


def _build_trash_target(workspace: Path, filename: str) -> Path:
    date_str = datetime.now(timezone.utc).date().isoformat()
    trash_dir = metamirror_dir(workspace) / "trash" / date_str
    trash_dir.mkdir(parents=True, exist_ok=True)

    candidate = trash_dir / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = trash_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _ensure_relpath_within_workspace(workspace: Path, rel_path: str) -> Path:
    candidate = (workspace / rel_path).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {rel_path}") from exc
    return candidate


def _avoid_overwrite_target(target: Path) -> Path:
    if not target.exists():
        return target
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem}_restored_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def approve_delete_proposal(
    workspace: str | Path,
    proposal_id: str,
) -> ApproveProposalResult:
    ws_path = Path(workspace).resolve()
    now = _utc_now()

    with connect_db(ws_path) as conn:
        row = conn.execute(
            """
            SELECT p.proposal_id, p.status, p.action_type, p.file_id, f.path, f.filename
            FROM action_proposals AS p
            JOIN files AS f ON f.file_id = p.file_id
            WHERE p.proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"proposal_id not found: {proposal_id}")

        _, proposal_status, action_type, file_id, rel_path, filename = row
        if action_type != "delete":
            raise ValueError(f"proposal action_type is not delete: {action_type}")
        if proposal_status != "pending":
            raise ValueError(f"proposal is not pending: {proposal_status}")

        old_abs_path = ws_path / rel_path
        if not old_abs_path.exists():
            raise ValueError(f"file no longer exists for proposal: {rel_path}")

        new_abs_path = _build_trash_target(ws_path, filename)
        new_abs_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_abs_path), str(new_abs_path))
        new_rel_path = str(new_abs_path.relative_to(ws_path))

        conn.execute(
            """
            UPDATE files
            SET path = ?, status = 'soft_deleted', last_seen_at = ?
            WHERE file_id = ?
            """,
            (new_rel_path, now, file_id),
        )
        conn.execute(
            """
            UPDATE action_proposals
            SET status = 'approved', proposed_target = ?, approved_at = ?, executed_at = ?
            WHERE proposal_id = ?
            """,
            (rel_path, now, now, proposal_id),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'moved', ?, ?, 'system', 'trash_move', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, new_rel_path, proposal_id, now),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'deleted', ?, ?, 'system', 'soft_delete_to_trash', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, new_rel_path, proposal_id, now),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'soft_deleted', ?, ?, 'system', 'approve_delete', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, new_rel_path, proposal_id, now),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'user_approved_delete', ?, ?, 'user', 'proposal_approved', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, new_rel_path, proposal_id, now),
        )
        conn.commit()

    return ApproveProposalResult(
        proposal_id=proposal_id,
        file_id=file_id,
        old_path=rel_path,
        new_path=new_rel_path,
        proposal_status="approved",
        file_status="soft_deleted",
    )


@dataclass
class RejectProposalResult:
    proposal_id: str
    file_id: str
    old_path: str
    proposal_status: str


@dataclass
class RestoreResult:
    file_id: str
    old_path: str
    new_path: str
    file_status: str


@dataclass
class ExpireProposalResult:
    proposal_id: str
    file_id: str
    old_path: str
    proposal_status: str


def reject_proposal(
    workspace: str | Path,
    proposal_id: str,
) -> RejectProposalResult:
    ws_path = Path(workspace).resolve()
    now = _utc_now()

    with connect_db(ws_path) as conn:
        row = conn.execute(
            """
            SELECT p.proposal_id, p.status, p.action_type, p.file_id, f.path
            FROM action_proposals AS p
            JOIN files AS f ON f.file_id = p.file_id
            WHERE p.proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"proposal_id not found: {proposal_id}")

        _, proposal_status, action_type, file_id, rel_path = row
        if action_type != "delete":
            raise ValueError(f"proposal action_type is not delete: {action_type}")
        if proposal_status != "pending":
            raise ValueError(f"proposal is not pending: {proposal_status}")

        conn.execute(
            """
            UPDATE action_proposals
            SET status = 'rejected'
            WHERE proposal_id = ?
            """,
            (proposal_id,),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'user_rejected_delete', ?, ?, 'user', 'proposal_rejected', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, rel_path, proposal_id, now),
        )
        conn.commit()

    return RejectProposalResult(
        proposal_id=proposal_id,
        file_id=file_id,
        old_path=rel_path,
        proposal_status="rejected",
    )


def restore_soft_deleted_file(
    workspace: str | Path,
    file_id: str,
    restore_path: str | None = None,
) -> RestoreResult:
    ws_path = Path(workspace).resolve()
    mm_root = metamirror_dir(ws_path).resolve()
    now = _utc_now()

    with connect_db(ws_path) as conn:
        row = conn.execute(
            """
            SELECT file_id, path, filename, status
            FROM files
            WHERE file_id = ?
            """,
            (file_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"file_id not found: {file_id}")

        _, rel_path, filename, status = row
        if status != "soft_deleted":
            raise ValueError(f"file is not soft_deleted: {status}")

        source_abs = _ensure_relpath_within_workspace(ws_path, str(rel_path))
        if not source_abs.exists():
            raise ValueError(f"soft-deleted file not found in workspace: {rel_path}")

        target_rel: str
        if restore_path:
            target_rel = restore_path
        else:
            target_row = conn.execute(
                """
                SELECT proposed_target
                FROM action_proposals
                WHERE file_id = ? AND status = 'approved'
                ORDER BY approved_at DESC, created_at DESC
                LIMIT 1
                """,
                (file_id,),
            ).fetchone()
            target_rel = str(target_row[0]) if target_row and target_row[0] else str(filename)

        target_abs = _ensure_relpath_within_workspace(ws_path, target_rel)
        if mm_root in target_abs.parents or target_abs == mm_root:
            raise ValueError("restore target cannot be inside .metamirror")
        target_abs = _avoid_overwrite_target(target_abs)
        target_abs.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(str(source_abs), str(target_abs))
        new_rel_path = str(target_abs.relative_to(ws_path))

        conn.execute(
            """
            UPDATE files
            SET path = ?, status = 'active', last_seen_at = ?
            WHERE file_id = ?
            """,
            (new_rel_path, now, file_id),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'moved', ?, ?, 'system', 'restore_move', NULL, ?)
            """,
            (str(uuid4()), file_id, str(rel_path), new_rel_path, now),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'restored', ?, ?, 'user', 'restore_soft_deleted', NULL, ?)
            """,
            (str(uuid4()), file_id, str(rel_path), new_rel_path, now),
        )
        conn.commit()

    return RestoreResult(
        file_id=file_id,
        old_path=str(rel_path),
        new_path=new_rel_path,
        file_status="active",
    )


def expire_proposal(
    workspace: str | Path,
    proposal_id: str,
) -> ExpireProposalResult:
    ws_path = Path(workspace).resolve()
    now = _utc_now()

    with connect_db(ws_path) as conn:
        row = conn.execute(
            """
            SELECT p.proposal_id, p.status, p.action_type, p.file_id, f.path
            FROM action_proposals AS p
            JOIN files AS f ON f.file_id = p.file_id
            WHERE p.proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"proposal_id not found: {proposal_id}")

        _, proposal_status, action_type, file_id, rel_path = row
        if action_type != "delete":
            raise ValueError(f"proposal action_type is not delete: {action_type}")
        if proposal_status != "pending":
            raise ValueError(f"proposal is not pending: {proposal_status}")

        conn.execute(
            """
            UPDATE action_proposals
            SET status = 'expired', executed_at = ?
            WHERE proposal_id = ?
            """,
            (now, proposal_id),
        )
        conn.execute(
            """
            INSERT INTO file_events (
                event_id, file_id, event_type, old_path, new_path,
                actor, reason, evidence, created_at
            )
            VALUES (?, ?, 'proposal_expired', ?, ?, 'system', 'proposal_expired', ?, ?)
            """,
            (str(uuid4()), file_id, rel_path, rel_path, proposal_id, now),
        )
        conn.commit()

    return ExpireProposalResult(
        proposal_id=proposal_id,
        file_id=file_id,
        old_path=rel_path,
        proposal_status="expired",
    )
