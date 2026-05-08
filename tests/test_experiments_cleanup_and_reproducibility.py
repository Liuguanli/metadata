from __future__ import annotations

import json
from pathlib import Path

from experiments import benchmark_runner


def _load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_large_files_cleanup_and_reproducibility_token(tmp_path: Path) -> None:
    out1 = tmp_path / "large_files_run1"
    out2 = tmp_path / "large_files_run2"

    rc1 = benchmark_runner.main(
        [
            "large_files",
            "--output",
            str(out1),
            "--file-count",
            "80",
            "--large-file-size-mb",
            "101",
            "--seed",
            "42",
            "--cleanup-large-files",
            "true",
            "--cleanup-large-threshold-mb",
            "100",
        ]
    )
    assert rc1 == 0

    rc2 = benchmark_runner.main(
        [
            "large_files",
            "--output",
            str(out2),
            "--file-count",
            "80",
            "--large-file-size-mb",
            "101",
            "--seed",
            "42",
            "--cleanup-large-files",
            "true",
            "--cleanup-large-threshold-mb",
            "100",
        ]
    )
    assert rc2 == 0

    m1 = _load_manifest(out1 / "manifest.json")
    m2 = _load_manifest(out2 / "manifest.json")

    cleanup1 = m1.get("post_run_cleanup", {})
    assert cleanup1.get("enabled") is True
    assert int(cleanup1.get("removed_file_count", 0)) > 0
    assert int(cleanup1.get("removed_total_bytes", 0)) > 0

    big_files_after = [p for p in (out1 / "workspaces").rglob("*") if p.is_file() and p.stat().st_size >= 100 * 1024 * 1024]
    assert big_files_after == []

    assert m1.get("generated_file_hashes") == m2.get("generated_file_hashes")
    assert m1.get("reproducibility_token") == m2.get("reproducibility_token")
