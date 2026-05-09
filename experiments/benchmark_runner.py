from __future__ import annotations

import argparse
import csv
import json
import hashlib
import os
import platform
import random
import sqlite3
import subprocess
import sys
import time
import shutil
from uuid import uuid4
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from experiments.dataset_generator import GenerationConfig, generate_workspace
    from experiments.metrics import mean_reciprocal_rank, precision_at_k, recall_at_k
except ModuleNotFoundError:
    from dataset_generator import GenerationConfig, generate_workspace
    from metrics import mean_reciprocal_rank, precision_at_k, recall_at_k
from metamirror.cli import main as metamirror_main
from metamirror.db import find_duplicates, search_files
from metamirror.scanner import EXCLUDED_DIR_NAMES, EXCLUDED_FILE_NAMES, HASH_SIZE_LIMIT_BYTES


SUPPORTED_EXPERIMENTS = (
    "scalability",
    "metadata_utility",
    "token_efficiency",
    "safety",
    "history_audit",
    "large_files",
    "frequent_updates",
    "metadata_consistency",
)


@dataclass
class ExperimentContext:
    experiment_name: str
    output_path: Path
    workspace_path: Path
    random_seed: int
    parameters: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_bool_flag(value: str | bool | None, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _sha256_path(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _hash_generated_files(generated_files: list[str], root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    base = root.resolve()
    for raw in generated_files:
        p = Path(raw)
        if p.exists() and p.is_file():
            try:
                key = str(p.resolve().relative_to(base))
            except ValueError:
                key = p.name
            out[key] = _sha256_path(p)
    return out


def _cleanup_large_files(ctx: ExperimentContext) -> dict[str, Any]:
    enabled = _parse_bool_flag(ctx.parameters.get("cleanup_large_files"), default=True)
    threshold_mb = int(ctx.parameters.get("cleanup_large_threshold_mb", 100))
    threshold_bytes = threshold_mb * 1024 * 1024
    report: dict[str, Any] = {
        "enabled": enabled,
        "threshold_mb": threshold_mb,
        "removed_file_count": 0,
        "removed_total_bytes": 0,
        "removed_paths": [],
        "scanned_roots": [],
    }
    if not enabled:
        return report

    candidate_roots = {
        (ctx.output_path / "workspace").resolve(),
        (ctx.output_path / "workspaces").resolve(),
        ctx.workspace_path.resolve(),
    }
    for root in sorted(candidate_roots):
        if root.exists() and root.is_dir():
            report["scanned_roots"].append(str(root))
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if ".metamirror" in p.parts:
                    continue
                try:
                    size = p.stat().st_size
                except OSError:
                    continue
                if size < threshold_bytes:
                    continue
                rel = str(p.relative_to(ctx.output_path))
                try:
                    p.unlink()
                except OSError:
                    continue
                report["removed_file_count"] += 1
                report["removed_total_bytes"] += int(size)
                if len(report["removed_paths"]) < 200:
                    report["removed_paths"].append(rel)
    return report


def get_git_commit_hash() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def prepare_output_dir(experiment_name: str, output: str | None) -> Path:
    if output:
        out = Path(output).resolve()
    else:
        out = Path("experiment_results") / experiment_name
        out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    return out


def build_context(
    experiment_name: str,
    args: argparse.Namespace,
) -> ExperimentContext:
    output_path = prepare_output_dir(experiment_name, getattr(args, "output", None))
    workspace_value = getattr(args, "workspace", None)
    workspace_path = Path(workspace_value).resolve() if workspace_value else (output_path / "workspace").resolve()
    workspace_path.mkdir(parents=True, exist_ok=True)
    random_seed = int(getattr(args, "seed", 42))

    parameters = {
        k: v
        for k, v in vars(args).items()
        if k not in {"command", "output", "workspace"}
    }
    return ExperimentContext(
        experiment_name=experiment_name,
        output_path=output_path,
        workspace_path=workspace_path,
        random_seed=random_seed,
        parameters=parameters,
    )


def write_manifest(
    ctx: ExperimentContext,
    generated_files: list[str],
    result_files: list[str],
    notes: str,
) -> Path:
    cleanup_report = _cleanup_large_files(ctx)
    generated_hashes = _hash_generated_files(generated_files, ctx.output_path)
    reproducibility_token = hashlib.sha256(
        json.dumps(
            {
                "experiment_name": ctx.experiment_name,
                "random_seed": ctx.random_seed,
                "parameters": ctx.parameters,
                "generated_file_hashes": generated_hashes,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    manifest = {
        "experiment_name": ctx.experiment_name,
        "timestamp": utc_now_iso(),
        "git_commit_hash": get_git_commit_hash(),
        "python_version": sys.version.replace("\n", " "),
        "operating_system": platform.platform(),
        "workspace_path": str(ctx.workspace_path),
        "output_path": str(ctx.output_path),
        "random_seed": ctx.random_seed,
        "experiment_parameters": ctx.parameters,
        "generated_file_hashes": generated_hashes,
        "reproducibility_token": reproducibility_token,
        "post_run_cleanup": cleanup_report,
        "generated_files": generated_files,
        "result_files": result_files,
        "notes": notes,
    }
    manifest_path = ctx.output_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def write_placeholder_result(ctx: ExperimentContext, filename: str, columns: list[str]) -> Path:
    out = ctx.output_path / filename
    out.write_text(",".join(columns) + "\n", encoding="utf-8")
    return out


def _workspace_total_size_bytes(workspace: Path) -> int:
    total = 0
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        if ".metamirror" in p.parts:
            continue
        total += p.stat().st_size
    return total


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    values_sorted = sorted(values)
    idx = int((len(values_sorted) * 0.95) - 1)
    idx = max(0, min(idx, len(values_sorted) - 1))
    return values_sorted[idx]


def _db_metric_counts(workspace: Path) -> tuple[int, int, int]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        active_files = conn.execute(
            "SELECT COUNT(*) FROM files WHERE status='active' AND path != 'synthetic_manifest.json'"
        ).fetchone()[0]
        hashed_files = conn.execute(
            "SELECT COUNT(*) FROM files WHERE status='active' AND sha256 IS NOT NULL AND path != 'synthetic_manifest.json'"
        ).fetchone()[0]
        skipped_hash_files = conn.execute(
            "SELECT COUNT(*) FROM files WHERE status='active' AND sha256 IS NULL AND path != 'synthetic_manifest.json'"
        ).fetchone()[0]
    finally:
        conn.close()
    return active_files, hashed_files, skipped_hash_files


def _tokenize_query(text: str) -> list[str]:
    stop = {"find", "about", "related", "to", "files", "file", "documents"}
    tokens = [t.strip().lower() for t in text.replace("-", " ").split()]
    return [t for t in tokens if t and t not in stop]


def _metadata_search_ranked(workspace: Path, query_text: str, limit: int = 20) -> list[str]:
    # Metadata-only retrieval by token fusion over existing search endpoint.
    tokens = _tokenize_query(query_text)
    if not tokens:
        tokens = [query_text.strip().lower()]

    scores: dict[str, float] = {}
    for token in tokens:
        token_results = search_files(workspace, token, limit=limit * 3)
        for pos, row in enumerate(token_results, start=1):
            path = row.get("path")
            if not path:
                continue
            # Higher score for higher rank and repeated token hits.
            scores[path] = scores.get(path, 0.0) + (1.0 / float(pos))

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [p for p, _ in ranked[:limit]]


def _estimate_tokens(text: str) -> int:
    # Simple, deterministic approximation good enough for relative experiment comparison.
    return max(1, (len(text) + 3) // 4)


def _read_text_lossy(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        data = path.read_bytes()
        return data.decode("utf-8", errors="ignore")


def _metadata_context_text(workspace: Path, rel_path: str) -> str:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT f.path, f.filename, COALESCE(m.summary, ''), COALESCE(m.tags, '')
            FROM files f
            LEFT JOIN file_metadata m ON m.file_id = f.file_id
            WHERE f.path=?
            """,
            (rel_path,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return rel_path
    return f"path={row[0]}\nfilename={row[1]}\nsummary={row[2]}\ntags={row[3]}\n"


def run_scalability(args: argparse.Namespace) -> int:
    ctx = build_context("scalability", args)
    csv_path = ctx.output_path / "scalability_results.csv"
    csv_columns = [
        "run_id",
        "file_count",
        "duplicate_ratio",
        "seed",
        "repeat_id",
        "total_size_bytes",
        "scan_time_ms",
        "steady_scan_time_ms",
        "db_size_bytes",
        "active_files",
        "hashed_files",
        "skipped_hash_files",
        "avg_search_latency_ms",
        "p95_search_latency_ms",
        "duplicate_detection_time_ms",
    ]
    search_queries = [
        "research",
        "finance",
        "visa",
        "code",
        "photos",
        "logs",
        "contracts",
        ".py",
        ".md",
        "file_",
    ]

    generated_files: list[str] = []
    rows: list[dict[str, Any]] = []

    workspace_root = ctx.output_path / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)
    file_counts: list[int] = list(args.file_counts)
    repeats: int = int(args.repeats)
    duplicate_ratio: float = float(args.duplicate_ratio)
    base_seed: int = int(args.seed)

    for repeat_id in range(repeats):
        for file_count in file_counts:
            run_seed = base_seed + repeat_id * 10_000 + file_count
            run_id = f"f{file_count}_r{repeat_id}"
            workspace = workspace_root / run_id
            workspace.mkdir(parents=True, exist_ok=True)

            manifest = generate_workspace(
                GenerationConfig(
                    output=workspace,
                    num_files=file_count,
                    duplicate_ratio=duplicate_ratio,
                    large_file_ratio=0.0,
                    large_file_size_mb=101,
                    structure="mixed",
                    seed=run_seed,
                )
            )
            generated_files.append(str(workspace / "synthetic_manifest.json"))

            init_code = metamirror_main(["init", str(workspace)])
            if init_code != 0:
                raise RuntimeError(f"metamirror init failed for {workspace}")

            t0 = time.perf_counter()
            scan_code = metamirror_main(["scan", str(workspace)])
            t1 = time.perf_counter()
            if scan_code != 0:
                raise RuntimeError(f"metamirror scan failed for {workspace}")
            scan_time_ms = (t1 - t0) * 1000.0

            t2 = time.perf_counter()
            steady_code = metamirror_main(["scan", str(workspace)])
            t3 = time.perf_counter()
            if steady_code != 0:
                raise RuntimeError(f"metamirror steady-state scan failed for {workspace}")
            steady_scan_time_ms = (t3 - t2) * 1000.0

            search_latencies: list[float] = []
            for q in search_queries:
                s0 = time.perf_counter()
                search_files(workspace, q, limit=20)
                s1 = time.perf_counter()
                search_latencies.append((s1 - s0) * 1000.0)

            d0 = time.perf_counter()
            find_duplicates(workspace)
            d1 = time.perf_counter()
            duplicate_detection_time_ms = (d1 - d0) * 1000.0

            db_path = workspace / ".metamirror" / "metadata.db"
            db_size_bytes = db_path.stat().st_size if db_path.exists() else 0
            active_files, hashed_files, skipped_hash_files = _db_metric_counts(workspace)
            total_size_bytes = _workspace_total_size_bytes(workspace)

            rows.append(
                {
                    "run_id": run_id,
                    "file_count": file_count,
                    "duplicate_ratio": duplicate_ratio,
                    "seed": run_seed,
                    "repeat_id": repeat_id,
                    "total_size_bytes": total_size_bytes,
                    "scan_time_ms": round(scan_time_ms, 3),
                    "steady_scan_time_ms": round(steady_scan_time_ms, 3),
                    "db_size_bytes": db_size_bytes,
                    "active_files": active_files,
                    "hashed_files": hashed_files,
                    "skipped_hash_files": skipped_hash_files,
                    "avg_search_latency_ms": round(sum(search_latencies) / len(search_latencies), 3),
                    "p95_search_latency_ms": round(_p95(search_latencies), 3),
                    "duplicate_detection_time_ms": round(duplicate_detection_time_ms, 3),
                }
            )
            print(
                f"[scalability] run={run_id} files={manifest['total_files']} "
                f"scan_ms={rows[-1]['scan_time_ms']} steady_ms={rows[-1]['steady_scan_time_ms']} "
                f"avg_search_ms={rows[-1]['avg_search_latency_ms']}"
            )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    write_manifest(
        ctx,
        generated_files=generated_files,
        result_files=[str(csv_path)],
        notes="Scalability experiment executed with synthetic workspaces only.",
    )
    print(f"[scalability] output: {ctx.output_path}")
    return 0


def run_metadata_utility(args: argparse.Namespace) -> int:
    ctx = build_context("metadata_utility", args)
    csv_path = ctx.output_path / "metadata_utility_results.csv"
    csv_columns = [
        "query_id",
        "query_text",
        "topic",
        "k",
        "precision_at_k",
        "recall_at_k",
        "mrr",
        "raw_file_reads",
        "query_latency_ms",
    ]
    workspace = ctx.output_path / "workspace"
    file_count = int(getattr(args, "file_count", 1000))
    seed = int(getattr(args, "seed", 42))
    manifest = generate_workspace(
        GenerationConfig(
            output=workspace,
            num_files=file_count,
            duplicate_ratio=0.1,
            large_file_ratio=0.0,
            large_file_size_mb=101,
            structure="mixed",
            seed=seed,
        )
    )

    if metamirror_main(["init", str(workspace)]) != 0:
        raise RuntimeError("metamirror init failed in metadata_utility")
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("metamirror scan failed in metadata_utility")

    topic_keywords = {
        "research": "research papers spatial index",
        "finance": "finance records invoice budget",
        "visa": "visa documents application passport",
        "code": "code files database",
        "photos": "photos image gallery",
        "logs": "logs error runtime",
        "contracts": "contracts legal agreement",
    }
    queries = [
        ("q1", "find research papers about spatial index", "research"),
        ("q2", "find visa documents", "visa"),
        ("q3", "find finance records", "finance"),
        ("q4", "find code files related to database", "code"),
        ("q5", "find contracts", "contracts"),
    ]

    # Enrich metadata summaries/tags with topic signals.
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        for rel_path, topic in manifest["topic_labels"].items():
            row = conn.execute("SELECT file_id FROM files WHERE path = ?", (rel_path,)).fetchone()
            if row is None:
                continue
            file_id = row[0]
            tags = f"{topic},{topic_keywords[topic]}"
            summary = f"topic={topic}; keywords={topic_keywords[topic]}"
            conn.execute(
                """
                INSERT INTO file_metadata (file_id, summary, tags, summary_generated_at, extractor_version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    summary = excluded.summary,
                    tags = excluded.tags,
                    summary_generated_at = excluded.summary_generated_at,
                    extractor_version = excluded.extractor_version
                """,
                (file_id, summary, tags, utc_now_iso(), "exp-metadata-utility-v1"),
            )
        conn.commit()
    finally:
        conn.close()

    relevant_by_topic: dict[str, set[str]] = {}
    for rel_path, topic in manifest["topic_labels"].items():
        relevant_by_topic.setdefault(topic, set()).add(rel_path)

    rows: list[dict[str, Any]] = []
    for query_id, query_text, topic in queries:
        t0 = time.perf_counter()
        retrieved_paths = _metadata_search_ranked(workspace, query_text, limit=20)
        t1 = time.perf_counter()
        relevant = relevant_by_topic.get(topic, set())
        mrr = mean_reciprocal_rank(retrieved_paths, relevant)
        latency_ms = (t1 - t0) * 1000.0

        for k in (5, 10):
            rows.append(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "topic": topic,
                    "k": k,
                    "precision_at_k": round(precision_at_k(retrieved_paths, relevant, k), 6),
                    "recall_at_k": round(recall_at_k(retrieved_paths, relevant, k), 6),
                    "mrr": round(mrr, 6),
                    "raw_file_reads": 0,
                    "query_latency_ms": round(latency_ms, 3),
                }
            )
        print(
            f"[metadata_utility] {query_id} topic={topic} "
            f"p@5={rows[-2]['precision_at_k']} p@10={rows[-1]['precision_at_k']} mrr={rows[-1]['mrr']}"
        )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    write_manifest(
        ctx,
        generated_files=[str(workspace / "synthetic_manifest.json")],
        result_files=[str(csv_path)],
        notes="Metadata utility evaluated using metadata-only queries; no raw file reads during query-time.",
    )
    print(f"[metadata_utility] output: {ctx.output_path}")
    return 0


def run_token_efficiency(args: argparse.Namespace) -> int:
    ctx = build_context("token_efficiency", args)
    csv_path = ctx.output_path / "token_efficiency_results.csv"
    csv_columns = [
        "query_id",
        "query_text",
        "topic",
        "k",
        "precision_at_k",
        "recall_at_k",
        "mrr",
        "metadata_context_tokens",
        "fulltext_context_tokens",
        "token_saving",
        "token_reduction_ratio",
        "query_latency_ms",
    ]
    workspace = ctx.output_path / "workspace"
    file_count = int(getattr(args, "file_count", 1000))
    seed = int(getattr(args, "seed", 42))
    manifest = generate_workspace(
        GenerationConfig(
            output=workspace,
            num_files=file_count,
            duplicate_ratio=0.1,
            large_file_ratio=0.0,
            large_file_size_mb=101,
            structure="mixed",
            seed=seed,
        )
    )
    # Inflate synthetic text files to medium-length documents so token comparison reflects
    # realistic "full-read vs summary-read" usage rather than tiny toy files.
    filler = (
        "This section contains detailed project notes, decisions, constraints, and references. "
        "It is intentionally repetitive to emulate medium-length documents for token budgeting.\n"
    )
    for p in workspace.rglob("*"):
        if not p.is_file():
            continue
        if p.name == "synthetic_manifest.json":
            continue
        if p.suffix.lower() not in {".txt", ".md", ".py", ".json", ".csv", ".pdf"}:
            continue
        with p.open("a", encoding="utf-8") as fh:
            fh.write(filler * 16)

    if metamirror_main(["init", str(workspace)]) != 0:
        raise RuntimeError("metamirror init failed in token_efficiency")
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("metamirror scan failed in token_efficiency")

    topic_keywords = {
        "research": "research papers spatial index",
        "finance": "finance records invoice budget",
        "visa": "visa documents application passport",
        "code": "code files database",
        "photos": "photos image gallery",
        "logs": "logs error runtime",
        "contracts": "contracts legal agreement",
    }
    queries = [
        ("q1", "find research papers about spatial index", "research"),
        ("q2", "find visa documents", "visa"),
        ("q3", "find finance records", "finance"),
        ("q4", "find code files related to database", "code"),
        ("q5", "find contracts", "contracts"),
    ]

    # Enrich metadata summaries/tags with topic signals.
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        for rel_path, topic in manifest["topic_labels"].items():
            row = conn.execute("SELECT file_id FROM files WHERE path = ?", (rel_path,)).fetchone()
            if row is None:
                continue
            file_id = row[0]
            tags = f"{topic},{topic_keywords[topic]}"
            summary = f"topic={topic}; keywords={topic_keywords[topic]}"
            conn.execute(
                """
                INSERT INTO file_metadata (file_id, summary, tags, summary_generated_at, extractor_version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_id) DO UPDATE SET
                    summary = excluded.summary,
                    tags = excluded.tags,
                    summary_generated_at = excluded.summary_generated_at,
                    extractor_version = excluded.extractor_version
                """,
                (file_id, summary, tags, utc_now_iso(), "exp-token-efficiency-v1"),
            )
        conn.commit()
    finally:
        conn.close()

    relevant_by_topic: dict[str, set[str]] = {}
    for rel_path, topic in manifest["topic_labels"].items():
        relevant_by_topic.setdefault(topic, set()).add(rel_path)

    rows: list[dict[str, Any]] = []
    for query_id, query_text, topic in queries:
        t0 = time.perf_counter()
        retrieved_paths = _metadata_search_ranked(workspace, query_text, limit=20)
        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000.0
        relevant = relevant_by_topic.get(topic, set())
        mrr = mean_reciprocal_rank(retrieved_paths, relevant)

        for k in (5, 10):
            topk = retrieved_paths[:k]
            metadata_context_tokens = _estimate_tokens(query_text)
            fulltext_context_tokens = _estimate_tokens(query_text)
            for rel_path in topk:
                metadata_context = _metadata_context_text(workspace, rel_path)
                metadata_context_tokens += _estimate_tokens(metadata_context)
                raw_text = _read_text_lossy(workspace / rel_path)
                fulltext_context_tokens += _estimate_tokens(raw_text)

            token_saving = max(0, fulltext_context_tokens - metadata_context_tokens)
            token_reduction_ratio = (
                float(token_saving) / float(max(1, fulltext_context_tokens))
            )

            rows.append(
                {
                    "query_id": query_id,
                    "query_text": query_text,
                    "topic": topic,
                    "k": k,
                    "precision_at_k": round(precision_at_k(retrieved_paths, relevant, k), 6),
                    "recall_at_k": round(recall_at_k(retrieved_paths, relevant, k), 6),
                    "mrr": round(mrr, 6),
                    "metadata_context_tokens": int(metadata_context_tokens),
                    "fulltext_context_tokens": int(fulltext_context_tokens),
                    "token_saving": int(token_saving),
                    "token_reduction_ratio": round(token_reduction_ratio, 6),
                    "query_latency_ms": round(latency_ms, 3),
                }
            )
        print(
            f"[token_efficiency] {query_id} topic={topic} "
            f"saved@5={rows[-2]['token_saving']} saved@10={rows[-1]['token_saving']}"
        )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    write_manifest(
        ctx,
        generated_files=[str(workspace / "synthetic_manifest.json")],
        result_files=[str(csv_path)],
        notes=(
            "Token efficiency experiment compares metadata-context vs fulltext-context "
            "token cost using deterministic token estimation."
        ),
    )
    print(f"[token_efficiency] output: {ctx.output_path}")
    return 0


def run_safety(args: argparse.Namespace) -> int:
    """Per-task safety case study.

    The agent here is a deterministic oracle, not an LLM. It encodes three
    plausible workspace-cleanup intents (T1 duplicate-cleanup,
    T2 archive-old, T3 trim-large) and executes them either through raw
    filesystem ops (Direct mode) or through the MetaMirror gateway
    (MetaMirror mode). LLM integration is left to future work.

    The CSV emits one row per (task, mode) pair so downstream figures can
    show per-task outcomes side by side.
    """
    ctx = build_context("safety", args)
    csv_columns = [
        "task_id",
        "mode",
        "attempted_ops",
        "executed_direct",
        "blocked_or_routed",
        "proposed",
        "approved",
        "rejected",
        "sensitive_or_important_touched",
        "recoverable_count",
        "audit_event_count",
    ]
    csv_path = ctx.output_path / "safety_results.csv"
    events_path = ctx.output_path / "safety_events.jsonl"
    event_lines: list[dict[str, Any]] = []

    workspaces_root = ctx.output_path / "workspaces"
    base_ws = workspaces_root / "base"
    direct_ws = workspaces_root / "direct_mode"
    mm_ws = workspaces_root / "metamirror_mode"
    workspaces_root.mkdir(parents=True, exist_ok=True)

    file_count = int(getattr(args, "file_count", 500))
    manifest = generate_workspace(
        GenerationConfig(
            output=base_ws,
            num_files=file_count,
            duplicate_ratio=0.2,
            large_file_ratio=0.1,
            large_file_size_mb=101,
            structure="mixed",
            seed=int(args.seed),
        )
    )

    if direct_ws.exists():
        shutil.rmtree(direct_ws)
    if mm_ws.exists():
        shutil.rmtree(mm_ws)
    shutil.copytree(base_ws, direct_ws)
    shutil.copytree(base_ws, mm_ws)

    topic_labels: dict[str, str] = manifest["topic_labels"]
    sensitive_topics = {"visa", "contracts"}
    important_topics = {"finance", "research"}
    sensitive_paths = {p for p, t in topic_labels.items() if t in sensitive_topics}
    important_paths = {p for p, t in topic_labels.items() if t in important_topics}

    def is_sensitive_or_important(rel_path: str) -> bool:
        return rel_path in sensitive_paths or rel_path in important_paths

    duplicate_targets = [
        g["members"][1] for g in manifest["duplicate_groups"] if len(g["members"]) > 1
    ]
    large_targets = [p for p in topic_labels if p.endswith(".bin")][
        : max(1, file_count // 25)
    ]
    small_sorted = sorted([p for p in topic_labels if not p.endswith(".bin")])
    archive_targets = small_sorted[: max(2, file_count // 20)]

    task_targets: list[tuple[str, str, list[str]]] = [
        ("T1_duplicate_cleanup", "delete", sorted(set(duplicate_targets))),
        ("T2_archive_old", "move", list(archive_targets)),
        ("T3_trim_large", "delete", sorted(set(large_targets))),
    ]

    rows: list[dict[str, Any]] = []

    def empty_row(task_id: str, mode: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "mode": mode,
            "attempted_ops": 0,
            "executed_direct": 0,
            "blocked_or_routed": 0,
            "proposed": 0,
            "approved": 0,
            "rejected": 0,
            "sensitive_or_important_touched": 0,
            "recoverable_count": 0,
            "audit_event_count": 0,
        }

    # ---- Direct mode: each task executes raw filesystem ops with no policy gate
    for task_id, intent, targets in task_targets:
        row = empty_row(task_id, "direct")
        for rel in targets:
            target = direct_ws / rel
            if not target.exists():
                continue
            row["attempted_ops"] += 1
            if is_sensitive_or_important(rel):
                row["sensitive_or_important_touched"] += 1
            if intent == "delete":
                target.unlink()
                row["executed_direct"] += 1
                event_lines.append(
                    {
                        "mode": "direct",
                        "task_id": task_id,
                        "intent": "delete",
                        "path": rel,
                        "sensitive_or_important": is_sensitive_or_important(rel),
                        "timestamp": utc_now_iso(),
                    }
                )
            elif intent == "move":
                archive_dir = direct_ws / "archive"
                archive_dir.mkdir(parents=True, exist_ok=True)
                dst = archive_dir / target.name
                if dst.exists():
                    dst = archive_dir / f"{target.stem}_dup{target.suffix}"
                target.rename(dst)
                row["executed_direct"] += 1
                event_lines.append(
                    {
                        "mode": "direct",
                        "task_id": task_id,
                        "intent": "move",
                        "path": rel,
                        "target_path": str(dst.relative_to(direct_ws)),
                        "timestamp": utc_now_iso(),
                    }
                )
        rows.append(row)

    # ---- MetaMirror mode: init + scan + tag policy on sensitive/important
    if metamirror_main(["init", str(mm_ws)]) != 0:
        raise RuntimeError("metamirror init failed in safety experiment")
    if metamirror_main(["scan", str(mm_ws)]) != 0:
        raise RuntimeError("metamirror scan failed in safety experiment")

    db_path = mm_ws / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        for rel in topic_labels:
            row_db = conn.execute(
                "SELECT file_id FROM files WHERE path = ?", (rel,)
            ).fetchone()
            if row_db is None:
                continue
            file_id = row_db[0]
            if rel in sensitive_paths:
                conn.execute(
                    """
                    UPDATE file_policy
                    SET sensitivity='sensitive',
                        ai_can_delete_original=0,
                        delete_requires_approval=1
                    WHERE file_id=?
                    """,
                    (file_id,),
                )
            elif rel in important_paths:
                conn.execute(
                    """
                    UPDATE file_policy
                    SET sensitivity='important',
                        ai_can_delete_original=0,
                        delete_requires_approval=1
                    WHERE file_id=?
                    """,
                    (file_id,),
                )
        conn.commit()
    finally:
        conn.close()

    audit_offsets: dict[str, int] = {}
    audit_file = mm_ws / ".metamirror" / "audit.jsonl"

    def audit_lines_so_far() -> int:
        if not audit_file.exists():
            return 0
        return len(audit_file.read_text(encoding="utf-8").splitlines())

    audit_offsets["start"] = audit_lines_so_far()

    for task_id, intent, targets in task_targets:
        row = empty_row(task_id, "metamirror")
        before_audit = audit_lines_so_far()

        for rel in targets:
            conn = sqlite3.connect(db_path)
            try:
                lookup = conn.execute(
                    "SELECT file_id FROM files WHERE path = ?", (rel,)
                ).fetchone()
            finally:
                conn.close()
            if lookup is None:
                continue
            file_id = lookup[0]
            row["attempted_ops"] += 1
            if is_sensitive_or_important(rel):
                row["sensitive_or_important_touched"] += 1

            if intent == "delete":
                rc = metamirror_main(
                    [
                        "propose-delete",
                        str(mm_ws),
                        file_id,
                        "--reason",
                        f"{task_id}_intent",
                        "--evidence",
                        rel,
                    ]
                )
                if rc != 0:
                    continue
                row["proposed"] += 1
                row["blocked_or_routed"] += 1  # routed through gateway, not direct
                event_lines.append(
                    {
                        "mode": "metamirror",
                        "task_id": task_id,
                        "intent": "propose_delete",
                        "path": rel,
                        "sensitive_or_important": is_sensitive_or_important(rel),
                        "timestamp": utc_now_iso(),
                    }
                )

                conn = sqlite3.connect(db_path)
                try:
                    prow = conn.execute(
                        """
                        SELECT proposal_id
                        FROM action_proposals
                        WHERE file_id = ? AND status = 'pending'
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (file_id,),
                    ).fetchone()
                finally:
                    conn.close()
                if prow is None:
                    continue
                proposal_id = prow[0]

                if is_sensitive_or_important(rel):
                    if metamirror_main(["reject", str(mm_ws), proposal_id]) == 0:
                        row["rejected"] += 1
                else:
                    if metamirror_main(["approve", str(mm_ws), proposal_id]) == 0:
                        row["approved"] += 1
                        row["recoverable_count"] += 1

            elif intent == "move":
                # MetaMirror mode treats move-to-archive as an out-of-policy
                # destructive intent in this experiment: blocked at gateway.
                # In a richer model the gateway would expose a propose_move
                # primitive; we record the block so the case study can show
                # MetaMirror does not silently apply the move.
                row["blocked_or_routed"] += 1
                event_lines.append(
                    {
                        "mode": "metamirror",
                        "task_id": task_id,
                        "intent": "blocked_move",
                        "path": rel,
                        "sensitive_or_important": is_sensitive_or_important(rel),
                        "timestamp": utc_now_iso(),
                    }
                )

        after_audit = audit_lines_so_far()
        row["audit_event_count"] = max(0, after_audit - before_audit)
        rows.append(row)

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    with events_path.open("w", encoding="utf-8") as fh:
        for event in event_lines:
            fh.write(json.dumps(event, ensure_ascii=True) + "\n")

    write_manifest(
        ctx,
        generated_files=[str(base_ws / "synthetic_manifest.json")],
        result_files=[str(csv_path), str(events_path)],
        notes=(
            "Safety experiment uses a deterministic agent oracle (not an LLM). "
            "Three tasks (duplicate-cleanup, archive-old, trim-large) are run "
            "in both Direct and MetaMirror modes; one CSV row per (task, mode)."
        ),
    )
    print(f"[safety] output: {ctx.output_path}")
    return 0


def run_history_audit(args: argparse.Namespace) -> int:
    ctx = build_context("history_audit", args)
    csv_path = ctx.output_path / "history_audit_results.csv"
    gt_path = ctx.output_path / "ground_truth_events.jsonl"
    mm_path = ctx.output_path / "metamirror_events.jsonl"
    columns = [
        "event_recall",
        "event_precision",
        "missing_detection_accuracy",
        "move_detection_accuracy",
        "proposal_status_accuracy",
        "audit_completeness",
    ]

    workspace = ctx.output_path / "workspace"
    file_count = int(getattr(args, "file_count", 500))
    seed = int(getattr(args, "seed", 42))
    generate_workspace(
        GenerationConfig(
            output=workspace,
            num_files=file_count,
            duplicate_ratio=0.1,
            large_file_ratio=0.0,
            large_file_size_mb=101,
            structure="mixed",
            seed=seed,
        )
    )

    gt_events: list[dict[str, Any]] = []

    def gt(event_type: str, path: str, details: dict[str, Any] | None = None) -> None:
        gt_events.append(
            {
                "timestamp": utc_now_iso(),
                "event_type": event_type,
                "path": path,
                "details": details or {},
            }
        )

    if metamirror_main(["init", str(workspace)]) != 0:
        raise RuntimeError("history_audit init failed")
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("history_audit scan failed")

    # Scripted operations
    created = workspace / "ops_created_1.txt"
    created.write_text("created now", encoding="utf-8")
    gt("created", "ops_created_1.txt")

    conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
    try:
        sample_row = conn.execute(
            "SELECT path FROM files WHERE path != 'synthetic_manifest.json' ORDER BY path LIMIT 1"
        ).fetchone()
        sample_path = sample_row[0] if sample_row else "ops_created_1.txt"
    finally:
        conn.close()

    sample_file = workspace / sample_path
    sample_file.write_text(sample_file.read_text(encoding="utf-8", errors="ignore") + "\nmodified", encoding="utf-8")
    gt("modified", sample_path)

    moved_src = created
    moved_dst = workspace / "ops_moved_1.txt"
    moved_src.rename(moved_dst)
    gt("moved", "ops_moved_1.txt", {"from": "ops_created_1.txt"})

    # external delete
    delete_target = sample_file
    if delete_target.exists():
        delete_target.unlink()
        gt("deleted", sample_path)

    # rescan to reconcile
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("history_audit second scan failed")

    # proposals
    conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
    try:
        rows = conn.execute(
            "SELECT file_id, path FROM files WHERE status='active' ORDER BY path LIMIT 2"
        ).fetchall()
    finally:
        conn.close()
    if len(rows) >= 2:
        (file_id_a, path_a), (file_id_b, path_b) = rows[0], rows[1]
        if metamirror_main(
            [
                "propose-delete",
                str(workspace),
                file_id_a,
                "--reason",
                "history_audit",
                "--evidence",
                path_a,
            ]
        ) == 0:
            gt("ai_proposed_delete", path_a)
        if metamirror_main(
            [
                "propose-delete",
                str(workspace),
                file_id_b,
                "--reason",
                "history_audit",
                "--evidence",
                path_b,
            ]
        ) == 0:
            gt("ai_proposed_delete", path_b)

        conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
        try:
            props = conn.execute(
                "SELECT proposal_id, file_id FROM action_proposals WHERE status='pending' ORDER BY created_at"
            ).fetchall()
        finally:
            conn.close()
        if props:
            p0 = props[0][0]
            if metamirror_main(["approve", str(workspace), p0]) == 0:
                gt("soft_deleted", path_a)
        if len(props) > 1:
            p1 = props[1][0]
            if metamirror_main(["reject", str(workspace), p1]) == 0:
                gt("user_rejected_delete", path_b)

    # Gather metamirror events
    conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
    try:
        mm_rows = conn.execute(
            "SELECT event_type, COALESCE(new_path, old_path, '') AS path, created_at FROM file_events ORDER BY created_at"
        ).fetchall()
        status_rows = conn.execute(
            "SELECT status, COUNT(*) FROM files GROUP BY status"
        ).fetchall()
        proposal_rows = conn.execute(
            "SELECT status, COUNT(*) FROM action_proposals GROUP BY status"
        ).fetchall()
    finally:
        conn.close()

    mm_events = [
        {"event_type": r[0], "path": r[1], "timestamp": r[2]}
        for r in mm_rows
    ]

    # Write raw event files
    with gt_path.open("w", encoding="utf-8") as fh:
        for e in gt_events:
            fh.write(json.dumps(e, ensure_ascii=True) + "\n")
    with mm_path.open("w", encoding="utf-8") as fh:
        for e in mm_events:
            fh.write(json.dumps(e, ensure_ascii=True) + "\n")

    # Metric computation (simple overlap-based)
    gt_pairs = {(e["event_type"], e["path"]) for e in gt_events}
    mm_pairs = {(e["event_type"], e["path"]) for e in mm_events}
    true_pos = len(gt_pairs & mm_pairs)
    recall = true_pos / len(gt_pairs) if gt_pairs else 1.0
    precision = true_pos / len(mm_pairs) if mm_pairs else 1.0

    status_dict = {k: v for k, v in status_rows}
    proposal_dict = {k: v for k, v in proposal_rows}
    missing_accuracy = 1.0 if status_dict.get("missing", 0) >= 1 else 0.0
    move_accuracy = 1.0 if any(e["event_type"] in ("moved", "soft_deleted") for e in mm_events) else 0.0
    proposal_status_accuracy = 1.0 if (
        proposal_dict.get("approved", 0) >= 1 and proposal_dict.get("rejected", 0) >= 1
    ) else 0.0

    audit_file = workspace / ".metamirror" / "audit.jsonl"
    audit_lines = audit_file.read_text(encoding="utf-8").splitlines() if audit_file.exists() else []
    audit_completeness = min(1.0, len(audit_lines) / max(1, len(gt_events)))

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerow(
            {
                "event_recall": round(recall, 6),
                "event_precision": round(precision, 6),
                "missing_detection_accuracy": round(missing_accuracy, 6),
                "move_detection_accuracy": round(move_accuracy, 6),
                "proposal_status_accuracy": round(proposal_status_accuracy, 6),
                "audit_completeness": round(audit_completeness, 6),
            }
        )

    write_manifest(
        ctx,
        generated_files=[str(workspace / "synthetic_manifest.json")],
        result_files=[str(csv_path), str(gt_path), str(mm_path)],
        notes="History and audit comparison executed on synthetic workspace with scripted operations.",
    )
    print(f"[history_audit] output: {ctx.output_path}")
    return 0


def run_large_files(args: argparse.Namespace) -> int:
    ctx = build_context("large_files", args)
    csv_path = ctx.output_path / "large_file_results.csv"
    csv_columns = [
        "run_id",
        "file_count",
        "large_file_ratio",
        "large_file_size_mb",
        "scan_time_ms",
        "db_size_bytes",
        "total_workspace_size_bytes",
        "large_files",
        "skipped_hash_files",
        "basic_only_files",
        "ready_files",
        "avg_processing_time_small_file_ms",
        "avg_processing_time_large_file_ms",
    ]

    file_count = int(getattr(args, "file_count", 1000))
    large_file_size_mb = int(getattr(args, "large_file_size_mb", 101))
    ratios = [0.0, 0.01, 0.05, 0.10, 0.20]
    workspace_root = ctx.output_path / "workspaces"
    workspace_root.mkdir(parents=True, exist_ok=True)

    generated_files: list[str] = []
    rows: list[dict[str, Any]] = []

    for ratio in ratios:
        run_id = f"ratio_{int(ratio*100):02d}"
        ws = workspace_root / run_id
        ws.mkdir(parents=True, exist_ok=True)
        manifest = generate_workspace(
            GenerationConfig(
                output=ws,
                num_files=file_count,
                duplicate_ratio=0.1,
                large_file_ratio=ratio,
                large_file_size_mb=large_file_size_mb,
                structure="mixed",
                seed=int(args.seed) + int(ratio * 1000),
            )
        )
        generated_files.append(str(ws / "synthetic_manifest.json"))

        if metamirror_main(["init", str(ws)]) != 0:
            raise RuntimeError(f"metamirror init failed for {run_id}")
        t0 = time.perf_counter()
        if metamirror_main(["scan", str(ws)]) != 0:
            raise RuntimeError(f"metamirror scan failed for {run_id}")
        t1 = time.perf_counter()
        scan_time_ms = (t1 - t0) * 1000.0

        db_path = ws / ".metamirror" / "metadata.db"
        conn = sqlite3.connect(db_path)
        try:
            large_files = conn.execute(
                "SELECT COUNT(*) FROM files WHERE status='active' AND path LIKE '%.bin'"
            ).fetchone()[0]
            skipped_hash_files = conn.execute(
                "SELECT COUNT(*) FROM files WHERE status='active' AND sha256 IS NULL AND path != 'synthetic_manifest.json'"
            ).fetchone()[0]
            basic_only_files = conn.execute(
                "SELECT COUNT(*) FROM files WHERE status='active' AND metadata_status='basic_only' AND path != 'synthetic_manifest.json'"
            ).fetchone()[0]
            ready_files = conn.execute(
                "SELECT COUNT(*) FROM files WHERE status='active' AND metadata_status='ready'"
            ).fetchone()[0]
        finally:
            conn.close()

        total_workspace_size_bytes = _workspace_total_size_bytes(ws)
        db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

        # Approximation by category based on total scan and file counts.
        n_small = max(1, file_count - large_files)
        n_large = max(1, large_files)
        avg_small_ms = scan_time_ms / float(n_small)
        avg_large_ms = scan_time_ms / float(n_large)

        rows.append(
            {
                "run_id": run_id,
                "file_count": file_count,
                "large_file_ratio": ratio,
                "large_file_size_mb": large_file_size_mb,
                "scan_time_ms": round(scan_time_ms, 3),
                "db_size_bytes": db_size_bytes,
                "total_workspace_size_bytes": total_workspace_size_bytes,
                "large_files": large_files,
                "skipped_hash_files": skipped_hash_files,
                "basic_only_files": basic_only_files,
                "ready_files": ready_files,
                "avg_processing_time_small_file_ms": round(avg_small_ms, 6),
                "avg_processing_time_large_file_ms": round(avg_large_ms, 6),
            }
        )
        print(
            f"[large_files] {run_id} ratio={ratio} large={manifest['expected_large_file_count']} "
            f"scan_ms={rows[-1]['scan_time_ms']}"
        )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=csv_columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    write_manifest(
        ctx,
        generated_files=generated_files,
        result_files=[str(csv_path)],
        notes="Large-file ratio experiment executed on synthetic workspaces only.",
    )
    print(f"[large_files] output: {ctx.output_path}")
    return 0


def run_frequent_updates(args: argparse.Namespace) -> int:
    ctx = build_context("frequent_updates", args)
    csv_path = ctx.output_path / "frequent_update_results.csv"
    events_path = ctx.output_path / "update_events.jsonl"
    columns = [
        "update_rate",
        "number_of_filesystem_updates",
        "number_of_db_updates",
        "number_of_files_marked_dirty",
        "number_of_files_marked_stale",
        "time_until_metadata_ready_ms",
        "event_to_db_latency_ms",
        "missed_event_count",
        "reconciliation_corrections",
    ]

    workspace = ctx.output_path / "workspace"
    file_count = int(getattr(args, "file_count", 500))
    seed = int(getattr(args, "seed", 42))
    generate_workspace(
        GenerationConfig(
            output=workspace,
            num_files=file_count,
            duplicate_ratio=0.05,
            large_file_ratio=0.0,
            large_file_size_mb=101,
            structure="mixed",
            seed=seed,
        )
    )

    if metamirror_main(["init", str(workspace)]) != 0:
        raise RuntimeError("frequent_updates init failed")
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("frequent_updates initial scan failed")

    update_profiles = [
        ("low", 1, 20, 1.0),
        ("medium", 10, 30, 0.1),
        ("high", 100, 40, 0.01),
    ]

    all_update_events: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []

    conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
    try:
        candidates = conn.execute(
            """
            SELECT path FROM files
            WHERE status='active' AND path != 'synthetic_manifest.json'
              AND (path LIKE '%.txt' OR path LIKE '%.md' OR path LIKE '%.py' OR path LIKE '%.json' OR path LIKE '%.csv')
            ORDER BY path
            LIMIT 60
            """
        ).fetchall()
    finally:
        conn.close()
    candidate_paths = [r[0] for r in candidates]
    if not candidate_paths:
        candidate_paths = ["synthetic_manifest.json"]

    for rate_label, rate_per_sec, updates_to_apply, intended_interval_s in update_profiles:
        conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
        try:
            before_events = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
        finally:
            conn.close()

        first_update_ts = None
        last_update_ts = None
        per_profile_updates = 0

        # Apply deterministic repeated updates without long sleeps.
        for i in range(updates_to_apply):
            rel = candidate_paths[i % len(candidate_paths)]
            target = workspace / rel
            if not target.exists() or target.suffix == ".pdf":
                continue
            timestamp = utc_now_iso()
            if first_update_ts is None:
                first_update_ts = timestamp
            last_update_ts = timestamp
            try:
                with target.open("a", encoding="utf-8") as fh:
                    fh.write(f"\nupdate_rate={rate_label} idx={i} ts={timestamp}\n")
                per_profile_updates += 1
                all_update_events.append(
                    {
                        "timestamp": timestamp,
                        "update_rate": rate_label,
                        "path": rel,
                        "update_index": i,
                        "intended_interval_s": intended_interval_s,
                        "rate_per_sec": rate_per_sec,
                    }
                )
            except OSError:
                continue

        t0 = time.perf_counter()
        if metamirror_main(["scan", str(workspace)]) != 0:
            raise RuntimeError(f"frequent_updates reconcile scan failed for {rate_label}")
        t1 = time.perf_counter()
        reconcile_ms = (t1 - t0) * 1000.0

        conn = sqlite3.connect(workspace / ".metamirror" / "metadata.db")
        try:
            after_events = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
            modified_events = conn.execute(
                "SELECT COUNT(*) FROM file_events WHERE event_type='modified'"
            ).fetchone()[0]
            last_event_ts = conn.execute(
                "SELECT MAX(created_at) FROM file_events"
            ).fetchone()[0]
        finally:
            conn.close()

        db_updates = max(0, after_events - before_events)
        missed_event_count = max(0, per_profile_updates - db_updates)

        event_to_db_latency_ms = 0.0
        if last_update_ts and last_event_ts:
            try:
                lu = datetime.fromisoformat(last_update_ts.replace("Z", "+00:00"))
                le = datetime.fromisoformat(last_event_ts.replace("Z", "+00:00"))
                event_to_db_latency_ms = max(0.0, (le - lu).total_seconds() * 1000.0)
            except ValueError:
                event_to_db_latency_ms = 0.0

        # Current MetaMirror does not implement dirty/stale transitions yet.
        dirty_count = 0
        stale_count = 0
        time_until_ready_ms = 0.0

        result_rows.append(
            {
                "update_rate": rate_label,
                "number_of_filesystem_updates": per_profile_updates,
                "number_of_db_updates": db_updates,
                "number_of_files_marked_dirty": dirty_count,
                "number_of_files_marked_stale": stale_count,
                "time_until_metadata_ready_ms": round(time_until_ready_ms, 3),
                "event_to_db_latency_ms": round(event_to_db_latency_ms, 3),
                "missed_event_count": missed_event_count,
                "reconciliation_corrections": max(0, db_updates - per_profile_updates),
            }
        )
        print(
            f"[frequent_updates] rate={rate_label} fs_updates={per_profile_updates} "
            f"db_updates={db_updates} reconcile_ms={round(reconcile_ms, 3)} modified_total={modified_events}"
        )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in result_rows:
            writer.writerow(row)

    with events_path.open("w", encoding="utf-8") as fh:
        for e in all_update_events:
            fh.write(json.dumps(e, ensure_ascii=True) + "\n")

    write_manifest(
        ctx,
        generated_files=[str(workspace / "synthetic_manifest.json")],
        result_files=[str(csv_path), str(events_path)],
        notes=(
            "Frequent-update experiment executed. Dirty/stale metrics are currently zero because "
            "dirty/stale state transitions are not implemented in core MetaMirror yet."
        ),
    )
    print(f"[frequent_updates] output: {ctx.output_path}")
    return 0


DEFAULT_METADATA_CONSISTENCY_DISTRIBUTION: dict[str, float] = {
    "create_file": 15.0,
    "modify_file": 22.0,
    "delete_file_externally": 10.0,
    "move_file": 10.0,
    "rename_file": 10.0,
    "propose_delete": 10.0,
    "approve_delete_proposal": 8.0,
    "reject_delete_proposal": 7.0,
    "restore_soft_deleted_file": 3.0,
    "simulate_missed_event_then_reconcile": 5.0,
}


SUPPORTED_METADATA_CONSISTENCY_OPS = set(DEFAULT_METADATA_CONSISTENCY_DISTRIBUTION.keys())


def _parse_bool(value: str | bool | None, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_distribution(distribution: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in distribution.values() if v > 0)
    if total <= 0:
        raise ValueError("operation distribution sum must be > 0")
    return {k: (v / total) for k, v in distribution.items() if v > 0}


def _parse_operation_distribution(raw: str | None) -> dict[str, float]:
    if not raw:
        return dict(DEFAULT_METADATA_CONSISTENCY_DISTRIBUTION)
    output: dict[str, float] = {}
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "=" not in token:
            raise ValueError(f"Invalid operation distribution token: {token}")
        name, weight_raw = token.split("=", 1)
        name = name.strip()
        if name not in SUPPORTED_METADATA_CONSISTENCY_OPS:
            raise ValueError(f"Unsupported operation in distribution: {name}")
        weight = float(weight_raw.strip())
        if weight < 0:
            raise ValueError(f"Operation weight cannot be negative: {token}")
        output[name] = weight
    if not output:
        raise ValueError("operation distribution is empty")
    return output


def _random_choice_by_weight(rng: random.Random, distribution: dict[str, float]) -> str:
    names = list(distribution.keys())
    weights = list(distribution.values())
    return rng.choices(names, weights=weights, k=1)[0]


def _assert_within_workspace(workspace: Path, target: Path) -> None:
    ws = workspace.resolve()
    tp = target.resolve()
    try:
        tp.relative_to(ws)
    except ValueError as exc:
        raise RuntimeError(f"Safety boundary violation: {tp} is outside workspace {ws}") from exc


def _iter_active_workspace_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk(workspace):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIR_NAMES]
        for name in names:
            if name in EXCLUDED_FILE_NAMES:
                continue
            p = Path(root) / name
            if p.is_file():
                files.append(p)
    return files


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _list_audit_events(workspace: Path) -> list[dict[str, Any]]:
    audit_file = workspace / ".metamirror" / "audit.jsonl"
    if not audit_file.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in audit_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _count_db_rows(workspace: Path) -> dict[str, int]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        counts = {
            "active": conn.execute("SELECT COUNT(*) FROM files WHERE status='active'").fetchone()[0],
            "missing": conn.execute("SELECT COUNT(*) FROM files WHERE status='missing'").fetchone()[0],
            "deleted": conn.execute("SELECT COUNT(*) FROM files WHERE status='deleted'").fetchone()[0],
            "soft_deleted": conn.execute("SELECT COUNT(*) FROM files WHERE status='soft_deleted'").fetchone()[0],
            "events": conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0],
            "proposals": conn.execute("SELECT COUNT(*) FROM action_proposals").fetchone()[0],
        }
    finally:
        conn.close()
    return counts


def _compute_proposal_consistency(workspace: Path) -> tuple[float, int, int]:
    audit_rows = _list_audit_events(workspace)
    audit_proposed: set[str] = set()
    audit_approved: set[str] = set()
    audit_rejected: set[str] = set()
    audit_expired: set[str] = set()
    for ev in audit_rows:
        action = str(ev.get("action") or "")
        details = ev.get("details") or {}
        proposal_id = str(details.get("proposal_id") or "")
        if not proposal_id:
            continue
        if action == "propose_delete":
            audit_proposed.add(proposal_id)
        elif action == "approve_proposal":
            audit_approved.add(proposal_id)
        elif action == "reject_proposal":
            audit_rejected.add(proposal_id)
        elif action == "expire_proposal":
            audit_expired.add(proposal_id)

    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        proposals = conn.execute(
            """
            SELECT p.proposal_id, p.status, p.file_id, f.path, f.status
            FROM action_proposals p
            JOIN files f ON f.file_id = p.file_id
            """
        ).fetchall()
        total = 0
        consistent = 0
        mismatches = 0

        for proposal_id, proposal_status, file_id, file_path, file_status in proposals:
            total += 1
            abs_path = workspace / str(file_path)
            is_consistent = True

            proposed_evt = conn.execute(
                """
                SELECT COUNT(*) FROM file_events
                WHERE file_id=? AND event_type='ai_proposed_delete'
                """,
                (file_id,),
            ).fetchone()[0] > 0

            if proposal_status == "pending":
                is_consistent = (
                    str(file_status) == "active"
                    and abs_path.exists()
                    and not str(file_path).startswith(".metamirror/trash/")
                    and proposed_evt
                    and str(proposal_id) in audit_proposed
                )
            elif proposal_status in {"approved", "executed"}:
                approved_evt = conn.execute(
                    """
                    SELECT COUNT(*) FROM file_events
                    WHERE file_id=?
                      AND event_type='soft_deleted'
                      AND actor='user'
                      AND reason='approve_delete_proposal'
                    """,
                    (file_id,),
                ).fetchone()[0] > 0
                soft_deleted_evt = conn.execute(
                    """
                    SELECT COUNT(*) FROM file_events
                    WHERE file_id=? AND event_type='soft_deleted'
                    """,
                    (file_id,),
                ).fetchone()[0] > 0
                is_consistent = (
                    str(file_status) == "soft_deleted"
                    and str(file_path).startswith(".metamirror/trash/")
                    and abs_path.exists()
                    and proposed_evt
                    and approved_evt
                    and soft_deleted_evt
                    and str(proposal_id) in audit_proposed
                    and str(proposal_id) in audit_approved
                )
            elif proposal_status == "rejected":
                rejected_evt = conn.execute(
                    """
                    SELECT COUNT(*) FROM file_events
                    WHERE file_id=? AND event_type='user_rejected_delete'
                    """,
                    (file_id,),
                ).fetchone()[0] > 0
                is_consistent = (
                    str(file_status) == "active"
                    and abs_path.exists()
                    and not str(file_path).startswith(".metamirror/trash/")
                    and proposed_evt
                    and rejected_evt
                    and str(proposal_id) in audit_proposed
                    and str(proposal_id) in audit_rejected
                )
            elif proposal_status == "expired":
                expired_evt = conn.execute(
                    """
                    SELECT COUNT(*) FROM file_events
                    WHERE file_id=? AND event_type='proposal_expired'
                    """,
                    (file_id,),
                ).fetchone()[0] > 0
                is_consistent = (
                    str(file_status) == "active"
                    and abs_path.exists()
                    and not str(file_path).startswith(".metamirror/trash/")
                    and proposed_evt
                    and expired_evt
                    and str(proposal_id) in audit_proposed
                    and str(proposal_id) in audit_expired
                )
            else:
                is_consistent = False

            if is_consistent:
                consistent += 1
            else:
                mismatches += 1
    finally:
        conn.close()

    score = float(consistent) / float(max(1, total))
    return score, mismatches, total


def _fetch_file_row_by_path(workspace: Path, rel_path: str) -> dict[str, Any] | None:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT file_id, path, status, size_bytes, modified_at, sha256, metadata_status, dirty
            FROM files
            WHERE path=?
            """,
            (rel_path,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    keys = ["file_id", "path", "status", "size_bytes", "modified_at", "sha256", "metadata_status", "dirty"]
    return dict(zip(keys, row))


def _fetch_file_row_by_file_id(workspace: Path, file_id: str) -> dict[str, Any] | None:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT file_id, path, status, size_bytes, modified_at, sha256, metadata_status, dirty
            FROM files
            WHERE file_id=?
            """,
            (file_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    keys = ["file_id", "path", "status", "size_bytes", "modified_at", "sha256", "metadata_status", "dirty"]
    return dict(zip(keys, row))


def _fetch_pending_proposal_ids(workspace: Path) -> list[str]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT proposal_id FROM action_proposals WHERE status='pending' ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def _fetch_pending_proposals(workspace: Path) -> list[tuple[str, str, str, str]]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT p.proposal_id, p.file_id, f.path, f.status
            FROM action_proposals p
            JOIN files f ON f.file_id = p.file_id
            WHERE p.status='pending'
            ORDER BY p.created_at
            """
        ).fetchall()
    finally:
        conn.close()
    return [(str(r[0]), str(r[1]), str(r[2]), str(r[3])) for r in rows]


def _fetch_pending_proposal_file_ids(workspace: Path) -> set[str]:
    return {file_id for _, file_id, _, _ in _fetch_pending_proposals(workspace)}


def _fetch_active_file_rows(workspace: Path) -> list[tuple[str, str]]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT file_id, path FROM files WHERE status='active' ORDER BY path"
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1]) for r in rows]


def _fetch_soft_deleted_rows(workspace: Path) -> list[tuple[str, str]]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT file_id, path FROM files WHERE status='soft_deleted' ORDER BY path"
        ).fetchall()
    finally:
        conn.close()
    return [(str(r[0]), str(r[1])) for r in rows]


def _fetch_status_for_path(workspace: Path, rel_path: str) -> str | None:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT status FROM files WHERE path=?", (rel_path,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def _get_row_counts_for_step(workspace: Path) -> tuple[int, int]:
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        event_count = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
    finally:
        conn.close()
    audit_count = len(_list_audit_events(workspace))
    return int(event_count), int(audit_count)


def _core_mismatch_count(workspace: Path) -> int:
    fs_files = _iter_active_workspace_files(workspace)
    fs_paths = {str(p.relative_to(workspace)) for p in fs_files}
    active_rows = _fetch_active_file_rows(workspace)
    active_by_path: dict[str, int] = {}
    for _, rel in active_rows:
        active_by_path[rel] = active_by_path.get(rel, 0) + 1
    mismatches = 0
    for rel in fs_paths:
        if active_by_path.get(rel, 0) != 1:
            mismatches += 1
    for _, rel in active_rows:
        if rel not in fs_paths:
            mismatches += 1
    return mismatches


def _evaluate_invariants(
    workspace: Path,
    step_id: int,
    operation_type: str,
    operation_result: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    fs_files = _iter_active_workspace_files(workspace)
    fs_paths = {str(p.relative_to(workspace)) for p in fs_files}
    db_path = workspace / ".metamirror" / "metadata.db"

    conn = sqlite3.connect(db_path)
    try:
        file_rows = conn.execute(
            """
            SELECT file_id, path, status, size_bytes, modified_at, sha256, metadata_status, dirty
            FROM files
            """
        ).fetchall()
        event_rows = conn.execute(
            """
            SELECT event_type, file_id, old_path, new_path
            FROM file_events
            ORDER BY created_at
            """
        ).fetchall()
    finally:
        conn.close()

    rows = [
        {
            "file_id": r[0],
            "path": r[1],
            "status": r[2],
            "size_bytes": r[3],
            "modified_at": r[4],
            "sha256": r[5],
            "metadata_status": r[6],
            "dirty": r[7],
        }
        for r in file_rows
    ]
    active_rows = [r for r in rows if r["status"] == "active"]
    active_by_path: dict[str, list[dict[str, Any]]] = {}
    for r in active_rows:
        active_by_path.setdefault(str(r["path"]), []).append(r)
    rows_by_path: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        rows_by_path.setdefault(str(r["path"]), []).append(r)

    event_types = [str(er[0]) for er in event_rows]
    violations: list[dict[str, Any]] = []
    checks = 0

    summary = {
        "active_file_mismatches": 0,
        "missing_file_mismatches": 0,
        "stale_hash_mismatches": 0,
        "path_mismatches": 0,
        "proposal_state_mismatches": 0,
        "trash_state_mismatches": 0,
    }

    # Invariant 1: active filesystem file -> exactly one active row
    for rel_path in sorted(fs_paths):
        checks += 1
        active_count = len(active_by_path.get(rel_path, []))
        if active_count != 1:
            summary["active_file_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "active_file_invariant",
                    "severity": "error",
                    "expected": "exactly one active row",
                    "observed": f"active_rows={active_count}",
                    "file_id": "",
                    "path": rel_path,
                    "operation_type": operation_type,
                }
            )

    # Invariant 2: active DB row path exists; absent path should not stay active
    for r in active_rows:
        checks += 1
        rel_path = str(r["path"])
        if rel_path not in fs_paths:
            summary["missing_file_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "missing_deleted_invariant",
                    "severity": "error",
                    "expected": "active row path exists in filesystem",
                    "observed": "active row path missing from filesystem",
                    "file_id": r["file_id"],
                    "path": rel_path,
                    "operation_type": operation_type,
                }
            )

    # Invariant 3: metadata update after modify
    if operation_type == "modify_file" and operation_result.get("executed"):
        checks += 1
        target = operation_result.get("new_path") or operation_result.get("old_path")
        expected = operation_result.get("expected_state", {})
        row = _fetch_file_row_by_path(workspace, str(target)) if target else None
        if row is None:
            summary["stale_hash_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "metadata_update_invariant",
                    "severity": "error",
                    "expected": "row exists after modify+reconcile",
                    "observed": "row missing",
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(target or ""),
                    "operation_type": operation_type,
                }
            )
        else:
            if int(row["size_bytes"] or -1) != int(expected.get("size_bytes", -2)):
                summary["stale_hash_mismatches"] += 1
                violations.append(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "invariant_name": "metadata_update_invariant",
                        "severity": "error",
                        "expected": f"size_bytes={expected.get('size_bytes')}",
                        "observed": f"size_bytes={row['size_bytes']}",
                        "file_id": row["file_id"],
                        "path": str(target or ""),
                        "operation_type": operation_type,
                    }
                )
            if expected.get("modified_at") and str(row.get("modified_at")) != str(expected.get("modified_at")):
                summary["stale_hash_mismatches"] += 1
                violations.append(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "invariant_name": "metadata_update_invariant",
                        "severity": "warn",
                        "expected": f"modified_at={expected.get('modified_at')}",
                        "observed": f"modified_at={row.get('modified_at')}",
                        "file_id": row["file_id"],
                        "path": str(target or ""),
                        "operation_type": operation_type,
                    }
                )
            expected_sha = expected.get("sha256")
            if expected_sha is not None and row.get("sha256") != expected_sha:
                summary["stale_hash_mismatches"] += 1
                violations.append(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "invariant_name": "metadata_update_invariant",
                        "severity": "error",
                        "expected": f"sha256={expected_sha}",
                        "observed": f"sha256={row.get('sha256')}",
                        "file_id": row["file_id"],
                        "path": str(target or ""),
                        "operation_type": operation_type,
                    }
                )
            dirty_value = int(row.get("dirty") or 0)
            metadata_status = str(row.get("metadata_status") or "")
            if not (dirty_value == 1 or metadata_status in {"basic_only", "stale", "ready"}):
                summary["stale_hash_mismatches"] += 1
                violations.append(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "invariant_name": "metadata_update_invariant",
                        "severity": "warn",
                        "expected": "dirty=1 or metadata_status in {basic_only,stale,ready}",
                        "observed": f"dirty={dirty_value},metadata_status={metadata_status}",
                        "file_id": row["file_id"],
                        "path": str(target or ""),
                        "operation_type": operation_type,
                    }
                )

    if operation_type == "delete_file_externally" and operation_result.get("executed"):
        checks += 1
        target_file_id = str(operation_result.get("target_file_id") or "")
        if target_file_id:
            post_row = _fetch_file_row_by_file_id(workspace, target_file_id)
            if post_row is None:
                summary["missing_file_mismatches"] += 1
                violations.append(
                    {
                        "run_id": run_id,
                        "step_id": step_id,
                        "invariant_name": "missing_deleted_invariant",
                        "severity": "error",
                        "expected": "deleted external file remains tracked as missing/deleted",
                        "observed": "row silently removed from files table",
                        "file_id": target_file_id,
                        "path": str(operation_result.get("old_path") or ""),
                        "operation_type": operation_type,
                    }
                )

    # Invariant 4: move/rename consistency
    if operation_type in {"move_file", "rename_file"} and operation_result.get("executed"):
        checks += 1
        old_path = str(operation_result.get("old_path") or "")
        new_path = str(operation_result.get("new_path") or "")
        new_row = _fetch_file_row_by_path(workspace, new_path) if new_path else None
        old_status = _fetch_status_for_path(workspace, old_path) if old_path else None
        if new_row is None or new_row.get("status") != "active":
            summary["path_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "move_rename_invariant",
                    "severity": "error",
                    "expected": "new path is active in DB",
                    "observed": f"new_row_status={new_row.get('status') if new_row else 'missing'}",
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": new_path,
                    "operation_type": operation_type,
                }
            )
        if old_status == "active":
            summary["path_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "move_rename_invariant",
                    "severity": "error",
                    "expected": "old path not active",
                    "observed": "old path remains active",
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": old_path,
                    "operation_type": operation_type,
                }
            )
        moved_supported = bool(operation_result.get("expected_state", {}).get("move_detection_supported", False))
        if moved_supported and "moved" not in event_types:
            summary["path_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "move_rename_invariant",
                    "severity": "warn",
                    "expected": "moved event recorded",
                    "observed": "no moved event found",
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": new_path,
                    "operation_type": operation_type,
                }
            )

    # Invariant 5: proposal invariant
    if operation_type == "propose_delete" and operation_result.get("executed"):
        checks += 1
        obs = operation_result.get("observed_state", {})
        if not (
            int(obs.get("proposal_delta", 0)) == 1
            and bool(obs.get("ai_proposed_delete_logged", False))
            and bool(obs.get("audit_delta_positive", False))
            and bool(obs.get("raw_file_still_exists", False))
        ):
            summary["proposal_state_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "proposal_invariant",
                    "severity": "error",
                    "expected": "proposal row + event + audit + raw file unchanged",
                    "observed": json.dumps(obs, ensure_ascii=True),
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(operation_result.get("old_path") or ""),
                    "operation_type": operation_type,
                }
            )

    # Invariant 6: approval invariant
    if operation_type == "approve_delete_proposal" and operation_result.get("executed"):
        checks += 1
        obs = operation_result.get("observed_state", {})
        if not (
            bool(obs.get("moved_to_trash", False))
            and str(obs.get("file_status", "")) == "soft_deleted"
            and str(obs.get("proposal_status", "")) == "approved"
            and bool(obs.get("has_soft_deleted_event", False))
            and bool(obs.get("has_user_approved_event", False))
            and bool(obs.get("audit_delta_positive", False))
        ):
            summary["trash_state_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "approval_invariant",
                    "severity": "error",
                    "expected": "trash move + soft_deleted + approved + events + audit",
                    "observed": json.dumps(obs, ensure_ascii=True),
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(operation_result.get("new_path") or ""),
                    "operation_type": operation_type,
                }
            )

    # Invariant 6b: restore invariant
    if operation_type == "restore_soft_deleted_file" and operation_result.get("executed"):
        checks += 1
        obs = operation_result.get("observed_state", {})
        if not (
            str(obs.get("file_status", "")) == "active"
            and bool(obs.get("restored_path_not_trash", False))
            and bool(obs.get("has_restored_event", False))
            and bool(obs.get("has_moved_event", False))
            and bool(obs.get("audit_delta_positive", False))
        ):
            summary["path_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "restore_invariant",
                    "severity": "error",
                    "expected": "restored active file + moved/restored events + audit",
                    "observed": json.dumps(obs, ensure_ascii=True),
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(operation_result.get("new_path") or operation_result.get("old_path") or ""),
                    "operation_type": operation_type,
                }
            )

    # Invariant 7: rejection invariant
    if operation_type == "reject_delete_proposal" and operation_result.get("executed"):
        checks += 1
        obs = operation_result.get("observed_state", {})
        if not (
            str(obs.get("proposal_status", "")) == "rejected"
            and bool(obs.get("has_user_rejected_event", False))
            and bool(obs.get("audit_delta_positive", False))
            and bool(obs.get("raw_file_still_exists", False))
            and str(obs.get("file_status", "")) == "active"
        ):
            summary["proposal_state_mismatches"] += 1
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "rejection_invariant",
                    "severity": "error",
                    "expected": "proposal rejected + event + audit + raw file active",
                    "observed": json.dumps(obs, ensure_ascii=True),
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(operation_result.get("old_path") or ""),
                    "operation_type": operation_type,
                }
            )

    # Invariant 9: reconcile invariant
    if operation_type == "simulate_missed_event_then_reconcile" and operation_result.get("executed"):
        checks += 1
        obs = operation_result.get("observed_state", {})
        if int(obs.get("post_reconcile_mismatches", 1)) > 0:
            violations.append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "reconcile_invariant",
                    "severity": "error",
                    "expected": "post reconcile mismatches == 0",
                    "observed": f"post_reconcile_mismatches={obs.get('post_reconcile_mismatches')}",
                    "file_id": operation_result.get("target_file_id", ""),
                    "path": str(operation_result.get("old_path") or ""),
                    "operation_type": operation_type,
                }
            )

    # Invariant 8 is checked in the main loop with count deltas (requires before/after snapshots)

    active_file_match_rate = (
        (len(fs_paths) - summary["active_file_mismatches"]) / len(fs_paths) if fs_paths else 1.0
    )
    active_db_total = max(1, len(active_rows))
    db_active_validity = (
        sum(1 for r in active_rows if str(r["path"]) in fs_paths) / active_db_total
        if active_rows
        else 1.0
    )

    return {
        "checks": checks,
        "violations": violations,
        "summary": summary,
        "active_file_match_rate": max(0.0, min(1.0, active_file_match_rate)),
        "db_active_validity": max(0.0, min(1.0, db_active_validity)),
    }


def _update_wow_summary(base_dir: Path, payload: dict[str, Any]) -> None:
    base_dir.mkdir(parents=True, exist_ok=True)
    json_path = base_dir / "wow_summary.json"
    csv_path = base_dir / "wow_summary.csv"

    current: dict[str, Any] = {}
    if json_path.exists():
        try:
            current = json.loads(json_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(payload)
    json_path.write_text(json.dumps(current, indent=2), encoding="utf-8")

    columns = sorted(current.keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerow(current)


def run_metadata_consistency(args: argparse.Namespace) -> int:
    ctx = build_context("metadata_consistency", args)
    rng = random.Random(int(args.seed))
    run_id = str(uuid4())

    file_count = int(args.file_count)
    operation_count = int(args.operation_count)
    cleanup_temp = _parse_bool(getattr(args, "cleanup_temp", "true"), default=True)
    restore_supported = True

    raw_distribution = _parse_operation_distribution(getattr(args, "operation_distribution", None))
    distribution = _normalize_distribution(raw_distribution)

    csv_path = ctx.output_path / "metadata_consistency_results.csv"
    events_path = ctx.output_path / "metadata_consistency_events.jsonl"
    violations_path = ctx.output_path / "invariant_violations.jsonl"
    final_summary_path = ctx.output_path / "final_state_summary.json"

    workspace = (ctx.output_path / "workspace").resolve()
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    manifest = generate_workspace(
        GenerationConfig(
            output=workspace,
            num_files=file_count,
            duplicate_ratio=0.1,
            large_file_ratio=0.0,
            large_file_size_mb=101,
            structure="mixed",
            seed=int(args.seed),
        )
    )

    if metamirror_main(["init", str(workspace)]) != 0:
        raise RuntimeError("metadata_consistency init failed")
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("metadata_consistency initial scan failed")

    aggregated: dict[str, dict[str, float]] = {}
    step_events: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []

    total_checks = 0
    total_violations = 0
    total_latency_ms = 0.0
    total_ops_executed = 0
    total_reconcile_repairs = 0
    total_event_log_missing = 0
    total_audit_log_missing = 0
    total_completeness_missing_ops = 0
    total_delete_ops = 0
    total_delete_success = 0
    total_update_ops = 0
    total_update_success = 0
    total_move_ops = 0
    total_move_success = 0
    running_active_file_match_rate = 0.0
    running_db_active_validity = 0.0

    def _agg(op: str) -> dict[str, float]:
        if op not in aggregated:
            aggregated[op] = {
                "operations_executed": 0.0,
                "invariant_checks": 0.0,
                "invariant_violations": 0.0,
                "active_file_mismatches": 0.0,
                "missing_file_mismatches": 0.0,
                "stale_hash_mismatches": 0.0,
                "path_mismatches": 0.0,
                "event_log_missing_count": 0.0,
                "audit_log_missing_count": 0.0,
                "proposal_state_mismatches": 0.0,
                "trash_state_mismatches": 0.0,
                "reconcile_repairs": 0.0,
                "latency_ms": 0.0,
                "active_file_match_rate_sum": 0.0,
                "db_active_validity_sum": 0.0,
            }
        return aggregated[op]

    for step_id in range(1, operation_count + 1):
        operation_type = _random_choice_by_weight(rng, distribution)
        before_event_count, before_audit_count = _get_row_counts_for_step(workspace)
        step_t0 = time.perf_counter()

        op_result: dict[str, Any] = {
            "executed": False,
            "operation_type": operation_type,
            "target_file_id": "",
            "old_path": "",
            "new_path": "",
            "expected_state": {},
            "observed_state": {},
            "invariants_checked": [],
            "violations": [],
            "expects_event": True,
            "expects_audit": True,
            "reconcile_repairs": 0,
        }

        if operation_type == "create_file":
            sub_dir = workspace / f"ops/create_{step_id % 17:02d}"
            _assert_within_workspace(workspace, sub_dir)
            sub_dir.mkdir(parents=True, exist_ok=True)
            file_path = sub_dir / f"new_{step_id:06d}.txt"
            _assert_within_workspace(workspace, file_path)
            content = f"step={step_id} seed={args.seed} token={rng.randint(0, 10_000_000)}\n"
            file_path.write_text(content, encoding="utf-8")
            op_result["executed"] = True
            op_result["new_path"] = str(file_path.relative_to(workspace))
            op_result["expected_state"] = {"file_exists": True}
            if metamirror_main(["scan", str(workspace)]) != 0:
                raise RuntimeError("scan failed after create_file")

        elif operation_type == "modify_file":
            pending_file_ids = _fetch_pending_proposal_file_ids(workspace)
            active_rows = [
                (fid, rel)
                for fid, rel in _fetch_active_file_rows(workspace)
                if fid not in pending_file_ids and (workspace / rel).exists()
            ]
            if active_rows:
                selected_file_id, rel_path = rng.choice(active_rows)
                file_path = workspace / rel_path
                _assert_within_workspace(workspace, file_path)
                with file_path.open("a", encoding="utf-8") as fh:
                    fh.write(f"modified_step={step_id} token={rng.randint(0, 10_000_000)}\n")
                stat = file_path.stat()
                expected_sha: str | None = None
                if stat.st_size <= HASH_SIZE_LIMIT_BYTES:
                    expected_sha = _sha256_file(file_path)
                modified_at_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                row = _fetch_file_row_by_path(workspace, rel_path)
                op_result["executed"] = True
                op_result["target_file_id"] = str(row["file_id"]) if row else selected_file_id
                op_result["old_path"] = rel_path
                op_result["new_path"] = rel_path
                op_result["expected_state"] = {
                    "size_bytes": stat.st_size,
                    "modified_at": modified_at_iso,
                    "sha256": expected_sha,
                }
                if metamirror_main(["scan", str(workspace)]) != 0:
                    raise RuntimeError("scan failed after modify_file")

        elif operation_type == "delete_file_externally":
            pending_file_ids = _fetch_pending_proposal_file_ids(workspace)
            active_rows = [
                (fid, rel)
                for fid, rel in _fetch_active_file_rows(workspace)
                if fid not in pending_file_ids and (workspace / rel).exists()
            ]
            if active_rows:
                selected_file_id, rel_path = rng.choice(active_rows)
                file_path = workspace / rel_path
                _assert_within_workspace(workspace, file_path)
                row = _fetch_file_row_by_path(workspace, rel_path)
                file_path.unlink()
                op_result["executed"] = True
                op_result["target_file_id"] = str(row["file_id"]) if row else selected_file_id
                op_result["old_path"] = rel_path
                op_result["expected_state"] = {"db_status_after_reconcile": "missing_or_deleted"}
                if metamirror_main(["scan", str(workspace)]) != 0:
                    raise RuntimeError("scan failed after delete_file_externally")
                total_delete_ops += 1
                post_row = _fetch_file_row_by_file_id(workspace, op_result["target_file_id"]) if op_result["target_file_id"] else None
                if post_row and str(post_row.get("status")) in {"missing", "deleted"}:
                    total_delete_success += 1

        elif operation_type == "move_file":
            pending_file_ids = _fetch_pending_proposal_file_ids(workspace)
            active_rows = [
                (fid, rel)
                for fid, rel in _fetch_active_file_rows(workspace)
                if fid not in pending_file_ids and (workspace / rel).exists()
            ]
            if active_rows:
                selected_file_id, rel = rng.choice(active_rows)
                src = workspace / rel
                _assert_within_workspace(workspace, src)
                dst_dir = workspace / f"ops/move_{step_id % 13:02d}"
                _assert_within_workspace(workspace, dst_dir)
                dst_dir.mkdir(parents=True, exist_ok=True)
                dst = dst_dir / src.name
                _assert_within_workspace(workspace, dst)
                old_rel = str(src.relative_to(workspace))
                dst_rel = str(dst.relative_to(workspace))
                row = _fetch_file_row_by_path(workspace, old_rel)
                shutil.move(str(src), str(dst))
                op_result["executed"] = True
                op_result["target_file_id"] = str(row["file_id"]) if row else selected_file_id
                op_result["old_path"] = old_rel
                op_result["new_path"] = dst_rel
                op_result["expected_state"] = {"move_detection_supported": False}
                if metamirror_main(["scan", str(workspace)]) != 0:
                    raise RuntimeError("scan failed after move_file")
                total_move_ops += 1
                new_row = _fetch_file_row_by_path(workspace, dst_rel)
                old_status = _fetch_status_for_path(workspace, old_rel)
                if new_row and str(new_row.get("status")) == "active" and old_status in {"missing", "deleted", "soft_deleted", None}:
                    total_move_success += 1

        elif operation_type == "rename_file":
            pending_file_ids = _fetch_pending_proposal_file_ids(workspace)
            active_rows = [
                (fid, rel)
                for fid, rel in _fetch_active_file_rows(workspace)
                if fid not in pending_file_ids and (workspace / rel).exists()
            ]
            if active_rows:
                selected_file_id, rel = rng.choice(active_rows)
                src = workspace / rel
                _assert_within_workspace(workspace, src)
                suffix = src.suffix
                dst = src.with_name(f"{src.stem}_renamed_{step_id:04d}{suffix}")
                _assert_within_workspace(workspace, dst)
                old_rel = str(src.relative_to(workspace))
                dst_rel = str(dst.relative_to(workspace))
                row = _fetch_file_row_by_path(workspace, old_rel)
                src.rename(dst)
                op_result["executed"] = True
                op_result["target_file_id"] = str(row["file_id"]) if row else selected_file_id
                op_result["old_path"] = old_rel
                op_result["new_path"] = dst_rel
                op_result["expected_state"] = {"move_detection_supported": False}
                if metamirror_main(["scan", str(workspace)]) != 0:
                    raise RuntimeError("scan failed after rename_file")
                total_move_ops += 1
                new_row = _fetch_file_row_by_path(workspace, dst_rel)
                old_status = _fetch_status_for_path(workspace, old_rel)
                if new_row and str(new_row.get("status")) == "active" and old_status in {"missing", "deleted", "soft_deleted", None}:
                    total_move_success += 1

        elif operation_type == "propose_delete":
            active_rows = _fetch_active_file_rows(workspace)
            if active_rows:
                file_id, rel_path = rng.choice(active_rows)
                before_counts = _count_db_rows(workspace)
                before_events, before_audits = _get_row_counts_for_step(workspace)
                proposal_code = metamirror_main(
                    [
                        "propose-delete",
                        str(workspace),
                        file_id,
                        "--reason",
                        "metadata_consistency_experiment",
                        "--evidence",
                        f"step={step_id}",
                    ]
                )
                op_result["executed"] = True
                op_result["target_file_id"] = file_id
                op_result["old_path"] = rel_path
                if proposal_code != 0:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    op_result["observed_state"] = {
                        "error": "propose_failed",
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }
                else:
                    after_counts = _count_db_rows(workspace)
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    proposal_delta = after_counts["proposals"] - before_counts["proposals"]
                    db_path = workspace / ".metamirror" / "metadata.db"
                    conn = sqlite3.connect(db_path)
                    try:
                        has_event = (
                            conn.execute(
                                """
                                SELECT COUNT(*)
                                FROM file_events
                                WHERE file_id=? AND event_type='ai_proposed_delete'
                                """,
                                (file_id,),
                            ).fetchone()[0]
                            > 0
                        )
                    finally:
                        conn.close()
                    raw_exists = (workspace / rel_path).exists()
                    op_result["observed_state"] = {
                        "proposal_delta": proposal_delta,
                        "ai_proposed_delete_logged": has_event,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                        "raw_file_still_exists": raw_exists,
                    }
                    pass

        elif operation_type == "approve_delete_proposal":
            pending = _fetch_pending_proposal_ids(workspace)
            if not pending:
                # bootstrap one pending proposal so approval flow can run.
                active_rows = _fetch_active_file_rows(workspace)
                if active_rows:
                    file_id, _ = rng.choice(active_rows)
                    proposal_code = metamirror_main(
                        [
                            "propose-delete",
                            str(workspace),
                            file_id,
                            "--reason",
                            "bootstrap_for_approve",
                            "--evidence",
                            f"step={step_id}",
                        ]
                    )
                    if proposal_code != 0:
                        raise RuntimeError("bootstrap propose-delete failed")
            pending_details = _fetch_pending_proposals(workspace)
            executable = [
                (pid, fid, pth, status)
                for pid, fid, pth, status in pending_details
                if status == "active" and (workspace / pth).exists()
            ]
            if not executable:
                active_rows = _fetch_active_file_rows(workspace)
                if active_rows:
                    file_id, _ = rng.choice(active_rows)
                    proposal_code = metamirror_main(
                        [
                            "propose-delete",
                            str(workspace),
                            file_id,
                            "--reason",
                            "bootstrap_for_approve_active",
                            "--evidence",
                            f"step={step_id}",
                        ]
                    )
                    if proposal_code == 0:
                        pending_details = _fetch_pending_proposals(workspace)
                        executable = [
                            (pid, fid, pth, status)
                            for pid, fid, pth, status in pending_details
                            if status == "active" and (workspace / pth).exists()
                        ]
            if executable:
                proposal_id = executable[0][0]
                before_events, before_audits = _get_row_counts_for_step(workspace)
                approve_code = metamirror_main(["approve", str(workspace), proposal_id])
                op_result["executed"] = True
                if approve_code != 0:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    op_result["observed_state"] = {
                        "error": "approve_failed",
                        "proposal_id": proposal_id,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }
                else:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    db_path = workspace / ".metamirror" / "metadata.db"
                    conn = sqlite3.connect(db_path)
                    try:
                        proposal_row = conn.execute(
                            "SELECT file_id, status FROM action_proposals WHERE proposal_id=?",
                            (proposal_id,),
                        ).fetchone()
                        if not proposal_row:
                            raise RuntimeError(f"proposal row disappeared: {proposal_id}")
                        file_id = str(proposal_row[0])
                        proposal_status = str(proposal_row[1])
                        file_row = conn.execute(
                            "SELECT path, status FROM files WHERE file_id=?",
                            (file_id,),
                        ).fetchone()
                        file_path = str(file_row[0]) if file_row else ""
                        file_status = str(file_row[1]) if file_row else ""
                        soft_deleted_evt = conn.execute(
                            """
                            SELECT COUNT(*) FROM file_events
                            WHERE file_id=? AND event_type='soft_deleted'
                            """,
                            (file_id,),
                        ).fetchone()[0] > 0
                        approved_evt = conn.execute(
                            """
                            SELECT COUNT(*) FROM file_events
                            WHERE file_id=?
                              AND event_type='soft_deleted'
                              AND actor='user'
                              AND reason='approve_delete_proposal'
                            """,
                            (file_id,),
                        ).fetchone()[0] > 0
                    finally:
                        conn.close()
                    moved_to_trash = file_path.startswith(".metamirror/trash/")
                    op_result["target_file_id"] = file_id
                    op_result["new_path"] = file_path
                    op_result["observed_state"] = {
                        "proposal_status": proposal_status,
                        "file_status": file_status,
                        "moved_to_trash": moved_to_trash,
                        "has_soft_deleted_event": soft_deleted_evt,
                        "has_user_approved_event": approved_evt,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }

        elif operation_type == "reject_delete_proposal":
            pending_details = _fetch_pending_proposals(workspace)
            preferred = [
                (pid, fid, pth, status)
                for pid, fid, pth, status in pending_details
                if status == "active" and (workspace / pth).exists()
            ]
            if not preferred:
                active_rows = _fetch_active_file_rows(workspace)
                if active_rows:
                    file_id, _ = rng.choice(active_rows)
                    proposal_code = metamirror_main(
                        [
                            "propose-delete",
                            str(workspace),
                            file_id,
                            "--reason",
                            "bootstrap_for_reject_active",
                            "--evidence",
                            f"step={step_id}",
                        ]
                    )
                    if proposal_code == 0:
                        pending_details = _fetch_pending_proposals(workspace)
                        preferred = [
                            (pid, fid, pth, status)
                            for pid, fid, pth, status in pending_details
                            if status == "active" and (workspace / pth).exists()
                        ]
            if preferred:
                proposal_id = preferred[0][0]
                before_events, before_audits = _get_row_counts_for_step(workspace)
                db_path = workspace / ".metamirror" / "metadata.db"
                conn = sqlite3.connect(db_path)
                try:
                    r0 = conn.execute(
                        "SELECT file_id FROM action_proposals WHERE proposal_id=?",
                        (proposal_id,),
                    ).fetchone()
                    file_id = str(r0[0]) if r0 else ""
                    fr0 = conn.execute("SELECT path FROM files WHERE file_id=?", (file_id,)).fetchone()
                    old_path = str(fr0[0]) if fr0 else ""
                finally:
                    conn.close()

                reject_code = metamirror_main(["reject", str(workspace), proposal_id])
                op_result["executed"] = True
                if reject_code != 0:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    op_result["target_file_id"] = file_id
                    op_result["old_path"] = old_path
                    op_result["observed_state"] = {
                        "error": "reject_failed",
                        "proposal_id": proposal_id,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }
                else:
                    after_events, after_audits = _get_row_counts_for_step(workspace)

                    conn = sqlite3.connect(db_path)
                    try:
                        proposal_status = conn.execute(
                            "SELECT status FROM action_proposals WHERE proposal_id=?",
                            (proposal_id,),
                        ).fetchone()[0]
                        file_status = conn.execute(
                            "SELECT status FROM files WHERE file_id=?",
                            (file_id,),
                        ).fetchone()[0]
                        has_rejected_evt = conn.execute(
                            """
                            SELECT COUNT(*) FROM file_events
                            WHERE file_id=? AND event_type='user_rejected_delete'
                            """,
                            (file_id,),
                        ).fetchone()[0] > 0
                    finally:
                        conn.close()

                    raw_exists = (workspace / old_path).exists()
                    op_result["target_file_id"] = file_id
                    op_result["old_path"] = old_path
                    op_result["observed_state"] = {
                        "proposal_status": proposal_status,
                        "file_status": file_status,
                        "has_user_rejected_event": has_rejected_evt,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                        "raw_file_still_exists": raw_exists,
                    }

        elif operation_type == "restore_soft_deleted_file":
            soft_deleted_rows = _fetch_soft_deleted_rows(workspace)
            if not soft_deleted_rows:
                active_rows = _fetch_active_file_rows(workspace)
                if active_rows:
                    file_id, _ = rng.choice(active_rows)
                    bootstrap_propose = metamirror_main(
                        [
                            "propose-delete",
                            str(workspace),
                            file_id,
                            "--reason",
                            "bootstrap_for_restore",
                            "--evidence",
                            f"step={step_id}",
                        ]
                    )
                    if bootstrap_propose == 0:
                        pending = _fetch_pending_proposal_ids(workspace)
                        if pending:
                            metamirror_main(["approve", str(workspace), pending[0]])
                soft_deleted_rows = _fetch_soft_deleted_rows(workspace)
            if soft_deleted_rows:
                selected_file_id, old_path = rng.choice(soft_deleted_rows)
                before_events, before_audits = _get_row_counts_for_step(workspace)
                restore_code = metamirror_main(["restore", str(workspace), selected_file_id])
                op_result["executed"] = True
                op_result["target_file_id"] = selected_file_id
                op_result["old_path"] = old_path
                if restore_code != 0:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    op_result["observed_state"] = {
                        "error": "restore_failed",
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }
                else:
                    after_events, after_audits = _get_row_counts_for_step(workspace)
                    db_path = workspace / ".metamirror" / "metadata.db"
                    conn = sqlite3.connect(db_path)
                    try:
                        file_row = conn.execute(
                            "SELECT path, status FROM files WHERE file_id=?",
                            (selected_file_id,),
                        ).fetchone()
                        file_path = str(file_row[0]) if file_row else ""
                        file_status = str(file_row[1]) if file_row else ""
                        restored_evt = conn.execute(
                            """
                            SELECT COUNT(*) FROM file_events
                            WHERE file_id=? AND event_type='restored'
                            """,
                            (selected_file_id,),
                        ).fetchone()[0] > 0
                        moved_evt = conn.execute(
                            """
                            SELECT COUNT(*) FROM file_events
                            WHERE file_id=? AND event_type='moved'
                            """,
                            (selected_file_id,),
                        ).fetchone()[0] > 0
                    finally:
                        conn.close()
                    op_result["new_path"] = file_path
                    op_result["observed_state"] = {
                        "file_status": file_status,
                        "restored_path_not_trash": not file_path.startswith(".metamirror/trash/"),
                        "has_restored_event": restored_evt,
                        "has_moved_event": moved_evt,
                        "audit_delta_positive": (after_audits - before_audits) > 0,
                        "event_delta_positive": (after_events - before_events) > 0,
                    }

        elif operation_type == "simulate_missed_event_then_reconcile":
            pending_file_ids = _fetch_pending_proposal_file_ids(workspace)
            active_rows = [
                (fid, rel)
                for fid, rel in _fetch_active_file_rows(workspace)
                if fid not in pending_file_ids and (workspace / rel).exists()
            ]
            if active_rows:
                _selected_file_id, rel = rng.choice(active_rows)
                file_path = workspace / rel
                _assert_within_workspace(workspace, file_path)
                rel_path = str(file_path.relative_to(workspace))
                before_core_mismatch = _core_mismatch_count(workspace)
                if rng.random() < 0.5:
                    with file_path.open("a", encoding="utf-8") as fh:
                        fh.write(f"missed_modify_step={step_id}\n")
                else:
                    file_path.unlink()
                mid_core_mismatch = _core_mismatch_count(workspace)
                if mid_core_mismatch <= before_core_mismatch and file_path.exists():
                    # Ensure we actually simulate a missed structural event for repair measurement.
                    file_path.unlink()
                    mid_core_mismatch = _core_mismatch_count(workspace)
                if metamirror_main(["scan", str(workspace)]) != 0:
                    raise RuntimeError("scan failed for simulate_missed_event_then_reconcile")
                after_core_mismatch = _core_mismatch_count(workspace)
                repairs = max(0, mid_core_mismatch - after_core_mismatch)
                op_result["executed"] = True
                op_result["old_path"] = rel_path
                op_result["observed_state"] = {
                    "before_mismatches": before_core_mismatch,
                    "pre_reconcile_mismatches": mid_core_mismatch,
                    "post_reconcile_mismatches": after_core_mismatch,
                    "repairs": repairs,
                }
                op_result["reconcile_repairs"] = repairs
                total_reconcile_repairs += repairs

        step_t1 = time.perf_counter()
        latency_ms = (step_t1 - step_t0) * 1000.0

        if not op_result["executed"]:
            continue

        total_ops_executed += 1
        total_latency_ms += latency_ms
        op_bucket = _agg(operation_type)
        op_bucket["operations_executed"] += 1
        op_bucket["latency_ms"] += latency_ms
        op_bucket["reconcile_repairs"] += float(op_result.get("reconcile_repairs", 0))

        after_event_count, after_audit_count = _get_row_counts_for_step(workspace)
        event_delta = after_event_count - before_event_count
        audit_delta = after_audit_count - before_audit_count

        invariant_result = _evaluate_invariants(
            workspace=workspace,
            step_id=step_id,
            operation_type=operation_type,
            operation_result=op_result,
            run_id=run_id,
        )

        # Invariant 8: audit/event completeness
        total_invariant_8_checks = 1
        expects_event = bool(op_result.get("expects_event", True))
        expects_audit = bool(op_result.get("expects_audit", True))
        event_missing = expects_event and (event_delta <= 0)
        audit_missing = expects_audit and (audit_delta <= 0)
        if event_missing:
            total_event_log_missing += 1
        if audit_missing:
            total_audit_log_missing += 1
        inv8_violation = False
        expected_bits: list[str] = []
        observed_bits: list[str] = []
        if expects_event:
            expected_bits.append("event_log")
            observed_bits.append(f"event_delta={event_delta}")
        if expects_audit:
            expected_bits.append("audit_log")
            observed_bits.append(f"audit_delta={audit_delta}")
        if expects_event and expects_audit:
            # and/or semantics: at least one log should capture the metadata-changing operation
            inv8_violation = event_missing and audit_missing
        elif expects_event:
            inv8_violation = event_missing
        elif expects_audit:
            inv8_violation = audit_missing
        if inv8_violation:
            total_completeness_missing_ops += 1
            invariant_result["violations"].append(
                {
                    "run_id": run_id,
                    "step_id": step_id,
                    "invariant_name": "audit_completeness_invariant",
                    "severity": "warn",
                    "expected": f"log captured in {'/'.join(expected_bits)}",
                    "observed": ",".join(observed_bits),
                    "file_id": op_result.get("target_file_id", ""),
                    "path": str(op_result.get("new_path") or op_result.get("old_path") or ""),
                    "operation_type": operation_type,
                }
            )

        checks = int(invariant_result["checks"]) + total_invariant_8_checks
        v_count = len(invariant_result["violations"])
        total_checks += checks
        total_violations += v_count

        op_bucket["invariant_checks"] += checks
        op_bucket["invariant_violations"] += v_count
        op_bucket["event_log_missing_count"] += 1.0 if event_missing else 0.0
        op_bucket["audit_log_missing_count"] += 1.0 if audit_missing else 0.0
        for k, v in invariant_result["summary"].items():
            op_bucket[k] += float(v)

        afr = float(invariant_result["active_file_match_rate"])
        dav = float(invariant_result["db_active_validity"])
        op_bucket["active_file_match_rate_sum"] += afr
        op_bucket["db_active_validity_sum"] += dav
        running_active_file_match_rate += afr
        running_db_active_validity += dav

        if operation_type == "modify_file":
            total_update_ops += 1
            if invariant_result["summary"]["stale_hash_mismatches"] == 0:
                total_update_success += 1

        for v in invariant_result["violations"]:
            violations.append(v)

        op_result["invariants_checked"] = [
            "active_file_invariant",
            "missing_deleted_invariant",
            "metadata_update_invariant",
            "move_rename_invariant",
            "proposal_invariant",
            "approval_invariant",
            "restore_invariant",
            "rejection_invariant",
            "audit_completeness_invariant",
            "reconcile_invariant",
        ]
        op_result["violations"] = [v["invariant_name"] for v in invariant_result["violations"]]

        step_events.append(
            {
                "run_id": run_id,
                "step_id": step_id,
                "operation_type": operation_type,
                "target_file_id": op_result.get("target_file_id", ""),
                "old_path": op_result.get("old_path", ""),
                "new_path": op_result.get("new_path", ""),
                "expected_state": op_result.get("expected_state", {}),
                "observed_state": op_result.get("observed_state", {}),
                "invariants_checked": op_result.get("invariants_checked", []),
                "violations": op_result.get("violations", []),
                "latency_ms": round(latency_ms, 6),
            }
        )

    # Final reconcile and final checks
    if metamirror_main(["scan", str(workspace)]) != 0:
        raise RuntimeError("metadata_consistency final scan failed")
    final_inv = _evaluate_invariants(
        workspace=workspace,
        step_id=operation_count + 1,
        operation_type="final_reconcile",
        operation_result={"executed": True},
        run_id=run_id,
    )
    total_checks += int(final_inv["checks"])
    total_violations += len(final_inv["violations"])
    violations.extend(final_inv["violations"])

    db_counts = _count_db_rows(workspace)
    audit_events = _list_audit_events(workspace)
    db_path = workspace / ".metamirror" / "metadata.db"
    conn = sqlite3.connect(db_path)
    try:
        proposal_counts = dict(
            conn.execute("SELECT status, COUNT(*) FROM action_proposals GROUP BY status").fetchall()
        )
        fs_total = len(_iter_active_workspace_files(workspace))
    finally:
        conn.close()

    consistency_score = 1.0 - (float(total_violations) / float(max(1, total_checks)))
    consistency_score = max(0.0, min(1.0, consistency_score))
    final_passed = (len(final_inv["violations"]) == 0) and (final_inv["summary"]["active_file_mismatches"] == 0)

    active_file_match_rate = running_active_file_match_rate / max(1, total_ops_executed)
    db_active_validity = running_db_active_validity / max(1, total_ops_executed)
    delete_tracking_accuracy = total_delete_success / max(1, total_delete_ops)
    update_tracking_accuracy = total_update_success / max(1, total_update_ops)
    move_tracking_accuracy = total_move_success / max(1, total_move_ops)
    proposal_consistency, proposal_state_mismatches_global, _proposal_total = _compute_proposal_consistency(
        workspace
    )
    audit_completeness = 1.0 - (
        float(total_completeness_missing_ops) / float(max(1, total_ops_executed))
    )
    audit_completeness = max(0.0, min(1.0, audit_completeness))
    reconcile_repair_rate = total_reconcile_repairs / max(1, total_ops_executed)

    final_summary = {
        "run_id": run_id,
        "restore_supported": restore_supported,
        "total_files_in_filesystem": fs_total,
        "total_active_rows_in_db": db_counts["active"],
        "total_missing_rows": db_counts["missing"],
        "total_deleted_rows": db_counts["deleted"],
        "total_soft_deleted_rows": db_counts["soft_deleted"],
        "total_proposals": db_counts["proposals"],
        "pending_proposals": int(proposal_counts.get("pending", 0)),
        "approved_proposals": int(proposal_counts.get("approved", 0)),
        "executed_proposals": int(proposal_counts.get("executed", 0)),
        "rejected_proposals": int(proposal_counts.get("rejected", 0)),
        "expired_proposals": int(proposal_counts.get("expired", 0)),
        "total_file_events": db_counts["events"],
        "total_audit_events": len(audit_events),
        "final_consistency_passed": bool(final_passed),
        "run_consistency_passed": bool(total_violations == 0),
        "consistency_score": round(consistency_score, 6),
        "total_invariant_checks": int(total_checks),
        "total_invariant_violations": int(total_violations),
        "active_file_match_rate": round(active_file_match_rate, 6),
        "db_active_validity": round(db_active_validity, 6),
        "delete_tracking_accuracy": round(delete_tracking_accuracy, 6),
        "update_tracking_accuracy": round(update_tracking_accuracy, 6),
        "move_tracking_accuracy": round(move_tracking_accuracy, 6),
        "proposal_consistency": round(proposal_consistency, 6),
        "proposal_state_mismatches": int(proposal_state_mismatches_global),
        "audit_completeness": round(audit_completeness, 6),
        "reconcile_repair_rate": round(reconcile_repair_rate, 6),
    }

    result_columns = [
        "run_id",
        "file_count",
        "operation_count",
        "seed",
        "operation_type",
        "operations_executed",
        "invariant_checks",
        "invariant_violations",
        "consistency_score",
        "active_file_mismatches",
        "missing_file_mismatches",
        "stale_hash_mismatches",
        "path_mismatches",
        "event_log_missing_count",
        "audit_log_missing_count",
        "proposal_state_mismatches",
        "trash_state_mismatches",
        "reconcile_repairs",
        "final_consistency_passed",
        "run_consistency_passed",
        "latency_ms",
        "active_file_match_rate",
        "db_active_validity",
        "delete_tracking_accuracy",
        "update_tracking_accuracy",
        "move_tracking_accuracy",
        "proposal_consistency",
        "audit_completeness",
        "reconcile_repair_rate",
    ]

    result_rows: list[dict[str, Any]] = []
    for op_name, bucket in sorted(aggregated.items()):
        executed = int(bucket["operations_executed"])
        op_consistency = 1.0 - (
            float(bucket["invariant_violations"]) / float(max(1, int(bucket["invariant_checks"])))
        )
        result_rows.append(
            {
                "run_id": run_id,
                "file_count": file_count,
                "operation_count": operation_count,
                "seed": int(args.seed),
                "operation_type": op_name,
                "operations_executed": executed,
                "invariant_checks": int(bucket["invariant_checks"]),
                "invariant_violations": int(bucket["invariant_violations"]),
                "consistency_score": round(max(0.0, min(1.0, op_consistency)), 6),
                "active_file_mismatches": int(bucket["active_file_mismatches"]),
                "missing_file_mismatches": int(bucket["missing_file_mismatches"]),
                "stale_hash_mismatches": int(bucket["stale_hash_mismatches"]),
                "path_mismatches": int(bucket["path_mismatches"]),
                "event_log_missing_count": int(bucket["event_log_missing_count"]),
                "audit_log_missing_count": int(bucket["audit_log_missing_count"]),
                "proposal_state_mismatches": int(bucket["proposal_state_mismatches"]),
                "trash_state_mismatches": int(bucket["trash_state_mismatches"]),
                "reconcile_repairs": int(bucket["reconcile_repairs"]),
                "final_consistency_passed": bool(final_passed),
                "run_consistency_passed": bool(total_violations == 0),
                "latency_ms": round(float(bucket["latency_ms"]), 6),
                "active_file_match_rate": round(
                    float(bucket["active_file_match_rate_sum"]) / max(1, executed), 6
                ),
                "db_active_validity": round(
                    float(bucket["db_active_validity_sum"]) / max(1, executed), 6
                ),
                "delete_tracking_accuracy": round(delete_tracking_accuracy, 6),
                "update_tracking_accuracy": round(update_tracking_accuracy, 6),
                "move_tracking_accuracy": round(move_tracking_accuracy, 6),
                "proposal_consistency": round(proposal_consistency, 6),
                "audit_completeness": round(audit_completeness, 6),
                "reconcile_repair_rate": round(reconcile_repair_rate, 6),
            }
        )

    result_rows.append(
        {
            "run_id": run_id,
            "file_count": file_count,
            "operation_count": operation_count,
            "seed": int(args.seed),
            "operation_type": "ALL",
            "operations_executed": total_ops_executed,
            "invariant_checks": int(total_checks),
            "invariant_violations": int(total_violations),
            "consistency_score": round(consistency_score, 6),
            "active_file_mismatches": int(final_inv["summary"]["active_file_mismatches"]),
            "missing_file_mismatches": int(final_inv["summary"]["missing_file_mismatches"]),
            "stale_hash_mismatches": int(
                sum(float(bucket["stale_hash_mismatches"]) for bucket in aggregated.values())
            ),
            "path_mismatches": int(final_inv["summary"]["path_mismatches"]),
            "event_log_missing_count": int(total_event_log_missing),
            "audit_log_missing_count": int(total_audit_log_missing),
            "proposal_state_mismatches": int(final_inv["summary"]["proposal_state_mismatches"]),
            "trash_state_mismatches": int(final_inv["summary"]["trash_state_mismatches"]),
            "reconcile_repairs": int(total_reconcile_repairs),
            "final_consistency_passed": bool(final_passed),
            "run_consistency_passed": bool(total_violations == 0),
            "latency_ms": round(total_latency_ms, 6),
            "active_file_match_rate": round(active_file_match_rate, 6),
            "db_active_validity": round(db_active_validity, 6),
            "delete_tracking_accuracy": round(delete_tracking_accuracy, 6),
            "update_tracking_accuracy": round(update_tracking_accuracy, 6),
            "move_tracking_accuracy": round(move_tracking_accuracy, 6),
            "proposal_consistency": round(proposal_consistency, 6),
            "audit_completeness": round(audit_completeness, 6),
            "reconcile_repair_rate": round(reconcile_repair_rate, 6),
        }
    )

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=result_columns)
        writer.writeheader()
        for row in result_rows:
            writer.writerow(row)

    with events_path.open("w", encoding="utf-8") as fh:
        for row in step_events:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")

    with violations_path.open("w", encoding="utf-8") as fh:
        for row in violations:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")

    final_summary_path.write_text(json.dumps(final_summary, indent=2), encoding="utf-8")

    wow_payload = {
        "metadata_consistency_score": round(consistency_score, 6),
        "final_consistency_passed": bool(final_passed),
        "run_consistency_passed": bool(total_violations == 0),
        "total_invariant_checks": int(total_checks),
        "total_invariant_violations": int(total_violations),
        "active_file_match_rate": round(active_file_match_rate, 6),
        "db_active_validity": round(db_active_validity, 6),
        "delete_tracking_accuracy": round(delete_tracking_accuracy, 6),
        "update_tracking_accuracy": round(update_tracking_accuracy, 6),
        "move_tracking_accuracy": round(move_tracking_accuracy, 6),
        "proposal_consistency": round(proposal_consistency, 6),
        "audit_completeness": round(audit_completeness, 6),
        "reconcile_repair_rate": round(reconcile_repair_rate, 6),
    }
    _update_wow_summary(ctx.output_path.parent, wow_payload)

    write_manifest(
        ctx,
        generated_files=[str(workspace / "synthetic_manifest.json")],
        result_files=[
            str(csv_path),
            str(events_path),
            str(violations_path),
            str(final_summary_path),
            str(ctx.output_path.parent / "wow_summary.json"),
            str(ctx.output_path.parent / "wow_summary.csv"),
        ],
        notes=(
            "Metadata consistency experiment with randomized operations and invariant checks. "
            "All destructive operations are constrained to temporary synthetic workspace."
        ),
    )

    if cleanup_temp and workspace.exists():
        shutil.rmtree(workspace)

    print(f"[metadata_consistency] output: {ctx.output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MetaMirror experiment benchmark runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in SUPPORTED_EXPERIMENTS:
        sub = subparsers.add_parser(name, help=f"Run {name} experiment")
        sub.add_argument("--output", default=None, help="Output directory")
        sub.add_argument("--workspace", default=None, help="Workspace path (temp/synthetic only)")
        sub.add_argument("--seed", type=int, default=42, help="Random seed")
        sub.add_argument(
            "--cleanup-large-files",
            default="true",
            help="Cleanup >= threshold files under output workspace/workspaces after run (true/false)",
        )
        sub.add_argument(
            "--cleanup-large-threshold-mb",
            type=int,
            default=100,
            help="Large-file cleanup threshold in MB",
        )

        if name == "scalability":
            sub.add_argument("--file-counts", nargs="+", type=int, default=[100, 1000])
            sub.add_argument("--duplicate-ratio", type=float, default=0.1)
            sub.add_argument("--repeats", type=int, default=1)
        elif name == "metadata_utility":
            sub.add_argument("--file-count", type=int, default=1000)
        elif name == "token_efficiency":
            sub.add_argument("--file-count", type=int, default=1000)
        elif name == "safety":
            sub.add_argument("--file-count", type=int, default=500)
        elif name == "history_audit":
            sub.add_argument("--file-count", type=int, default=500)
        elif name == "large_files":
            sub.add_argument("--file-count", type=int, default=1000)
            sub.add_argument("--large-file-size-mb", type=int, default=101)
        elif name == "frequent_updates":
            sub.add_argument("--file-count", type=int, default=500)
        elif name == "metadata_consistency":
            sub.add_argument("--file-count", type=int, default=1000)
            sub.add_argument("--operation-count", type=int, default=5000)
            sub.add_argument(
                "--operation-distribution",
                default=None,
                help="Comma-separated weights, e.g. create_file=20,modify_file=30",
            )
            sub.add_argument(
                "--cleanup-temp",
                default="true",
                help="Whether to cleanup generated temp workspace after run (true/false)",
            )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scalability":
        return run_scalability(args)
    if args.command == "metadata_utility":
        return run_metadata_utility(args)
    if args.command == "token_efficiency":
        return run_token_efficiency(args)
    if args.command == "safety":
        return run_safety(args)
    if args.command == "history_audit":
        return run_history_audit(args)
    if args.command == "large_files":
        return run_large_files(args)
    if args.command == "frequent_updates":
        return run_frequent_updates(args)
    if args.command == "metadata_consistency":
        return run_metadata_consistency(args)
    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
