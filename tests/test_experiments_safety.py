from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments import benchmark_runner


def test_safety_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "safety"
    exit_code = benchmark_runner.main(
        [
            "safety",
            "--output",
            str(output),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "safety_results.csv"
    events_path = output / "safety_events.jsonl"
    manifest_path = output / "manifest.json"
    assert csv_path.exists()
    assert events_path.exists()
    assert manifest_path.exists()

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 1
    assert int(rows[0]["metamirror_direct_deleted_files"]) == 0

    # Ensure JSONL lines are valid JSON when present
    for line in events_path.read_text(encoding="utf-8").splitlines():
        json.loads(line)
