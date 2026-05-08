from __future__ import annotations

import csv
from pathlib import Path

from experiments import benchmark_runner


def test_token_efficiency_experiment_smoke(tmp_path: Path) -> None:
    output = tmp_path / "token_efficiency"
    exit_code = benchmark_runner.main(
        [
            "token_efficiency",
            "--output",
            str(output),
            "--file-count",
            "120",
            "--seed",
            "42",
        ]
    )
    assert exit_code == 0

    csv_path = output / "token_efficiency_results.csv"
    assert csv_path.exists()

    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8")))
    assert len(rows) == 10
    for r in rows:
        meta = int(r["metadata_context_tokens"])
        full = int(r["fulltext_context_tokens"])
        saving = int(r["token_saving"])
        assert full >= meta
        assert saving == full - meta
