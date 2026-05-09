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
    expected_tasks = {"T1_duplicate_cleanup", "T2_archive_old", "T3_trim_large"}
    expected_modes = {"direct", "metamirror"}
    assert {r["task_id"] for r in rows} == expected_tasks
    assert {r["mode"] for r in rows} == expected_modes
    assert len(rows) == len(expected_tasks) * len(expected_modes)

    by_key = {(r["task_id"], r["mode"]): r for r in rows}
    for task in expected_tasks:
        direct_row = by_key[(task, "direct")]
        mm_row = by_key[(task, "metamirror")]
        # Direct mode actually mutates the workspace; MetaMirror mode never
        # performs raw deletes, only proposes / approves / blocks.
        assert int(mm_row["executed_direct"]) == 0

    # Across the three tasks, MetaMirror should produce at least one
    # proposal (T1 duplicate-cleanup is the most reliable source).
    total_proposed = sum(int(r["proposed"]) for r in rows if r["mode"] == "metamirror")
    assert total_proposed >= 1

    # Ensure JSONL lines are valid JSON when present
    for line in events_path.read_text(encoding="utf-8").splitlines():
        json.loads(line)
