from __future__ import annotations

import sqlite3
from pathlib import Path

from metamirror import db as db_module
from metamirror.cli import main
from metamirror.db import fetch_status_summary


def test_status_summary_reports_active_count(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    summary = fetch_status_summary(tmp_path)
    assert summary["total_files"] == 2
    assert summary["active_files"] == 2
    assert summary["missing_files"] == 0
    assert summary["soft_deleted_files"] == 0
    assert summary["deleted_files"] == 0
    assert summary["last_seen_at"] is not None


def test_status_summary_uses_single_aggregate_query(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    select_count = {"n": 0}
    real_connect = db_module.sqlite3.connect

    def counting_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)

        def trace(stmt: str) -> None:
            if stmt.lstrip().upper().startswith("SELECT") and " FROM FILES" in stmt.upper():
                select_count["n"] += 1

        conn.set_trace_callback(trace)
        return conn

    monkeypatch.setattr(db_module.sqlite3, "connect", counting_connect)
    fetch_status_summary(tmp_path)
    assert select_count["n"] == 1, "fetch_status_summary should issue a single aggregate query"
