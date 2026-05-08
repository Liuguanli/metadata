from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare figure-ready CSV files from experiment results")
    parser.add_argument("--input", default="experiment_results")
    parser.add_argument("--output", default="experiment_results/figure_data")
    return parser


def warn(msg: str) -> None:
    print(f"[warn] {msg}")


def pick_latest_file(input_dir: Path, filename: str) -> Path | None:
    candidates = sorted(input_dir.rglob(filename))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open("r", encoding="utf-8")))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def prepare_scan_scalability(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "scalability_results.csv")
    if src is None:
        warn("scalability_results.csv missing; skip figure_scan_scalability.csv")
        return False

    rows = read_csv_rows(src)
    by_count: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_count.setdefault(r["file_count"], []).append(r)

    out_rows: list[dict[str, Any]] = []
    for file_count, items in sorted(by_count.items(), key=lambda kv: int(kv[0])):
        scan_vals = [float(x["scan_time_ms"]) for x in items]
        db_vals = [float(x["db_size_bytes"]) for x in items]
        search_vals = [float(x["avg_search_latency_ms"]) for x in items]
        dup_vals = [float(x["duplicate_detection_time_ms"]) for x in items]
        out_rows.append(
            {
                "file_count": int(file_count),
                "mean_scan_time_ms": statistics.mean(scan_vals),
                "std_scan_time_ms": statistics.pstdev(scan_vals) if len(scan_vals) > 1 else 0.0,
                "mean_db_size_bytes": statistics.mean(db_vals),
                "mean_search_latency_ms": statistics.mean(search_vals),
                "mean_duplicate_detection_time_ms": statistics.mean(dup_vals),
            }
        )

    write_csv(
        output_dir / "figure_scan_scalability.csv",
        [
            "file_count",
            "mean_scan_time_ms",
            "std_scan_time_ms",
            "mean_db_size_bytes",
            "mean_search_latency_ms",
            "mean_duplicate_detection_time_ms",
        ],
        out_rows,
    )
    return True


