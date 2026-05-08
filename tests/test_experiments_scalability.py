from __future__ import annotations

import csv
import json
from pathlib import Path

from experiments import benchmark_runner


def test_scalability_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "scalability"
    exit_code = benchmark_runner.main(
        [
            "scalability",
            "--output",
            str(output),
            "--file-counts",
            "12",
            "24",
            "--duplicate-ratio",
            "0.1",
            "--repeats",
            "1",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "scalability_results.csv"
    manifest_path = output / "manifest.json"
    assert csv_path.exists()
    assert manifest_path.exists()

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 2
    expected_cols = {
        "run_id",
        "file_count",
        "duplicate_ratio",
        "seed",
        "repeat_id",
        "total_size_bytes",
        "scan_time_ms",
        "db_size_bytes",
        "active_files",
        "hashed_files",
        "skipped_hash_files",
        "avg_search_latency_ms",
        "p95_search_latency_ms",
        "duplicate_detection_time_ms",
    }
    assert expected_cols.issubset(set(rows[0].keys()))

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["experiment_name"] == "scalability"
    assert "result_files" in manifest and manifest["result_files"]
