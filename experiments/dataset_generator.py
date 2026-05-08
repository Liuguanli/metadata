from __future__ import annotations

import argparse
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SMALL_FILE_TYPES = [".txt", ".md", ".py", ".json", ".csv", ".pdf"]
TOPIC_LABELS = ["research", "finance", "visa", "code", "photos", "logs", "contracts"]


@dataclass
class GenerationConfig:
    output: Path
    num_files: int
    duplicate_ratio: float
    large_file_ratio: float
    large_file_size_mb: int
    structure: str
    seed: int


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _dir_for_index(base: Path, idx: int, structure: str, rng: random.Random) -> Path:
    if structure == "shallow":
        return base / f"group_{idx % 10:02d}"
    if structure == "deep":
        return base / f"lvl1_{idx % 7:02d}" / f"lvl2_{idx % 11:02d}" / f"lvl3_{idx % 13:02d}"
    # mixed
    mode = rng.choice(["shallow", "deep"])
    return _dir_for_index(base, idx, mode, rng)


def _small_file_content(idx: int, ext: str, topic: str, rng: random.Random) -> str:
    base = f"file_index={idx}\ntopic={topic}\nseed_token={rng.randint(0, 10_000_000)}\n"
    if ext == ".py":
        return f"# topic: {topic}\nvalue_{idx} = {rng.randint(1, 9999)}\n"
    if ext == ".json":
        return json.dumps({"id": idx, "topic": topic, "value": rng.randint(1, 9999)}, sort_keys=True)
    if ext == ".csv":
        return f"id,topic,value\n{idx},{topic},{rng.randint(1, 9999)}\n"
    if ext == ".pdf":
        return f"PDF_PLACEHOLDER topic={topic} id={idx}\n"
    return base


def _write_large_sparse(path: Path, size_mb: int) -> None:
    size_bytes = size_mb * 1024 * 1024
    with path.open("wb") as fh:
        fh.seek(size_bytes - 1)
        fh.write(b"\0")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def generate_workspace(cfg: GenerationConfig) -> dict[str, Any]:
    rng = random.Random(cfg.seed)
    workspace = cfg.output.resolve()
    _mkdir(workspace)

    n_total = cfg.num_files
    n_large = int(round(n_total * cfg.large_file_ratio))
    n_dups = int(round(n_total * cfg.duplicate_ratio))
    n_dups = min(n_dups, max(0, n_total - 1))

    paths: list[Path] = []
    file_type_distribution: dict[str, int] = {k: 0 for k in SMALL_FILE_TYPES + [".bin"]}
    topics_for_file: dict[str, str] = {}
    duplicate_groups: list[dict[str, Any]] = []

    # 1) Create base files
    for i in range(n_total):
        is_large = i < n_large
        ext = ".bin" if is_large else rng.choice(SMALL_FILE_TYPES)
        d = _dir_for_index(workspace, i, cfg.structure, rng)
        _mkdir(d)
        file_path = d / f"file_{i:06d}{ext}"
        topic = rng.choice(TOPIC_LABELS)
        topics_for_file[str(file_path.relative_to(workspace))] = topic

        if is_large:
            _write_large_sparse(file_path, cfg.large_file_size_mb)
        else:
            content = _small_file_content(i, ext, topic, rng)
            file_path.write_text(content, encoding="utf-8")

        paths.append(file_path)
        file_type_distribution[ext] = file_type_distribution.get(ext, 0) + 1

    # 2) Make duplicates by copying from prior files to later files
    dup_pairs = 0
    dup_candidates = [p for p in paths if p.suffix != ".bin"]
    rng.shuffle(dup_candidates)
    max_pairs = min(n_dups, len(dup_candidates) // 2)
    for j in range(max_pairs):
        src = dup_candidates[j]
        dst = dup_candidates[-(j + 1)]
        if src == dst:
            continue
        dst.write_bytes(src.read_bytes())
        duplicate_groups.append(
            {
                "group_id": f"dup_{j:04d}",
                "sha256": _sha256(src),
                "members": [
                    str(src.relative_to(workspace)),
                    str(dst.relative_to(workspace)),
                ],
            }
        )
        dup_pairs += 1

    all_dirs = [p for p in workspace.rglob("*") if p.is_dir()]
    manifest = {
        "total_files": n_total,
        "total_directories": len(all_dirs),
        "duplicate_groups": duplicate_groups,
        "expected_duplicate_count": dup_pairs * 2,
        "expected_large_file_count": n_large,
        "random_seed": cfg.seed,
        "file_type_distribution": file_type_distribution,
        "topic_labels": topics_for_file,
        "structure": cfg.structure,
        "large_file_size_mb": cfg.large_file_size_mb,
    }
    manifest_path = workspace / "synthetic_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic workspace generator")
    parser.add_argument("--output", required=True)
    parser.add_argument("--num-files", type=int, default=1000)
    parser.add_argument("--duplicate-ratio", type=float, default=0.1)
    parser.add_argument("--large-file-ratio", type=float, default=0.05)
    parser.add_argument("--large-file-size-mb", type=int, default=101)
    parser.add_argument("--structure", choices=["shallow", "deep", "mixed"], default="mixed")
    parser.add_argument("--seed", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = GenerationConfig(
        output=Path(args.output),
        num_files=args.num_files,
        duplicate_ratio=args.duplicate_ratio,
        large_file_ratio=args.large_file_ratio,
        large_file_size_mb=args.large_file_size_mb,
        structure=args.structure,
        seed=args.seed,
    )
    manifest = generate_workspace(cfg)
    print(json.dumps({"output": str(cfg.output.resolve()), "summary": manifest}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
