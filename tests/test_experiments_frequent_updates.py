from __future__ import annotations

import csv
from pathlib import Path

from experiments import benchmark_runner


def test_frequent_updates_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "frequent_updates"
    exit_code = benchmark_runner.main(
        [
            "frequent_updates",
            "--output",
            str(output),
            "--file-count",
            "120",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "frequent_update_results.csv"
    events_path = output / "update_events.jsonl"
    assert csv_path.exists()
    assert events_path.exists()

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 3
    rates = {r["update_rate"] for r in rows}
    assert rates == {"low", "medium", "high"}
