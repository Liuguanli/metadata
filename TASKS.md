# MetaMirror Task Board

Last updated: 2026-05-07
Owner: Codex
Current mode: Auto-validation and continuous execution
CLI invocation: `metamirror ...` or `python3 -m metamirror ...`

## Acceptance Protocol

1. 我一次只推进一个任务，把它从 `TODO` 移到 `DOING`。
2. 完成后我会固定汇报：
   - 改了哪些文件
   - 做了什么行为变化
   - 运行了哪些命令（含关键输出摘要）
3. 我会给你该任务的“验收动作”和“通过标准”。
4. 我会停止继续开发，等待你回复 `验收通过`（或指出问题）。
5. 你未确认前，不进入下一个任务。

## Progress Overview

- Phase 1: init + schema + scan + status (100%)
- Phase 2: search + duplicates + recent (100%)
- Phase 3: propose-delete + approve/reject + audit linkage (100%)
- Phase 4: tests completion + regression (100%)
- Phase 5: CLI examples + docs wrap-up (100%)
- Phase 6: spec-gap fixes (100%)
- Phase 7: experiments layer + plotting (100%)
- Phase 8: EXP_PLUS metadata consistency extension (100%)

## TODO

### Phase 1

### Phase 2

### Phase 3

### Phase 4

### Phase 5

### Phase 6

- (none)

### Phase 7

### Phase 8

- [ ] (none)

## DOING

- [ ] (empty)

## DONE

- [x] P6-04: Add installable `metamirror` console command
  - Completed: 2026-05-05
  - Evidence: added `pyproject.toml` with `project.scripts.metamirror`, installed editable package, and verified `metamirror --help`
  - User acceptance action: run `python3 -m pip install -e .` then `metamirror --help`
  - Pass condition: `metamirror` command works without `python3 -m`

- [x] P6-03: Use proposal statuses `approved` and `expired`
  - Completed: 2026-05-05
  - Evidence: approve now writes proposal status `approved`; new `expire` command transitions pending proposals to `expired` with event/audit
  - User acceptance action: approve one pending proposal and expire another, then inspect `action_proposals.status`
  - Pass condition: lifecycle can produce `approved` and `expired`

- [x] P6-02: Emit `moved/deleted/restored` event types in real flows
  - Completed: 2026-05-05
  - Evidence: approve flow emits `moved` + `deleted`; restore flow emits `moved` + `restored`
  - User acceptance action: run approve + restore flow, then query `file_events`
  - Pass condition: real `moved`, `deleted`, `restored` events observed

- [x] E11: Plot rendering from figure-ready CSV
  - Completed: 2026-05-01
  - Evidence: rendered 5 PNG plots from figure-ready CSV files under `experiment_results/figures`
  - User acceptance action: run plot script and inspect generated images
  - Pass condition: experiment plots are generated from figure-ready CSV files

- [x] EP3: EXP_PLUS tests + stronger run + outputs validation
  - Completed: 2026-05-01
  - Evidence: `pytest -q tests/test_experiments_metadata_consistency.py` passed (9), generated strong run (`file_count=800`, `operation_count=900`) with complete outputs
  - User acceptance action: inspect `experiment_results/metadata_consistency/*` and `experiment_results/wow_summary.*`
  - Pass condition: all required EXP_PLUS outputs exist and key metrics are populated

- [x] EP2: Figure-ready + wow summary integration for metadata consistency
  - Completed: 2026-05-01
  - Evidence: `prepare_figure_data` now emits `figure_metadata_consistency.csv`; `wow_summary.json/csv` auto-updated after run
  - User acceptance action: run `python3 experiments/prepare_figure_data.py --input experiment_results --output experiment_results/figure_data`
  - Pass condition: `figure_metadata_consistency.csv` and wow summary fields are generated

- [x] EP1: Add `metadata_consistency` experiment group
  - Completed: 2026-05-01
  - Evidence: added randomized operation workload with invariant checks, events log, violations log, final summary, and safety boundary guard
  - User acceptance action: run `python3 experiments/benchmark_runner.py metadata_consistency --output experiment_results/metadata_consistency --file-count 100 --operation-count 100 --seed 42 --cleanup-temp true`
  - Pass condition: required CSV/JSONL/JSON outputs are generated and final consistency check runs

- [x] E10: Experiments README + tests
  - Completed: 2026-05-01
  - Evidence: README completed with runbook/metrics/output docs; targeted experiment test suite passed (11)
  - User acceptance action: run targeted experiment tests
  - Pass condition: docs complete and smoke tests pass

- [x] E9: Figure-ready CSV preparation
  - Completed: 2026-05-01
  - Evidence: generated all 5 figure-ready CSV files; added smoke test for preparation pipeline
  - User acceptance action: run `python3 experiments/prepare_figure_data.py --input experiment_results --output experiment_results/figure_data`
  - Pass condition: figure-ready CSV files generated when source data exists

- [x] E8: Frequent-update experiment
  - Completed: 2026-05-01
  - Evidence: generated `frequent_update_results.csv` + `update_events.jsonl` for low/medium/high update profiles
  - User acceptance action: run frequent_updates command
  - Pass condition: frequent update CSV + update events jsonl generated

