Please add a new experiment group for MetaMirror:

metadata_consistency

Goal:
Verify that metadata.db remains consistent with the local filesystem under create, update, delete, move, rename, proposal, approval, rejection, soft-delete, restore, and reconciliation scenarios.

This experiment should demonstrate that MetaMirror can synchronize metadata CRUD operations without producing inconsistent states.

Do not add plotting code.
Do not add paper files.
Do not hard delete user files.
Only run destructive operations inside generated temporary workspaces.

============================================================
Experiment: metadata_consistency
============================================================

Implement a new experiment named:

metadata_consistency

Command example:

python experiments/benchmark_runner.py metadata_consistency \
  --output experiment_results/metadata_consistency \
  --file-count 1000 \
  --operation-count 5000 \
  --seed 42 \
  --cleanup-temp true

============================================================
Definitions
============================================================

The experiment should treat the real local filesystem as the ground truth for active files.

For each operation, compare:
1. filesystem state
2. metadata.db state
3. file_events table
4. audit.jsonl
5. .metamirror/trash/ when soft delete is involved

Define consistency invariants.

Invariant 1: Active file invariant
Every active file in the filesystem, excluding ignored directories, should have exactly one active row in `files`.

Invariant 2: Missing/deleted invariant
If a DB row is marked `active`, the corresponding path should exist.
If a file no longer exists after reconciliation, its DB status should be `missing` or `deleted`, not silently removed.

Invariant 3: Metadata update invariant
After modifying a file and reconciling:
- size_bytes should match filesystem size
- modified_at should be updated
- dirty should be true or metadata_status should be stale/ready depending on implementation
- sha256 should be updated if the file is small enough to hash

Invariant 4: Move/rename invariant
After moving or renaming a file:
- the new path should exist in DB
- the old path should not remain active
- a `moved` event should be recorded if move detection is supported
- if move detection is not supported, the system should at least mark old path missing and new path active

Invariant 5: Proposal invariant
Creating a delete proposal should:
- insert exactly one row in `action_proposals`
- create an `ai_proposed_delete` event
- write an audit entry
- not delete or move the raw file

Invariant 6: Approval invariant
Approving a delete proposal should:
- move the raw file to `.metamirror/trash/<date>/`
- update files.status to `soft_deleted`
- update proposal status to `executed`
- write `soft_deleted` and `user_approved_delete` events
- write audit entries
- never hard delete the file

Invariant 7: Rejection invariant
Rejecting a proposal should:
- update proposal status to `rejected`
- write a `user_rejected_delete` event
- write audit entry
- leave the raw file unchanged and active

Invariant 8: Audit completeness invariant
Every metadata-changing operation should have a corresponding file_events entry and/or audit.jsonl entry.

Invariant 9: Reconciliation invariant
If watcher events are skipped or simulated as missed, running a full scan/reconcile should restore consistency between metadata.db and filesystem state.

============================================================
Operation Workload
============================================================

Generate a synthetic workspace, initialize MetaMirror, and perform a randomized sequence of operations.

Supported operations:
- create_file
- modify_file
- delete_file_externally
- move_file
- rename_file
- propose_delete
- approve_delete_proposal
- reject_delete_proposal
- restore_soft_deleted_file if restore exists
- simulate_missed_event_then_reconcile

Operation distribution should be configurable.

Default distribution:
- create_file: 15%
- modify_file: 25%
- delete_file_externally: 10%
- move_file: 10%
- rename_file: 10%
- propose_delete: 10%
- approve_delete_proposal: 8%
- reject_delete_proposal: 7%
- simulate_missed_event_then_reconcile: 5%

If restore is implemented, include restore operations. Otherwise skip and record restore_supported=false.

============================================================
Procedure
============================================================

1. Generate a temporary synthetic workspace with N files.
2. Run `metamirror init`.
3. Run `metamirror scan`.
4. Check initial consistency.
5. Execute operation_count randomized operations.
6. After each operation:
   - optionally run incremental sync if watcher is available
   - otherwise run scan/reconcile
   - check all applicable invariants
   - record violations
