from __future__ import annotations

import json
from pathlib import Path

from experiments.dataset_generator import GenerationConfig, generate_workspace


def _count_files(root: Path) -> int:
    return sum(1 for p in root.rglob("*") if p.is_file() and p.name != "synthetic_manifest.json")


def test_dataset_generator_file_count(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    cfg = GenerationConfig(
        output=ws,
        num_files=120,
        duplicate_ratio=0.1,
        large_file_ratio=0.05,
        large_file_size_mb=101,
        structure="mixed",
        seed=42,
    )
    manifest = generate_workspace(cfg)
    assert manifest["total_files"] == 120
    assert _count_files(ws) == 120


def test_dataset_generator_reproducible_same_seed(tmp_path: Path) -> None:
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    cfg1 = GenerationConfig(ws1, 80, 0.1, 0.1, 101, "mixed", 7)
    cfg2 = GenerationConfig(ws2, 80, 0.1, 0.1, 101, "mixed", 7)
    m1 = generate_workspace(cfg1)
    m2 = generate_workspace(cfg2)

    assert m1["file_type_distribution"] == m2["file_type_distribution"]
    assert len(m1["duplicate_groups"]) == len(m2["duplicate_groups"])


def test_duplicate_groups_are_identical_by_content(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    cfg = GenerationConfig(ws, 100, 0.2, 0.0, 101, "mixed", 123)
    manifest = generate_workspace(cfg)
    for group in manifest["duplicate_groups"]:
        members = group["members"]
        if len(members) < 2:
            continue
        blobs = [(ws / rel).read_bytes() for rel in members]
        head = blobs[0]
        assert all(b == head for b in blobs[1:])


def test_synthetic_manifest_valid_json(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    cfg = GenerationConfig(ws, 50, 0.1, 0.1, 101, "shallow", 9)
    generate_workspace(cfg)
    manifest_path = ws / "synthetic_manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["total_files"] == 50
    assert "duplicate_groups" in data
    assert "file_type_distribution" in data
