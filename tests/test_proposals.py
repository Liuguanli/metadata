from pathlib import Path
import sqlite3

from metamirror.cli import main


def _db_path(workspace: Path) -> Path:
    return workspace / ".metamirror" / "metadata.db"


def _fetch_one(db_path: Path, query: str) -> tuple | None:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(query).fetchone()
    finally:
        conn.close()


def test_propose_delete_creates_pending_without_deleting_raw_file(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    target = tmp_path / "data" / "target.txt"
    target.write_text("delete candidate", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    db_path = _db_path(tmp_path)
    file_row = _fetch_one(
        db_path,
        "SELECT file_id FROM files WHERE path = 'data/target.txt'",
    )
    assert file_row is not None
    file_id = file_row[0]

    assert (
        main(
            [
                "propose-delete",
                str(tmp_path),
                file_id,
                "--reason",
                "duplicate",
                "--evidence",
                "manual-check",
            ]
        )
        == 0
    )

    proposal_row = _fetch_one(
        db_path,
        "SELECT status FROM action_proposals WHERE file_id = "
        f"'{file_id}' ORDER BY created_at DESC LIMIT 1",
    )
    event_row = _fetch_one(
        db_path,
        "SELECT event_type FROM file_events WHERE file_id = "
        f"'{file_id}' AND event_type = 'ai_proposed_delete' LIMIT 1",
    )

    assert target.exists()
    assert proposal_row is not None and proposal_row[0] == "pending"
    assert event_row is not None and event_row[0] == "ai_proposed_delete"


def test_approve_proposal_moves_file_to_trash_and_marks_soft_deleted(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    target = tmp_path / "data" / "target.txt"
    target.write_text("delete candidate", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    db_path = _db_path(tmp_path)
    file_row = _fetch_one(
        db_path,
        "SELECT file_id FROM files WHERE path = 'data/target.txt'",
    )
    assert file_row is not None
    file_id = file_row[0]

    assert (
        main(
            [
                "propose-delete",
                str(tmp_path),
                file_id,
                "--reason",
                "duplicate",
                "--evidence",
                "manual-check",
            ]
        )
        == 0
    )

    proposal_row = _fetch_one(
        db_path,
        "SELECT proposal_id FROM action_proposals WHERE file_id = "
        f"'{file_id}' ORDER BY created_at DESC LIMIT 1",
    )
    assert proposal_row is not None
    proposal_id = proposal_row[0]

    assert main(["approve", str(tmp_path), proposal_id]) == 0

    proposal_state = _fetch_one(
        db_path,
        "SELECT status FROM action_proposals WHERE proposal_id = "
        f"'{proposal_id}'",
    )
    file_state = _fetch_one(
        db_path,
        "SELECT path, status FROM files WHERE file_id = "
        f"'{file_id}'",
    )
    events_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) FROM file_events WHERE evidence = "
        f"'{proposal_id}' AND event_type IN ('soft_deleted', 'user_approved_delete')",
    )
    moved_deleted_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) FROM file_events WHERE evidence = "
        f"'{proposal_id}' AND event_type IN ('moved', 'deleted')",
    )

    assert proposal_state is not None and proposal_state[0] == "approved"
    assert file_state is not None
    assert file_state[1] == "soft_deleted"
    assert file_state[0].startswith(".metamirror/trash/")
    assert not target.exists()
    assert (tmp_path / file_state[0]).exists()
    assert events_count is not None and events_count[0] == 2
    assert moved_deleted_count is not None and moved_deleted_count[0] == 2


def test_restore_soft_deleted_file_marks_active_and_emits_restored(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    target = tmp_path / "data" / "target.txt"
    target.write_text("delete candidate", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    db_path = _db_path(tmp_path)
    file_row = _fetch_one(
        db_path,
        "SELECT file_id FROM files WHERE path = 'data/target.txt'",
    )
    assert file_row is not None
    file_id = file_row[0]

    assert (
        main(
            [
                "propose-delete",
                str(tmp_path),
                file_id,
                "--reason",
                "duplicate",
                "--evidence",
                "manual-check",
            ]
        )
        == 0
    )

    proposal_row = _fetch_one(
        db_path,
        "SELECT proposal_id FROM action_proposals WHERE file_id = "
        f"'{file_id}' ORDER BY created_at DESC LIMIT 1",
    )
    assert proposal_row is not None
    proposal_id = proposal_row[0]
    assert main(["approve", str(tmp_path), proposal_id]) == 0
    assert main(["restore", str(tmp_path), file_id]) == 0

    file_state = _fetch_one(
        db_path,
        "SELECT path, status FROM files WHERE file_id = "
        f"'{file_id}'",
    )
    restored_count = _fetch_one(
        db_path,
        "SELECT COUNT(*) FROM file_events WHERE file_id = "
        f"'{file_id}' AND event_type = 'restored'",
    )

    assert file_state is not None
    assert file_state[1] == "active"
    assert not file_state[0].startswith(".metamirror/trash/")
    assert restored_count is not None and restored_count[0] >= 1
    assert (tmp_path / file_state[0]).exists()


def test_expire_pending_proposal_updates_status(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    target = tmp_path / "data" / "target.txt"
    target.write_text("delete candidate", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    db_path = _db_path(tmp_path)
    file_row = _fetch_one(
        db_path,
        "SELECT file_id FROM files WHERE path = 'data/target.txt'",
    )
    assert file_row is not None
    file_id = file_row[0]

    assert (
        main(
            [
                "propose-delete",
                str(tmp_path),
                file_id,
                "--reason",
                "stale decision",
                "--evidence",
                "manual-check",
            ]
        )
        == 0
    )

    proposal_row = _fetch_one(
        db_path,
        "SELECT proposal_id FROM action_proposals WHERE file_id = "
        f"'{file_id}' ORDER BY created_at DESC LIMIT 1",
    )
    assert proposal_row is not None
    proposal_id = proposal_row[0]

    assert main(["expire", str(tmp_path), proposal_id]) == 0
    proposal_state = _fetch_one(
        db_path,
        "SELECT status FROM action_proposals WHERE proposal_id = "
        f"'{proposal_id}'",
    )
    expired_event = _fetch_one(
        db_path,
        "SELECT COUNT(*) FROM file_events WHERE evidence = "
        f"'{proposal_id}' AND event_type = 'proposal_expired'",
    )

    assert proposal_state is not None and proposal_state[0] == "expired"
    assert expired_event is not None and expired_event[0] == 1