- [x] E7: History/audit experiment
  - Completed: 2026-05-01
  - Evidence: generated `history_audit_results.csv` + `ground_truth_events.jsonl` + `metamirror_events.jsonl`
  - User acceptance action: run history_audit command
  - Pass condition: results CSV + ground truth/metamirror event jsonl files

- [x] E6: Large-file experiment
  - Completed: 2026-05-01
  - Evidence: implemented ratio sweep (0/1/5/10/20%) with real scan metrics; generated `large_file_results.csv`
  - User acceptance action: run large_files command
  - Pass condition: large-file CSV generated with ratio-wise metrics

- [x] E5: Metadata utility experiment + metrics output
  - Completed: 2026-05-01
  - Evidence: implemented metadata-only retrieval evaluation; generated `metadata_utility_results.csv` with precision/recall/MRR and `raw_file_reads=0`
  - User acceptance action: run metadata_utility command
  - Pass condition: utility CSV with precision/recall/MRR and zero raw reads

- [x] E4: Safety experiment + CSV/JSONL output
  - Completed: 2026-05-01
  - Evidence: implemented direct-vs-metamirror safety run; generated `safety_results.csv` and `safety_events.jsonl`
  - User acceptance action: run safety command
  - Pass condition: safety result files generated in temp-only workspaces

- [x] E3: Scalability experiment + CSV output
  - Completed: 2026-05-01
  - Evidence: implemented real scalability loop + smoke test; generated CSV/manifest under `experiment_results/scalability_e3`
  - User acceptance action: run scalability command with small counts
  - Pass condition: `scalability_results.csv` and `manifest.json` generated

- [x] E2: Synthetic workspace generator + tests
  - Completed: 2026-05-01
  - Evidence: generator implemented with deterministic seed/duplicates/large-files; tests passed (4)
  - User acceptance action: run dataset generator and inspect `synthetic_manifest.json`
  - Pass condition: deterministic generation, duplicate truth, large-file support

- [x] E1: Experimental framework skeleton (`experiments/` + benchmark runner + manifests)
  - Completed: 2026-05-01
  - Evidence: `experiments/` skeleton exists; runner supports all named experiments; manifest/result placeholders generated
  - User acceptance action: run `python3 experiments/benchmark_runner.py --help`
  - Pass condition: framework files exist and runner supports named experiments

- [x] P6-01: Create `.metamirror/derived/summaries/` during `init`
  - Completed: 2026-05-01
  - Evidence: `find .metamirror/derived -maxdepth 2` shows `.metamirror/derived/summaries`
  - User acceptance action: run `python3 -m metamirror init . && find .metamirror/derived -maxdepth 2 | sort`
  - Pass condition: `.metamirror/derived/summaries` exists

- [x] P5-02: Final docs consistency pass
  - Completed: 2026-05-01
  - Evidence: added `IMPLEMENTATION_SPEC.md` + `IMPLEMENTATION_CONSISTENCY.md`, added `watch` command, and verified `pytest -q` (8 passed)
  - User acceptance action: review spec vs implementation checklist
  - Pass condition: behavior matches `IMPLEMENTATION_SPEC.md` and safety constraints

- [x] P5-01: Add CLI usage examples
  - Completed: 2026-05-01
  - Evidence: `CLI_USAGE.md` added with runnable examples for all implemented CLI commands
  - User acceptance action: review docs and run sample commands
  - Pass condition: every required CLI command has a runnable example

- [x] P4-06: Test excluded paths
  - Completed: 2026-05-01
  - Evidence: `pytest -k exclude -q` passed; excluded paths were not inserted
  - User acceptance action: run `pytest -k exclude -q`
  - Pass condition: excluded-path test passes

- [x] P4-05: Test proposal and approval flow
  - Completed: 2026-05-01
  - Evidence: `pytest -k proposal -q` passed (2 tests)
  - User acceptance action: run `pytest -k proposal -q`
  - Pass condition: propose/approve safety behavior passes

- [x] P4-04: Test duplicate detection
  - Completed: 2026-05-01
  - Evidence: `pytest -k duplicate -q` passed; same-content files grouped with `count=2`
  - User acceptance action: run `pytest -k duplicate -q`
  - Pass condition: duplicate test passes

- [x] P4-03: Test missing file behavior
  - Completed: 2026-05-01
  - Evidence: `pytest -k missing -q` passed; deleted file stayed in DB with `status=missing`
  - User acceptance action: run `pytest -k missing -q`
  - Pass condition: missing-file test passes and keeps DB history

- [x] P4-02: Test `scan` inserts and updates
  - Completed: 2026-05-01
  - Evidence: `pytest -k scan -q` passed (3 tests)
  - User acceptance action: run `pytest -k scan -q`
  - Pass condition: scan tests pass

- [x] P4-01: Test `init` scaffolding
  - Completed: 2026-05-01
  - Evidence: `pytest -k init -q` passed with 1 test
  - User acceptance action: run `pytest -k init -q`
  - Pass condition: init test passes

