from __future__ import annotations

import csv
from pathlib import Path

from experiments import benchmark_runner


def test_history_audit_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "history_audit"
    exit_code = benchmark_runner.main(
        [
            "history_audit",
            "--output",
            str(output),
            "--file-count",
            "100",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "history_audit_results.csv"
    gt_path = output / "ground_truth_events.jsonl"
    mm_path = output / "metamirror_events.jsonl"
    assert csv_path.exists()
    assert gt_path.exists()
    assert mm_path.exists()

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 1
    for k in [
        "event_recall",
        "event_precision",
        "missing_detection_accuracy",
        "move_detection_accuracy",
        "proposal_status_accuracy",
        "audit_completeness",
    ]:
        assert k in rows[0]
