from pathlib import Path

from metamirror.db import connect_db, init_db


def test_connect_db_enables_wal_and_foreign_keys(tmp_path: Path) -> None:
    init_db(tmp_path)
    with connect_db(tmp_path) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]

    assert journal_mode.lower() == "wal"
    assert foreign_keys == 1


def test_init_db_creates_indexes(tmp_path: Path) -> None:
    init_db(tmp_path)
    with connect_db(tmp_path) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            ).fetchall()
        }

    assert "idx_events_created_at" in names
    assert "idx_events_file_id" in names
    assert "idx_proposals_status" in names
