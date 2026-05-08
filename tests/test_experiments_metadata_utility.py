from __future__ import annotations

import csv
from pathlib import Path

from experiments import benchmark_runner


def test_metadata_utility_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "metadata_utility"
    exit_code = benchmark_runner.main(
        [
            "metadata_utility",
            "--output",
            str(output),
            "--file-count",
            "120",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "metadata_utility_results.csv"
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 10  # 5 queries * 2 k values
    assert all(int(r["raw_file_reads"]) == 0 for r in rows)
