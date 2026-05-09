from __future__ import annotations

from pathlib import Path

from metamirror.cli import main
from metamirror.db import search_files


def _setup_workspace(tmp_path: Path) -> None:
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "report_100pct.txt").write_text("100% complete", encoding="utf-8")
    (tmp_path / "files" / "draft_v2.txt").write_text("draft document", encoding="utf-8")
    (tmp_path / "files" / "snake_case.txt").write_text("uses underscores", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0


def test_percent_in_query_is_treated_literally(tmp_path: Path) -> None:
    _setup_workspace(tmp_path)
    results = search_files(tmp_path, "100%")
    paths = {r["path"] for r in results}
    assert paths == {"files/report_100pct.txt"} or all("100" in p or "100%" in p for p in paths)
    # The unescaped wildcard would also match draft and snake_case (matches any string).
    assert "files/draft_v2.txt" not in paths
    assert "files/snake_case.txt" not in paths


def test_underscore_in_query_is_treated_literally(tmp_path: Path) -> None:
    _setup_workspace(tmp_path)
    results = search_files(tmp_path, "snake_case")
    paths = {r["path"] for r in results}
    assert paths == {"files/snake_case.txt"}


def test_plain_substring_query_still_works(tmp_path: Path) -> None:
    _setup_workspace(tmp_path)
    results = search_files(tmp_path, "draft")
    paths = {r["path"] for r in results}
    assert paths == {"files/draft_v2.txt"}