- [x] P3-04: Implement `reject`
  - Completed: 2026-05-01
  - Evidence: rejecting a pending proposal set `status=rejected`, wrote `user_rejected_delete` event, and wrote audit record; raw file stayed unchanged
  - User acceptance action: reject a pending proposal and inspect DB/audit
  - Pass condition: proposal `rejected`; `user_rejected_delete` event exists; audit entry exists

- [x] P3-03: Implement `approve`
  - Completed: 2026-05-01
  - Evidence: approving a pending delete moved file into trash, set `files.status=soft_deleted`, set proposal `executed`, and wrote approval events + audit
  - User acceptance action: approve a pending delete and inspect file location + DB state
  - Pass condition: file moved to `.metamirror/trash/<date>/`; file status `soft_deleted`; proposal `executed`; events/audit written

- [x] P3-02: Implement `proposals` listing
  - Completed: 2026-05-01
  - Evidence: `proposals` command returns lifecycle fields and supports `--status` filter
  - User acceptance action: run `python3 -m metamirror proposals .`
  - Pass condition: shows pending/executed/rejected proposals with key lifecycle fields

- [x] P3-01: Implement `propose-delete`
  - Completed: 2026-05-01
  - Evidence: proposal row (`pending`) + `ai_proposed_delete` event + audit entry created, while raw file remained present
  - User acceptance action: run `python3 -m metamirror propose-delete . <file_id> --reason ... --evidence ...`
  - Pass condition: proposal row + `ai_proposed_delete` event + audit entry created; raw file unchanged

- [x] P2-03: Implement `metamirror recent <workspace> --days N`
  - Completed: 2026-04-30
  - Evidence: recent output listed `created`/`modified` events in descending timestamp order after two scans
  - User acceptance action: run `python3 -m metamirror recent . --days 7`
  - Pass condition: recent `file_events` are listed in time order

- [x] P2-02: Implement `metamirror duplicates <workspace>`
  - Completed: 2026-04-30
  - Evidence: a temp workspace with two same-content files produced one duplicate group (`count=2`) with shared sha256
  - User acceptance action: create two same-content files then run `python3 -m metamirror duplicates .`
  - Pass condition: duplicate group appears with count > 1 and shared sha256

- [x] P2-01: Implement `metamirror search <workspace> "query"`
  - Completed: 2026-04-30
  - Evidence: query matched by filename/path and by `file_metadata.summary/tags`
  - User acceptance action: run `python3 -m metamirror search . "<known-keyword>"`
  - Pass condition: searches filename/path/summary/tags and returns required fields

- [x] P1-06: Implement `metamirror status <workspace>`
  - Completed: 2026-04-30
  - Evidence: status output includes totals, status counts, and latest `last_seen_at`
  - User acceptance action: run `python3 -m metamirror status .`
  - Pass condition: output includes file counts and scan health summary

- [x] P1-05: Implement metadata write path + large file hash policy
  - Completed: 2026-04-30
  - Evidence: scan result showed small file `has_hash=1`, large file `has_hash=0`, both with `metadata_status=basic_only`
  - User acceptance action: scan one small file and one >100MB file, then query `sha256, metadata_status`
  - Pass condition: small file has sha256; large file has `sha256=NULL` and `metadata_status=basic_only`

- [x] P1-04: Implement full scanner with exclude rules
  - Completed: 2026-04-30
  - Evidence: scan over a temp workspace inserted only `docs/keep.txt`; excluded directories/files were not inserted
  - User acceptance action: create sample files in include/exclude dirs, run `python3 -m metamirror scan .`, inspect DB rows
  - Pass condition: excluded paths (`.git/`, `.metamirror/`, `node_modules/`, `.venv/`, `__pycache__/`, `.DS_Store`) are not inserted

- [x] P1-03: Implement `metamirror init <workspace>`
  - Completed: 2026-04-30
  - Evidence: `python3 -m metamirror init .` created required files/directories and wrote audit entry
  - User acceptance action: run `python3 -m metamirror init . && find .metamirror -maxdepth 3 | sort`
  - Pass condition: `.metamirror/`, `metadata.db`, `derived/`, `trash/`, `audit.jsonl` exist

- [x] P1-02: Implement SQLite schema initialization (`files`, `file_metadata`, `file_policy`, `file_events`, `action_proposals`)
  - Completed: 2026-04-30
  - Evidence: `init_db('.')` executed twice successfully; all required tables exist
  - User acceptance action: run `sqlite3 .metamirror/metadata.db '.tables'`
  - Pass condition: all required tables are present and re-running init does not duplicate or fail

- [x] P1-01: Create Python project skeleton (`metamirror/`, `tests/`)
  - Completed: 2026-04-30
  - Evidence: package modules and baseline test files were created
  - User acceptance action: run `find metamirror tests -maxdepth 2 -type f | sort`
  - Pass condition: package files and baseline test files exist

- [x] T0-01: Read and summarize `first.md`
  - Completed: 2026-04-30
  - Note: No code changes were made during understanding step.
