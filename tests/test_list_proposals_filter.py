from __future__ import annotations

import sqlite3
from pathlib import Path

from metamirror.cli import main
from metamirror.db import list_proposals


def _file_id(workspace: Path, rel: str) -> str:
    conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
    try:
        row = conn.execute("SELECT file_id FROM files WHERE path = ?", (rel,)).fetchone()
    finally:
        conn.close()
    assert row is not None
    return row[0]


def test_list_proposals_with_and_without_filter(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    fid_a = _file_id(tmp_path, "a.txt")
    fid_b = _file_id(tmp_path, "b.txt")

    assert main(["propose-delete", str(tmp_path), fid_a, "--reason", "r", "--evidence", "e"]) == 0
    assert main(["propose-delete", str(tmp_path), fid_b, "--reason", "r", "--evidence", "e"]) == 0

    pending_id_a = next(p["proposal_id"] for p in list_proposals(tmp_path) if p["file_id"] == fid_a)
    assert main(["approve", str(tmp_path), pending_id_a]) == 0

    all_props = list_proposals(tmp_path)
    pending = list_proposals(tmp_path, status="pending")
    approved = list_proposals(tmp_path, status="approved")

    assert len(all_props) == 2
    assert len(pending) == 1 and pending[0]["file_id"] == fid_b
    assert len(approved) == 1 and approved[0]["file_id"] == fid_a
