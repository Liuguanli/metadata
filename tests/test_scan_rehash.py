from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest.mock import patch

from metamirror import scanner
from metamirror.cli import main


def _db_path(workspace: Path) -> Path:
    return workspace / ".metamirror" / "metadata.db"


def _set_mtime(path: Path, ts: float) -> None:
    os.utime(path, (ts, ts))


def test_second_scan_skips_hashing_when_mtime_and_size_unchanged(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs" / "note.txt"
    target.write_text("steady state content", encoding="utf-8")
    _set_mtime(target, 1_700_000_000.0)

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    with patch.object(scanner, "_sha256_file", wraps=scanner._sha256_file) as spy:
        assert main(["scan", str(tmp_path)]) == 0
        assert spy.call_count == 0, "second scan must not rehash unchanged files"


def test_scan_rehashes_when_content_changes(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    target = tmp_path / "docs" / "note.txt"
    target.write_text("v1", encoding="utf-8")
    _set_mtime(target, 1_700_000_000.0)

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    target.write_text("v1 plus more bytes", encoding="utf-8")
    _set_mtime(target, 1_700_000_100.0)

    with patch.object(scanner, "_sha256_file", wraps=scanner._sha256_file) as spy:
        assert main(["scan", str(tmp_path)]) == 0
        assert spy.call_count == 1, "changed file must be rehashed exactly once"


def test_scan_rehashes_first_seen_files_only(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    with patch.object(scanner, "_sha256_file", wraps=scanner._sha256_file) as spy:
        assert main(["scan", str(tmp_path)]) == 0
        assert spy.call_count == 2

    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    with patch.object(scanner, "_sha256_file", wraps=scanner._sha256_file) as spy:
        assert main(["scan", str(tmp_path)]) == 0
        assert spy.call_count == 1, "only the new file should be hashed on incremental scan"

    conn = sqlite3.connect(_db_path(tmp_path))
    try:
        rows = {r[0]: r[1] for r in conn.execute("SELECT path, sha256 FROM files").fetchall()}
    finally:
        conn.close()
    assert all(v is not None and len(v) == 64 for v in rows.values())
