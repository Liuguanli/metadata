from pathlib import Path
import sqlite3

from metamirror.cli import main


def test_init_creates_scaffolding(tmp_path: Path) -> None:
    exit_code = main(["init", str(tmp_path)])
    assert exit_code == 0

    metamirror_dir = tmp_path / ".metamirror"
    assert metamirror_dir.exists() and metamirror_dir.is_dir()
    assert (metamirror_dir / "metadata.db").exists()
    assert (metamirror_dir / "audit.jsonl").exists()
    assert (metamirror_dir / "derived").exists()
    assert (metamirror_dir / "trash").exists()


def _db_path(workspace: Path) -> Path:
    return workspace / ".metamirror" / "metadata.db"


def test_scan_inserts_files_into_db(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "note.txt").write_text("hello world", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    conn = sqlite3.connect(_db_path(tmp_path))
    try:
        row = conn.execute(
            "SELECT path, filename, status, metadata_status, sha256 FROM files WHERE path = 'docs/note.txt'"
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    path, filename, status, metadata_status, sha256_value = row
    assert path == "docs/note.txt"
    assert filename == "note.txt"
    assert status == "active"
    assert metadata_status == "basic_only"
    assert sha256_value is not None and len(sha256_value) == 64


def test_scan_updates_existing_file_record(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs" / "note.txt"
    target.write_text("v1", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    conn = sqlite3.connect(_db_path(tmp_path))
    try:
        before = conn.execute(
            "SELECT file_id, size_bytes, sha256, modified_at FROM files WHERE path = 'docs/note.txt'"
        ).fetchone()
    finally:
        conn.close()
    assert before is not None

    target.write_text("v1 plus more", encoding="utf-8")
    assert main(["scan", str(tmp_path)]) == 0

    conn = sqlite3.connect(_db_path(tmp_path))
    try:
        after = conn.execute(
            "SELECT file_id, size_bytes, sha256, modified_at FROM files WHERE path = 'docs/note.txt'"
        ).fetchone()
    finally:
        conn.close()
    assert after is not None

    assert before[0] == after[0]
    assert before[1] != after[1]
    assert before[2] != after[2]
    assert before[3] != after[3]


def test_scan_excludes_reserved_paths(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "keep.txt").write_text("ok", encoding="utf-8")

    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("skip", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("skip", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "cfg.py").write_text("skip", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.pyc").write_text("skip", encoding="utf-8")
    (tmp_path / ".DS_Store").write_text("skip", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    conn = sqlite3.connect(_db_path(tmp_path))
    try:
        paths = [r[0] for r in conn.execute("SELECT path FROM files ORDER BY path").fetchall()]
    finally:
        conn.close()

    assert "docs/keep.txt" in paths
    assert all(not p.startswith(".git/") for p in paths)
    assert all(not p.startswith("node_modules/") for p in paths)
    assert all(not p.startswith(".venv/") for p in paths)
    assert all(not p.startswith("__pycache__/") for p in paths)
    assert ".DS_Store" not in paths
