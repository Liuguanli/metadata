from __future__ import annotations

import csv
from pathlib import Path

from experiments import benchmark_runner


def test_large_files_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "large_files"
    exit_code = benchmark_runner.main(
        [
            "large_files",
            "--output",
            str(output),
            "--file-count",
            "80",
            "--large-file-size-mb",
            "101",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "large_file_results.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 5  # five ratios
    assert set(r["large_file_ratio"] for r in rows) == {"0.0", "0.01", "0.05", "0.1", "0.2"}