def prepare_safety(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "safety_results.csv")
    if src is None:
        warn("safety_results.csv missing; skip figure_safety.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("safety_results.csv empty; skip figure_safety.csv")
        return False
    r = rows[0]
    out_rows = [
        {
            "baseline": "direct",
            "unauthorized_delete_count": int(r["unauthorized_delete_count"]),
            "unauthorized_overwrite_count": int(r["unauthorized_overwrite_count"]),
            "created_proposals": 0,
            "soft_deleted_files": 0,
            "recovery_possible_count": 0,
        },
        {
            "baseline": "metamirror",
            "unauthorized_delete_count": 0,
            "unauthorized_overwrite_count": 0,
            "created_proposals": int(r["metamirror_created_proposals"]),
            "soft_deleted_files": int(r["metamirror_soft_deleted_files"]),
            "recovery_possible_count": int(r["recovery_possible_count"]),
        },
    ]
    write_csv(
        output_dir / "figure_safety.csv",
        [
            "baseline",
            "unauthorized_delete_count",
            "unauthorized_overwrite_count",
            "created_proposals",
            "soft_deleted_files",
            "recovery_possible_count",
        ],
        out_rows,
    )
    return True


def prepare_metadata_utility(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "metadata_utility_results.csv")
    if src is None:
        warn("metadata_utility_results.csv missing; skip figure_metadata_utility.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("metadata_utility_results.csv empty; skip figure_metadata_utility.csv")
        return False

    by_topic: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        by_topic.setdefault(r["topic"], []).append(r)

    out_rows: list[dict[str, Any]] = []
    for topic, items in sorted(by_topic.items()):
        p5 = [float(x["precision_at_k"]) for x in items if x["k"] == "5"]
        p10 = [float(x["precision_at_k"]) for x in items if x["k"] == "10"]
        r10 = [float(x["recall_at_k"]) for x in items if x["k"] == "10"]
        mrr = [float(x["mrr"]) for x in items if x["k"] == "10"]
        raw_reads = [int(x["raw_file_reads"]) for x in items if x["k"] == "10"]
        out_rows.append(
            {
                "query_type": topic,
                "precision_at_5": statistics.mean(p5) if p5 else 0.0,
                "precision_at_10": statistics.mean(p10) if p10 else 0.0,
                "recall_at_10": statistics.mean(r10) if r10 else 0.0,
                "mrr": statistics.mean(mrr) if mrr else 0.0,
                "raw_file_reads": statistics.mean(raw_reads) if raw_reads else 0.0,
            }
        )

    write_csv(
        output_dir / "figure_metadata_utility.csv",
        ["query_type", "precision_at_5", "precision_at_10", "recall_at_10", "mrr", "raw_file_reads"],
        out_rows,
    )
    return True


def prepare_large_files(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "large_file_results.csv")
    if src is None:
        warn("large_file_results.csv missing; skip figure_large_files.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("large_file_results.csv empty; skip figure_large_files.csv")
        return False
    out_rows = [
        {
            "large_file_ratio": float(r["large_file_ratio"]),
            "scan_time_ms": float(r["scan_time_ms"]),
            "skipped_hash_files": int(r["skipped_hash_files"]),
            "basic_only_files": int(r["basic_only_files"]),
            "db_size_bytes": int(float(r["db_size_bytes"])),
        }
        for r in rows
    ]
    write_csv(
        output_dir / "figure_large_files.csv",
        ["large_file_ratio", "scan_time_ms", "skipped_hash_files", "basic_only_files", "db_size_bytes"],
        out_rows,
    )
    return True


def prepare_frequent_updates(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "frequent_update_results.csv")
    if src is None:
        warn("frequent_update_results.csv missing; skip figure_frequent_updates.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("frequent_update_results.csv empty; skip figure_frequent_updates.csv")
        return False
    out_rows = [
        {
            "update_rate": r["update_rate"],
            "db_update_count": int(r["number_of_db_updates"]),
            "stale_file_count": int(r["number_of_files_marked_stale"]),
            "event_to_db_latency_ms": float(r["event_to_db_latency_ms"]),
            "reconciliation_corrections": int(r["reconciliation_corrections"]),
        }
        for r in rows
    ]
    write_csv(
        output_dir / "figure_frequent_updates.csv",
        ["update_rate", "db_update_count", "stale_file_count", "event_to_db_latency_ms", "reconciliation_corrections"],
        out_rows,
    )
    return True


def prepare_metadata_consistency(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "metadata_consistency_results.csv")
    if src is None:
        warn("metadata_consistency_results.csv missing; skip figure_metadata_consistency.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("metadata_consistency_results.csv empty; skip figure_metadata_consistency.csv")
        return False

    out_rows: list[dict[str, Any]] = []
    for r in rows:
        if r.get("operation_type") == "ALL":
            continue
        out_rows.append(
            {
                "operation_type": r.get("operation_type", ""),
                "consistency_score": float(r.get("consistency_score", 0.0)),
                "invariant_violations": int(float(r.get("invariant_violations", 0))),
                "active_file_match_rate": float(r.get("active_file_match_rate", 0.0)),
                "db_active_validity": float(r.get("db_active_validity", 0.0)),
                "delete_tracking_accuracy": float(r.get("delete_tracking_accuracy", 0.0)),
                "update_tracking_accuracy": float(r.get("update_tracking_accuracy", 0.0)),
                "move_tracking_accuracy": float(r.get("move_tracking_accuracy", 0.0)),
                "proposal_consistency": float(r.get("proposal_consistency", 0.0)),
                "audit_completeness": float(r.get("audit_completeness", 0.0)),
                "reconcile_repair_rate": float(r.get("reconcile_repair_rate", 0.0)),
                "latency_ms": float(r.get("latency_ms", 0.0)),
            }
        )

    if not out_rows:
        warn("metadata_consistency_results.csv has no operation rows; skip figure_metadata_consistency.csv")
        return False

    write_csv(
        output_dir / "figure_metadata_consistency.csv",
        [
            "operation_type",
            "consistency_score",
            "invariant_violations",
            "active_file_match_rate",
            "db_active_validity",
            "delete_tracking_accuracy",
            "update_tracking_accuracy",
            "move_tracking_accuracy",
            "proposal_consistency",
            "audit_completeness",
            "reconcile_repair_rate",
            "latency_ms",
        ],
        out_rows,
    )
    return True


def prepare_token_efficiency(input_dir: Path, output_dir: Path) -> bool:
    src = pick_latest_file(input_dir, "token_efficiency_results.csv")
    if src is None:
        warn("token_efficiency_results.csv missing; skip figure_token_efficiency.csv")
        return False
    rows = read_csv_rows(src)
    if not rows:
        warn("token_efficiency_results.csv empty; skip figure_token_efficiency.csv")
        return False

    out_rows: list[dict[str, Any]] = []
    for r in rows:
        if str(r.get("k")) != "10":
            continue
        out_rows.append(
            {
                "query_id": r.get("query_id", ""),
                "topic": r.get("topic", ""),
                "metadata_context_tokens": int(float(r.get("metadata_context_tokens", 0))),
                "fulltext_context_tokens": int(float(r.get("fulltext_context_tokens", 0))),
                "token_saving": int(float(r.get("token_saving", 0))),
                "token_reduction_ratio": float(r.get("token_reduction_ratio", 0.0)),
                "precision_at_10": float(r.get("precision_at_k", 0.0)),
                "recall_at_10": float(r.get("recall_at_k", 0.0)),
                "mrr": float(r.get("mrr", 0.0)),
            }
        )

    if not out_rows:
        warn("token_efficiency_results.csv has no k=10 rows; skip figure_token_efficiency.csv")
        return False

    write_csv(
        output_dir / "figure_token_efficiency.csv",
        [
            "query_id",
            "topic",
            "metadata_context_tokens",
            "fulltext_context_tokens",
            "token_saving",
            "token_reduction_ratio",
            "precision_at_10",
            "recall_at_10",
            "mrr",
        ],
        out_rows,
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.exists():
        warn(f"input directory does not exist: {input_dir}")
        return 0

    generated = 0
    generated += 1 if prepare_scan_scalability(input_dir, output_dir) else 0
    generated += 1 if prepare_safety(input_dir, output_dir) else 0
    generated += 1 if prepare_metadata_utility(input_dir, output_dir) else 0
    generated += 1 if prepare_large_files(input_dir, output_dir) else 0
    generated += 1 if prepare_frequent_updates(input_dir, output_dir) else 0
    generated += 1 if prepare_metadata_consistency(input_dir, output_dir) else 0
    generated += 1 if prepare_token_efficiency(input_dir, output_dir) else 0

    print(f"prepare_figure_data done. generated_files={generated} output={output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