7. At the end:
   - run full scan/reconcile
   - check final consistency
   - export results

============================================================
Outputs
============================================================

Write:

experiment_results/metadata_consistency/metadata_consistency_results.csv
experiment_results/metadata_consistency/metadata_consistency_events.jsonl
experiment_results/metadata_consistency/invariant_violations.jsonl
experiment_results/metadata_consistency/final_state_summary.json

CSV columns for metadata_consistency_results.csv:
- run_id
- file_count
- operation_count
- seed
- operation_type
- operations_executed
- invariant_checks
- invariant_violations
- consistency_score
- active_file_mismatches
- missing_file_mismatches
- stale_hash_mismatches
- path_mismatches
- event_log_missing_count
- audit_log_missing_count
- proposal_state_mismatches
- trash_state_mismatches
- reconcile_repairs
- final_consistency_passed
- latency_ms

JSONL event rows should include:
- run_id
- step_id
- operation_type
- target_file_id
- old_path
- new_path
- expected_state
- observed_state
- invariants_checked
- violations
- latency_ms

Invariant violation rows should include:
- run_id
- step_id
- invariant_name
- severity
- expected
- observed
- file_id
- path
- operation_type

final_state_summary.json should include:
- total_files_in_filesystem
- total_active_rows_in_db
- total_missing_rows
- total_deleted_rows
- total_soft_deleted_rows
- total_proposals
- pending_proposals
- executed_proposals
- rejected_proposals
- total_file_events
- total_audit_events
- final_consistency_passed
- consistency_score

============================================================
Metrics
============================================================

Compute:

1. consistency_score:
   1 - (total_invariant_violations / total_invariant_checks)

2. active_file_match_rate:
   active filesystem files matched by active DB rows

3. db_active_validity:
   active DB rows whose paths exist in the filesystem

4. delete_tracking_accuracy:
   externally deleted files that become missing/deleted after reconcile

5. update_tracking_accuracy:
   modified files whose size/mtime/hash are correctly reflected

6. move_tracking_accuracy:
   moved/renamed files correctly reflected as moved or missing+created

7. proposal_consistency:
   proposal rows whose status matches file/trash/audit state

8. audit_completeness:
   operations with matching event/audit records

9. reconcile_repair_rate:
   missed-event inconsistencies repaired by full reconcile

============================================================
Figure-ready CSV
============================================================

Update experiments/prepare_figure_data.py to generate:

experiment_results/figure_data/figure_metadata_consistency.csv

Columns:
- operation_type
- consistency_score
- invariant_violations
- active_file_match_rate
- db_active_validity
- delete_tracking_accuracy
- update_tracking_accuracy
- move_tracking_accuracy
- proposal_consistency
- audit_completeness
- reconcile_repair_rate
- latency_ms

============================================================
Wow Summary
============================================================

Update wow_summary.json and wow_summary.csv to include:

- metadata_consistency_score
- final_consistency_passed
- total_invariant_checks
- total_invariant_violations
- active_file_match_rate
- db_active_validity
- delete_tracking_accuracy
- update_tracking_accuracy
- move_tracking_accuracy
- proposal_consistency
- audit_completeness
- reconcile_repair_rate

============================================================
Tests
============================================================

Add tests for:
1. create consistency
2. update consistency
3. external delete becomes missing, not removed
4. move/rename consistency
5. propose-delete does not move/delete file
6. approve proposal soft-deletes file and updates DB
7. reject proposal leaves file unchanged
8. full reconcile repairs simulated missed events
9. audit/event log completeness

============================================================
Important Safety Constraints
============================================================

- Never hard delete files.
- Only operate inside generated temporary workspaces.
- Never modify files outside the experiment workspace.
- Exclude `.metamirror/`, `.git/`, `node_modules/`, `.venv/`, and `__pycache__/`.
- If an invariant fails, record the failure and continue unless the filesystem safety boundary is violated.
- If any operation attempts to modify outside the temporary workspace, abort immediately.

Do not generate plots.