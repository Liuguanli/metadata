from pathlib import Path
import sqlite3

from metamirror.cli import main


def test_deleted_local_file_is_marked_missing_not_removed(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs" / "gone.txt"
    target.write_text("keep history", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    target.unlink()
    assert main(["scan", str(tmp_path)]) == 0

    db_path = tmp_path / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT file_id, path, status FROM files WHERE path = 'docs/gone.txt'"
        ).fetchone()
        missing_events = conn.execute(
            "SELECT COUNT(*) FROM file_events WHERE event_type = 'missing'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert row is not None
    assert row[1] == "docs/gone.txt"
    assert row[2] == "missing"
    assert missing_events >= 1
