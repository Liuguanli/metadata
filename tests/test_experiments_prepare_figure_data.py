from __future__ import annotations

from pathlib import Path

from experiments import benchmark_runner, prepare_figure_data


def test_prepare_figure_data_smoke(tmp_path: Path) -> None:
    base = tmp_path / "results"
    base.mkdir(parents=True, exist_ok=True)

    benchmark_runner.main(
        [
            "scalability",
            "--output",
            str(base / "scalability"),
            "--file-counts",
            "20",
            "--repeats",
            "1",
            "--seed",
            "42",
        ]
    )
    benchmark_runner.main(
        [
            "safety",
            "--output",
            str(base / "safety"),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )
    benchmark_runner.main(
        [
            "metadata_utility",
            "--output",
            str(base / "metadata_utility"),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )
    benchmark_runner.main(
        [
            "large_files",
            "--output",
            str(base / "large_files"),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )
    benchmark_runner.main(
        [
            "frequent_updates",
            "--output",
            str(base / "frequent_updates"),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )
    benchmark_runner.main(
        [
            "metadata_consistency",
            "--output",
            str(base / "metadata_consistency"),
            "--file-count",
            "60",
            "--operation-count",
            "30",
            "--seed",
            "42",
            "--cleanup-temp",
            "true",
        ]
    )
    benchmark_runner.main(
        [
            "token_efficiency",
            "--output",
            str(base / "token_efficiency"),
            "--file-count",
            "80",
            "--seed",
            "42",
        ]
    )

    out = base / "figure_data"
    exit_code = prepare_figure_data.main(["--input", str(base), "--output", str(out)])
    assert exit_code == 0

    assert (out / "figure_scan_scalability.csv").exists()
    assert (out / "figure_safety.csv").exists()
    assert (out / "figure_metadata_utility.csv").exists()
    assert (out / "figure_large_files.csv").exists()
    assert (out / "figure_frequent_updates.csv").exists()
    assert (out / "figure_metadata_consistency.csv").exists()
    assert (out / "figure_token_efficiency.csv").exists()
