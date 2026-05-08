from pathlib import Path

from metamirror.cli import main
from metamirror.db import find_duplicates


def test_duplicate_files_grouped_by_sha256(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.txt").write_text("same", encoding="utf-8")
    (tmp_path / "data" / "b.txt").write_text("same", encoding="utf-8")
    (tmp_path / "data" / "c.txt").write_text("different", encoding="utf-8")

    assert main(["init", str(tmp_path)]) == 0
    assert main(["scan", str(tmp_path)]) == 0

    groups = find_duplicates(tmp_path)
    assert len(groups) == 1
    group = groups[0]
    assert group["count"] == 2

    paths = [item["path"] for item in group["files"]]
    assert "data/a.txt" in paths
    assert "data/b.txt" in paths
