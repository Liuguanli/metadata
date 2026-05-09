from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/metamirror-mpl-cache")

import matplotlib.pyplot as plt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render publication-style plots from figure-ready CSV files")
    parser.add_argument("--input", default="experiment_results/figure_data", help="Figure-ready CSV directory")
    parser.add_argument("--output", default="experiment_results/figures", help="Output directory for plot files")
    return parser


def read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


def warn(msg: str) -> None:
    print(f"[warn] {msg}")


def _save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_dir / f"{stem}.png", dpi=220)
    fig.savefig(output_dir / f"{stem}.svg")
    plt.close(fig)


def _annotate_points(ax: plt.Axes, xs: list, ys: list[float], fmt: str = "{:.2f}") -> None:
    for x, y in zip(xs, ys):
        ax.annotate(fmt.format(y), (x, y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=8)


def plot_scan_scalability(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_scan_scalability.csv"
    if not src.exists():
        warn("figure_scan_scalability.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_scan_scalability.csv empty")
        return False

    x = [int(r["file_count"]) for r in rows]
    scan_mean = [float(r["mean_scan_time_ms"]) for r in rows]
    scan_std = [float(r["std_scan_time_ms"]) for r in rows]
    has_steady = all(r.get("mean_steady_scan_time_ms") not in (None, "") for r in rows)
    if has_steady:
        steady_mean = [float(r["mean_steady_scan_time_ms"]) for r in rows]
        steady_std = [float(r.get("std_steady_scan_time_ms") or 0.0) for r in rows]
    else:
        steady_mean = []
        steady_std = []
    db_size_mb = [float(r["mean_db_size_bytes"]) / (1024.0 * 1024.0) for r in rows]
    search_latency = [float(r["mean_search_latency_ms"]) for r in rows]
    dup_latency = [float(r["mean_duplicate_detection_time_ms"]) for r in rows]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    ax = axes[0][0]
    ax.errorbar(x, scan_mean, yerr=scan_std, marker="o", capsize=4, color="#1f77b4", label="Cold scan")
    if has_steady:
        ax.errorbar(x, steady_mean, yerr=steady_std, marker="s", capsize=4, color="#2ca02c", label="Steady-state")
        ax.legend(loc="upper left", fontsize=9)
    ax.set_title("A) Scan Time")
    ax.set_xlabel("File Count")
    ax.set_ylabel("ms")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.grid(alpha=0.3, which="both")
    _annotate_points(ax, x, scan_mean, "{:.1f}")
    if has_steady:
        _annotate_points(ax, x, steady_mean, "{:.1f}")

    ax = axes[0][1]
    ax.plot(x, db_size_mb, marker="o", color="#2ca02c")
    ax.set_title("B) Metadata DB Size")
    ax.set_xlabel("File Count")
    ax.set_ylabel("MB")
    ax.grid(alpha=0.3)
    _annotate_points(ax, x, db_size_mb, "{:.2f}")

    ax = axes[1][0]
    ax.plot(x, search_latency, marker="o", color="#ff7f0e")
    ax.set_title("C) Mean Search Latency")
    ax.set_xlabel("File Count")
    ax.set_ylabel("ms")
    ax.grid(alpha=0.3)
    _annotate_points(ax, x, search_latency, "{:.2f}")

    ax = axes[1][1]
    ax.plot(x, dup_latency, marker="o", color="#d62728")
    ax.set_title("D) Duplicate Detection Latency")
    ax.set_xlabel("File Count")
    ax.set_ylabel("ms")
    ax.grid(alpha=0.3)
    _annotate_points(ax, x, dup_latency, "{:.2f}")

    fig.suptitle("Scalability Overview", fontsize=14)
    _save(fig, output_dir, "figure_scan_scalability")
    return True


def plot_safety(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_safety.csv"
    if not src.exists():
        warn("figure_safety.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_safety.csv empty")
        return False

    by_key = {(r["task_id"], r["mode"]): r for r in rows}
    task_order = ["T1_duplicate_cleanup", "T2_archive_old", "T3_trim_large"]
    task_titles = {
        "T1_duplicate_cleanup": "T1: Duplicate Cleanup",
        "T2_archive_old": "T2: Archive Old",
        "T3_trim_large": "T3: Trim Large",
    }
    modes = ["direct", "metamirror"]
    mode_labels = {"direct": "Direct", "metamirror": "MetaMirror"}
    metric_keys = [
        ("executed_direct", "Raw mutations", "#d62728"),
        ("sensitive_or_important_touched", "Sensitive touched", "#ff9896"),
        ("recoverable_count", "Recoverable", "#2ca02c"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=False)
    width = 0.28
    x_positions = list(range(len(metric_keys)))

    for ax, task in zip(axes, task_order):
        if (task, "direct") not in by_key or (task, "metamirror") not in by_key:
            ax.set_title(f"{task_titles.get(task, task)}\n(no data)")
            ax.axis("off")
            continue
        for offset, mode in enumerate(modes):
            r = by_key[(task, mode)]
            heights = [int(r[key]) for key, _, _ in metric_keys]
            xs = [i + (offset - 0.5) * width for i in x_positions]
            colors = [c for _, _, c in metric_keys]
            for xi, h, c in zip(xs, heights, colors):
                hatch = "//" if mode == "metamirror" else None
                ax.bar(xi, h, width=width, color=c, hatch=hatch, edgecolor="white")
                if h > 0:
                    ax.annotate(
                        str(h),
                        (xi, h),
                        textcoords="offset points",
                        xytext=(0, 4),
                        ha="center",
                        fontsize=8,
                    )
        ax.set_xticks(x_positions, [name for _, name, _ in metric_keys], fontsize=9)
        ax.set_title(task_titles.get(task, task), fontsize=11)
        ax.grid(axis="y", alpha=0.3)
        ax.set_ylabel("Count")

    legend_handles = [
        plt.Rectangle((0, 0), 1, 1, color="#888", label=mode_labels["direct"]),
        plt.Rectangle((0, 0), 1, 1, color="#888", hatch="//", label=mode_labels["metamirror"]),
    ]
    fig.legend(handles=legend_handles, loc="upper center", ncol=2, fontsize=10, frameon=False)
    fig.suptitle("Per-Task Safety Outcomes (Direct vs MetaMirror)", fontsize=13, y=1.02)
    _save(fig, output_dir, "figure_safety")
    return True


def plot_metadata_utility(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_metadata_utility.csv"
    if not src.exists():
        warn("figure_metadata_utility.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_metadata_utility.csv empty")
        return False

    topics = [r["query_type"] for r in rows]
    p5 = [float(r["precision_at_5"]) for r in rows]
    p10 = [float(r["precision_at_10"]) for r in rows]
    r10 = [float(r["recall_at_10"]) for r in rows]
    mrr = [float(r["mrr"]) for r in rows]
    raw_reads = [float(r["raw_file_reads"]) for r in rows]

    x = list(range(len(topics)))
    w = 0.22
    fig, ax1 = plt.subplots(figsize=(12, 6))
    ax1.bar([i - w for i in x], p5, width=w, label="Precision@5", color="#1f77b4")
    ax1.bar(x, p10, width=w, label="Precision@10", color="#2ca02c")
    ax1.bar([i + w for i in x], r10, width=w, label="Recall@10", color="#ff7f0e")
    ax1.plot(x, mrr, marker="o", color="#d62728", linewidth=2, label="MRR")
    ax1.set_xticks(x, topics)
    ax1.set_ylim(0.0, 1.05)
    ax1.set_ylabel("Retrieval Score")
    ax1.set_title("Metadata Utility by Query Type")
    ax1.grid(axis="y", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(x, raw_reads, marker="s", color="#9467bd", linestyle="--", label="Raw File Reads")
    ax2.set_ylabel("Raw Reads")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="lower left")

    _save(fig, output_dir, "figure_metadata_utility")
    return True


def plot_large_files(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_large_files.csv"
    if not src.exists():
        warn("figure_large_files.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_large_files.csv empty")
        return False

    ratio = [float(r["large_file_ratio"]) * 100.0 for r in rows]
    scan = [float(r["scan_time_ms"]) for r in rows]
    skip = [float(r["skipped_hash_files"]) for r in rows]
    basic = [float(r["basic_only_files"]) for r in rows]
    db_mb = [float(r["db_size_bytes"]) / (1024.0 * 1024.0) for r in rows]

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0][0].plot(ratio, scan, marker="o", color="#1f77b4")
    axes[0][0].set_title("A) Scan Time")
    axes[0][0].set_xlabel("Large File Ratio (%)")
    axes[0][0].set_ylabel("ms")
    axes[0][0].grid(alpha=0.3)

    axes[0][1].plot(ratio, skip, marker="o", color="#d62728")
    axes[0][1].set_title("B) Skipped Hash Files")
    axes[0][1].set_xlabel("Large File Ratio (%)")
    axes[0][1].set_ylabel("count")
    axes[0][1].grid(alpha=0.3)

    axes[1][0].plot(ratio, basic, marker="o", color="#ff7f0e")
    axes[1][0].set_title("C) basic_only Files")
    axes[1][0].set_xlabel("Large File Ratio (%)")
    axes[1][0].set_ylabel("count")
    axes[1][0].grid(alpha=0.3)

    axes[1][1].plot(ratio, db_mb, marker="o", color="#2ca02c")
    axes[1][1].set_title("D) DB Size")
    axes[1][1].set_xlabel("Large File Ratio (%)")
    axes[1][1].set_ylabel("MB")
    axes[1][1].grid(alpha=0.3)

    fig.suptitle("Large-File Ratio Impact", fontsize=14)
    _save(fig, output_dir, "figure_large_files")
    return True


def plot_frequent_updates(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_frequent_updates.csv"
    if not src.exists():
        warn("figure_frequent_updates.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_frequent_updates.csv empty")
        return False

    rates = [r["update_rate"] for r in rows]
    db_updates = [float(r["db_update_count"]) for r in rows]
    stale = [float(r["stale_file_count"]) for r in rows]
    latency = [float(r["event_to_db_latency_ms"]) for r in rows]
    reconcile = [float(r["reconciliation_corrections"]) for r in rows]

    x = list(range(len(rates)))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    ax = axes[0]
    ax.bar(x, db_updates, color="#1f77b4", label="DB Updates")
    ax.plot(x, stale, color="#d62728", marker="o", label="Stale File Count")
    ax.set_xticks(x, rates)
    ax.set_title("A) Update Throughput")
    ax.set_ylabel("Count")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    ax = axes[1]
    ax.plot(x, latency, color="#2ca02c", marker="o", label="Event->DB Latency (ms)")
    ax.plot(x, reconcile, color="#9467bd", marker="s", label="Reconciliation Corrections")
    ax.set_xticks(x, rates)
    ax.set_title("B) Consistency Dynamics")
    ax.set_ylabel("Value")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    fig.suptitle("Frequent Update Behavior", fontsize=14)
    _save(fig, output_dir, "figure_frequent_updates")
    return True


def plot_metadata_consistency(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_metadata_consistency.csv"
    if not src.exists():
        warn("figure_metadata_consistency.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_metadata_consistency.csv empty")
        return False

    ops = [r["operation_type"] for r in rows]
    consistency = [float(r["consistency_score"]) for r in rows]
    violations = [float(r["invariant_violations"]) for r in rows]
    audit = [float(r["audit_completeness"]) for r in rows]
    reconcile = [float(r["reconcile_repair_rate"]) for r in rows]
    latency = [float(r["latency_ms"]) for r in rows]

    x = list(range(len(ops)))
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))

    ax = axes[0][0]
    ax.bar(x, consistency, color="#1f77b4")
    ax.set_xticks(x, ops, rotation=25, ha="right")
    ax.set_ylim(0.0, 1.05)
    ax.set_title("A) Consistency Score by Operation")
    ax.set_ylabel("score")
    ax.grid(axis="y", alpha=0.3)

    ax = axes[0][1]
    ax.bar(x, violations, color="#d62728")
    ax.set_xticks(x, ops, rotation=25, ha="right")
    ax.set_title("B) Invariant Violations by Operation")
    ax.set_ylabel("count")
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1][0]
    ax.plot(x, audit, marker="o", color="#2ca02c", label="Audit Completeness")
    ax.plot(x, reconcile, marker="s", color="#9467bd", label="Reconcile Repair Rate")
    ax.set_xticks(x, ops, rotation=25, ha="right")
    ax.set_ylim(0.0, 1.05)
    ax.set_title("C) Audit and Reconcile Metrics")
    ax.set_ylabel("rate")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    ax = axes[1][1]
    ax.bar(x, latency, color="#ff7f0e")
    ax.set_xticks(x, ops, rotation=25, ha="right")
    ax.set_title("D) Total Latency by Operation")
    ax.set_ylabel("ms")
    ax.grid(axis="y", alpha=0.3)

    fig.suptitle("Metadata Consistency Experiment (Latest Run)", fontsize=14)
    _save(fig, output_dir, "figure_metadata_consistency")
    return True


def plot_token_efficiency(input_dir: Path, output_dir: Path) -> bool:
    src = input_dir / "figure_token_efficiency.csv"
    if not src.exists():
        warn("figure_token_efficiency.csv missing")
        return False
    rows = read_csv(src)
    if not rows:
        warn("figure_token_efficiency.csv empty")
        return False

    labels = [f"{r['query_id']}:{r['topic']}" for r in rows]
    meta_tokens = [float(r["metadata_context_tokens"]) for r in rows]
    full_tokens = [float(r["fulltext_context_tokens"]) for r in rows]
    saving = [float(r["token_saving"]) for r in rows]
    reduction = [float(r["token_reduction_ratio"]) for r in rows]

    x = list(range(len(labels)))
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    ax = axes[0]
    width = 0.35
    ax.bar([i - width / 2 for i in x], full_tokens, width=width, color="#d62728", label="Fulltext Tokens")
    ax.bar([i + width / 2 for i in x], meta_tokens, width=width, color="#1f77b4", label="Metadata Tokens")
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_title("A) Context Token Cost (k=10)")
    ax.set_ylabel("estimated tokens")
    ax.grid(axis="y", alpha=0.3)
    ax.legend()

    ax = axes[1]
    ax.bar(x, reduction, color="#2ca02c", label="Reduction Ratio")
    ax.set_xticks(x, labels, rotation=20, ha="right")
    ax.set_title("B) Token Saving and Reduction")
    ax.set_ylabel("reduction ratio")
    ax.set_ylim(0.0, 1.05)
    ax.grid(axis="y", alpha=0.3)

    ax2 = ax.twinx()
    ax2.plot(x, saving, color="#9467bd", marker="o", label="Token Saving")
    ax2.set_ylabel("token saving")

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="best")

    fig.suptitle("Token Efficiency: Metadata vs Fulltext", fontsize=14)
    _save(fig, output_dir, "figure_token_efficiency")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    generated += 1 if plot_scan_scalability(input_dir, output_dir) else 0
    generated += 1 if plot_safety(input_dir, output_dir) else 0
    generated += 1 if plot_metadata_utility(input_dir, output_dir) else 0
    generated += 1 if plot_large_files(input_dir, output_dir) else 0
    generated += 1 if plot_frequent_updates(input_dir, output_dir) else 0
    generated += 1 if plot_metadata_consistency(input_dir, output_dir) else 0
    generated += 1 if plot_token_efficiency(input_dir, output_dir) else 0

    print(f"render_plots done. generated={generated} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
