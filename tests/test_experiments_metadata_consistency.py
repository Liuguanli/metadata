from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from experiments import benchmark_runner


def _run_metadata_consistency(
    tmp_path: Path,
    *,
    name: str,
    distribution: str,
    file_count: int = 30,
    operation_count: int = 8,
) -> Path:
    out = tmp_path / name
    exit_code = benchmark_runner.main(
        [
            "metadata_consistency",
            "--output",
            str(out),
            "--file-count",
            str(file_count),
            "--operation-count",
            str(operation_count),
            "--seed",
            "42",
            "--operation-distribution",
            distribution,
            "--cleanup-temp",
            "false",
        ]
    )
    assert exit_code == 0
    assert (out / "metadata_consistency_results.csv").exists()
    assert (out / "metadata_consistency_events.jsonl").exists()
    assert (out / "invariant_violations.jsonl").exists()
    assert (out / "final_state_summary.json").exists()
    return out


def _all_row(output: Path) -> dict[str, str]:
    rows = list(csv.DictReader((output / "metadata_consistency_results.csv").open("r", encoding="utf-8")))
    for r in rows:
        if r["operation_type"] == "ALL":
            return r
    raise AssertionError("ALL row missing")


def _workspace_db(output: Path) -> sqlite3.Connection:
    db = output / "workspace" / ".metamirror" / "metadata.db"
    assert db.exists()
    return sqlite3.connect(db)


def test_metadata_consistency_create_consistency(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_create",
        distribution="create_file=100",
    )
    all_row = _all_row(out)
    assert int(float(all_row["active_file_mismatches"])) == 0
    assert float(all_row["consistency_score"]) >= 0.9


def test_metadata_consistency_update_consistency(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_update",
        distribution="modify_file=100",
    )
    all_row = _all_row(out)
    assert float(all_row["update_tracking_accuracy"]) >= 0.9


def test_metadata_consistency_external_delete_becomes_missing(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_delete",
        distribution="delete_file_externally=100",
    )
    conn = _workspace_db(out)
    try:
        missing = conn.execute("SELECT COUNT(*) FROM files WHERE status='missing'").fetchone()[0]
        total_rows = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    finally:
        conn.close()
    assert missing > 0
    assert total_rows >= 1


def test_metadata_consistency_move_rename_consistency(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_move_rename",
        distribution="move_file=50,rename_file=50",
    )
    all_row = _all_row(out)
    assert float(all_row["move_tracking_accuracy"]) >= 0.8


def test_metadata_consistency_propose_does_not_move_file(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_propose",
        distribution="propose_delete=100",
    )
    conn = _workspace_db(out)
    try:
        pending = conn.execute("SELECT COUNT(*) FROM action_proposals WHERE status='pending'").fetchone()[0]
        soft_deleted = conn.execute("SELECT COUNT(*) FROM files WHERE status='soft_deleted'").fetchone()[0]
    finally:
        conn.close()
    assert pending > 0
    assert soft_deleted == 0


def test_metadata_consistency_approve_soft_deletes_file(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_approve",
        distribution="approve_delete_proposal=100",
    )
    conn = _workspace_db(out)
    try:
        approved = conn.execute("SELECT COUNT(*) FROM action_proposals WHERE status='approved'").fetchone()[0]
        soft_deleted = conn.execute("SELECT COUNT(*) FROM files WHERE status='soft_deleted'").fetchone()[0]
        in_trash = conn.execute(
            "SELECT COUNT(*) FROM files WHERE status='soft_deleted' AND path LIKE '.metamirror/trash/%'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert approved > 0
    assert soft_deleted > 0
    assert in_trash == soft_deleted


def test_metadata_consistency_restore_returns_active_and_logs_restore_event(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_restore",
        distribution="approve_delete_proposal=60,restore_soft_deleted_file=40",
        operation_count=12,
    )
    conn = _workspace_db(out)
    try:
        restored_events = conn.execute(
            "SELECT COUNT(*) FROM file_events WHERE event_type='restored'"
        ).fetchone()[0]
        active_rows = conn.execute("SELECT COUNT(*) FROM files WHERE status='active'").fetchone()[0]
    finally:
        conn.close()
    assert restored_events > 0
    assert active_rows > 0


def test_metadata_consistency_reject_leaves_file_unchanged(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_reject",
        distribution="reject_delete_proposal=100",
    )
    conn = _workspace_db(out)
    try:
        rejected = conn.execute("SELECT COUNT(*) FROM action_proposals WHERE status='rejected'").fetchone()[0]
        active_for_rejected = conn.execute(
            """
            SELECT COUNT(*)
            FROM action_proposals p
            JOIN files f ON f.file_id = p.file_id
            WHERE p.status='rejected' AND f.status='active'
            """
        ).fetchone()[0]
    finally:
        conn.close()
    assert rejected > 0
    assert active_for_rejected == rejected


def test_metadata_consistency_reconcile_repairs_missed_events(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_reconcile",
        distribution="simulate_missed_event_then_reconcile=100",
    )
    all_row = _all_row(out)
    assert int(float(all_row["reconcile_repairs"])) >= 1


def test_metadata_consistency_audit_event_completeness(tmp_path: Path) -> None:
    out = _run_metadata_consistency(
        tmp_path,
        name="mc_audit",
        distribution="create_file=25,modify_file=25,propose_delete=25,approve_delete_proposal=25",
        operation_count=10,
    )
    all_row = _all_row(out)
    assert int(float(all_row["event_log_missing_count"])) == 0
    assert int(float(all_row["audit_log_missing_count"])) == 0
    assert float(all_row["audit_completeness"]) >= 0.9
