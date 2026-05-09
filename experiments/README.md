# MetaMirror Experiments

This directory contains reproducible, workspace-local benchmarking scripts for MetaMirror.

Important:

- Experiments run only on generated synthetic workspaces or explicitly provided test workspaces.
- Do not run destructive/direct-mode scripts on your real data directories.
- No paper text and no bibliography handling are embedded here.
- Outputs are clean data artifacts: CSV, JSONL, and JSON manifest files.

### Agent model in case studies

The agent in our case studies is a **deterministic oracle, not an LLM**. It
encodes plausible workspace-cleanup intents (find duplicates, archive old
files, trim large files) and executes them either through raw filesystem
ops (Direct mode) or through the MetaMirror gateway (MetaMirror mode). This
isolates the *mediation* effect of MetaMirror from the variability of an
LLM-backed agent. Driving a real LLM-backed agent (Codex, Claude Code,
Cursor) on the same task set is left to future work and is tracked as an
open challenge in the paper.

## 1) Synthetic workspace generation

```bash
python3 experiments/dataset_generator.py \
  --output /tmp/mm_ws \
  --num-files 1000 \
  --duplicate-ratio 0.1 \
  --large-file-ratio 0.05 \
  --large-file-size-mb 101 \
  --structure mixed \
  --seed 42
```

Generated output:

- `/tmp/mm_ws/synthetic_manifest.json`

Manifest includes:

- `total_files`
- `total_directories`
- `duplicate_groups`
- `expected_duplicate_count`
- `expected_large_file_count`
- `random_seed`
- `file_type_distribution`
- `topic_labels`

## 2) Run each experiment

All experiments use:

```bash
python3 experiments/benchmark_runner.py <experiment_name> [options]
```

Common options:

- `--seed <int>`: deterministic workspace generation seed.
- `--cleanup-large-files true|false` (default `true`): remove oversized generated files after each run.
- `--cleanup-large-threshold-mb <int>` (default `100`): cleanup threshold.

Reproducibility + cleanup metadata is written to each `manifest.json`:

- `generated_file_hashes`
- `reproducibility_token`
- `post_run_cleanup`

### Scalability

```bash
python3 experiments/benchmark_runner.py scalability \
  --output experiment_results/scalability \
  --file-counts 100 1000 5000 \
  --duplicate-ratio 0.1 \
  --repeats 3 \
  --seed 42
```

Outputs:

- `experiment_results/scalability/scalability_results.csv`
- `experiment_results/scalability/manifest.json`

### Metadata utility

```bash
python3 experiments/benchmark_runner.py metadata_utility \
  --output experiment_results/metadata_utility \
  --file-count 1000 \
  --seed 42
```

Outputs:

- `experiment_results/metadata_utility/metadata_utility_results.csv`
- `experiment_results/metadata_utility/manifest.json`

### Safety

```bash
python3 experiments/benchmark_runner.py safety \
  --output experiment_results/safety \
  --file-count 500 \
  --seed 42
```

Outputs:

- `experiment_results/safety/safety_results.csv`
- `experiment_results/safety/safety_events.jsonl`
- `experiment_results/safety/manifest.json`

### History/audit

```bash
python3 experiments/benchmark_runner.py history_audit \
  --output experiment_results/history_audit \
  --file-count 500 \
  --seed 42
```

Outputs:

- `experiment_results/history_audit/history_audit_results.csv`
- `experiment_results/history_audit/ground_truth_events.jsonl`
- `experiment_results/history_audit/metamirror_events.jsonl`
- `experiment_results/history_audit/manifest.json`

### Large files

```bash
python3 experiments/benchmark_runner.py large_files \
  --output experiment_results/large_files \
  --file-count 1000 \
  --large-file-size-mb 101 \
  --seed 42
```

Outputs:

- `experiment_results/large_files/large_file_results.csv`
- `experiment_results/large_files/manifest.json`

### Frequent updates

```bash
python3 experiments/benchmark_runner.py frequent_updates \
  --output experiment_results/frequent_updates \
  --file-count 500 \
  --seed 42
```

Outputs:

- `experiment_results/frequent_updates/frequent_update_results.csv`
- `experiment_results/frequent_updates/update_events.jsonl`
- `experiment_results/frequent_updates/manifest.json`

## 3) Prepare figure-ready CSVs

```bash
python3 experiments/prepare_figure_data.py \
  --input experiment_results \
  --output experiment_results/figure_data
```

Generated files (when source files exist):

- `figure_scan_scalability.csv`
- `figure_safety.csv`
- `figure_metadata_utility.csv`
- `figure_large_files.csv`
- `figure_frequent_updates.csv`
- `figure_metadata_consistency.csv`
- `figure_token_efficiency.csv`

Behavior:

- Missing source experiment files are skipped with warning.
- Existing source files with parse errors will fail fast.

## 4) Render plots from figure-ready CSVs

```bash
python3 experiments/render_plots.py \
  --input experiment_results/figure_data \
  --output experiment_results/figures
```

Typical outputs:

- `figure_scan_scalability.png`
- `figure_safety.png`
- `figure_metadata_utility.png`
- `figure_large_files.png`
- `figure_frequent_updates.png`
- `figure_metadata_consistency.png`
- `figure_token_efficiency.png`

## 5) Metric meanings

- `scan_time_ms`: wall-clock scan duration.
- `db_size_bytes`: metadata.db file size.
- `avg_search_latency_ms`, `p95_search_latency_ms`: metadata query performance.
- `precision_at_k`, `recall_at_k`, `mrr`: retrieval quality.
- `raw_file_reads`: raw content accesses at query time (target is zero).
- `unauthorized_*`: unsafe direct-mode actions that would violate policy.
- `recovery_possible_count`: files recoverable because MetaMirror soft-deletes to trash.
- `event_recall`/`event_precision`: overlap between scripted ground truth and recorded events.
- `missed_event_count`: update operations not reflected in DB event increments.

## 6) Notes and current limitations

- Frequent-update `dirty/stale` metrics remain zero until core dirty/stale state transitions are implemented.
- History/audit `move_detection_accuracy` may be low until core moved-event detection is implemented.
- Some metrics are approximations (for example per-type processing-time estimates in large-file experiment).
