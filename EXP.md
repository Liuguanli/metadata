You are working on the MetaMirror project.

MetaMirror is a workspace-local, metadata-first, AI-safe local file mirror. The core system already implements or should implement:
- `.metamirror/metadata.db`
- workspace scanning
- metadata synchronization
- metadata search
- duplicate detection
- file event recording
- proposal-based deletion
- approval/rejection workflow
- soft-delete into `.metamirror/trash/`
- audit logging

Your task is to add an experimental benchmarking layer to this project.

Important constraints:
1. Do not add any paper text, LaTeX files, Overleaf files, or bibliography files.
2. Do not generate plots or figures.
3. Do not modify the paper.
4. Do not hard-code paper-specific claims.
5. The project should only generate clean experimental data files, such as CSV, JSONL, and JSON manifests.
6. All experiments must run only on generated temporary/synthetic workspaces or explicitly provided test workspaces.
7. Never hard delete user files.
8. Never run destructive operations outside temporary generated workspaces.
9. Keep the experimental code modular and reproducible.
10. Use deterministic random seeds wherever possible.

The goal is to produce figure-ready data for an external paper, while keeping the paper and the codebase independent.

Please implement the experimental layer in phases.

============================================================
PHASE 1: Experimental framework
============================================================

Create an `experiments/` directory with the following structure:

experiments/
  benchmark_runner.py
  dataset_generator.py
  metrics.py
  prepare_figure_data.py
  README.md

Create an output directory when experiments run:

experiment_results/

The benchmark runner should support named experiments:

python experiments/benchmark_runner.py scalability ...
python experiments/benchmark_runner.py metadata_utility ...
python experiments/benchmark_runner.py safety ...
python experiments/benchmark_runner.py history_audit ...
python experiments/benchmark_runner.py large_files ...
python experiments/benchmark_runner.py frequent_updates ...

Every experiment should write:

experiment_results/<experiment_name>/manifest.json

The manifest must include:
- experiment_name
- timestamp
- git_commit_hash if available
- python_version
- operating_system
- workspace_path
- output_path
- random_seed
- experiment_parameters
- generated_files
- result_files
- notes

Every experiment should also write result files in CSV and/or JSONL format.

Do not generate plots.

============================================================
PHASE 2: Synthetic workspace generator
============================================================

Implement or extend:

experiments/dataset_generator.py

It should create synthetic workspaces with configurable scale and file composition.

Required command:

python experiments/dataset_generator.py \
  --output <workspace> \
  --num-files 1000 \
  --duplicate-ratio 0.1 \
  --large-file-ratio 0.05 \
  --large-file-size-mb 101 \
  --structure mixed \
  --seed 42

Support file types:
- `.txt`
- `.md`
- `.py`
- `.json`
- `.csv`
- `.pdf` placeholder files
- `.bin` large binary placeholder files

Support directory structures:
- shallow
- deep
- mixed

Duplicate generation:
- If duplicate-ratio is 0.1, approximately 10% of files should have identical content to another file.
- Duplicates should have different filenames or paths.
- Record duplicate ground truth in the manifest.

Large file generation:
- Large files should exceed the hash threshold used by MetaMirror, e.g., >100MB.
- Use sparse files if the platform supports it, or document fallback behavior.
- Support `--large-file-size-mb`.

Write:

<workspace>/synthetic_manifest.json

The manifest should include:
- total files
- total directories
- duplicate groups
- expected duplicate count
- expected large file count
- random seed
- file type distribution
- topic labels if generated

Add tests for:
- correct number of files
- reproducibility with same seed
- duplicate groups are actually identical by content
- generated manifest is valid JSON

============================================================
PHASE 3: Scalability experiment
============================================================

Implement experiment:

scalability

Command example:

python experiments/benchmark_runner.py scalability \
  --output experiment_results/scalability \
  --file-counts 100 1000 5000 10000 \
  --duplicate-ratio 0.1 \
  --repeats 3 \
  --seed 42

For each file count:
1. Generate a fresh synthetic workspace.
2. Run `metamirror init`.
3. Run `metamirror scan`.
4. Run 10 fixed metadata search queries.
5. Run duplicate detection.

Measure:
- initial scan time
- metadata.db size
- number of active files
- number of files with sha256
- number of files skipped for hashing
- average search latency
- p95 search latency
- duplicate detection time
- total workspace size

Export:

experiment_results/scalability/scalability_results.csv

CSV columns:
- run_id
- file_count
- duplicate_ratio
- seed
- repeat_id
- total_size_bytes
- scan_time_ms
- db_size_bytes
- active_files
- hashed_files
- skipped_hash_files
- avg_search_latency_ms
- p95_search_latency_ms
- duplicate_detection_time_ms

Do not generate plots.

============================================================
PHASE 4: Metadata-first utility experiment
============================================================

Implement experiment:

metadata_utility

Goal:
Evaluate whether file discovery and recommendation tasks can be answered using metadata only, without reading raw file contents during query time.

Generate synthetic workspaces with topic categories:
- research
- finance
- visa
- code
- photos
- logs
- contracts

Encode topic signals in:
- filenames
- small text contents
- generated summaries
- tags

Insert summaries and tags into the MetaMirror metadata database.

Tasks:
For each topic query, such as:
- "find research papers about spatial index"
- "find visa documents"
- "find finance records"
- "find code files related to database"
- "find contracts"

Run metadata search and compare returned files against the synthetic manifest ground truth.

Metrics:
- precision@5
- precision@10
- recall@10
- mean reciprocal rank
- number of raw file reads during query time, should be zero
- query latency

Export:

experiment_results/metadata_utility/metadata_utility_results.csv

CSV columns:
- query_id
- query_text
- topic
- k
- precision_at_k
- recall_at_k
- mrr
- raw_file_reads
- query_latency_ms

Do not use any external LLM API.
Do not generate plots.

============================================================
PHASE 5: Safety experiment
============================================================

Implement experiment:

safety

Goal:
Compare direct filesystem operations with MetaMirror proposal-based operations.

Setup:
1. Generate a synthetic workspace with:
   - normal files
   - duplicate files
   - sensitive files
   - important raw files
2. Mark sensitive and important files in `file_policy`.
3. Define destructive task intents:
   - delete duplicate files
   - clean old files
   - remove large unused files
   - rename files into organized folders
   - move files into archive
   - overwrite generated summaries

Baselines:

A. Direct mode:
- Simulate direct filesystem operations on a temporary copied workspace only.
- Apply delete/move/overwrite according to the scripted destructive intents.
- Never run this mode on the user's real workspace.

B. MetaMirror mode:
- Run equivalent operations through MetaMirror APIs.
- Direct deletion should not occur.
- Destructive operations should become pending proposals.
- Approved operations should soft-delete only.

Metrics:
- attempted_destructive_ops
- direct_deleted_files
- direct_overwritten_files
- direct_moved_files
- metamirror_direct_deleted_files
- metamirror_created_proposals
- metamirror_soft_deleted_files
- unauthorized_delete_count
- unauthorized_overwrite_count
- recovery_possible_count
- audit_event_count

Export:

experiment_results/safety/safety_results.csv
experiment_results/safety/safety_events.jsonl

Do not generate plots.
Do not hard delete user files.

============================================================
PHASE 6: History and audit experiment
============================================================

Implement experiment:

history_audit

Goal:
Evaluate whether MetaMirror can answer historical file-system questions from metadata.db and audit logs.

Procedure:
1. Generate a synthetic workspace.
2. Run init and scan.
3. Apply a scripted sequence of operations:
   - create files
   - modify files
   - move files
   - delete files externally in a temporary workspace
   - propose delete through MetaMirror
   - approve some proposals
   - reject some proposals
4. Run scan/reconcile after operations.
5. Query the database to answer:
   - files created in last N minutes
   - files modified in last N minutes
   - files moved
   - files marked missing
   - files soft_deleted
   - proposals pending/approved/rejected
6. Compare query answers against a ground-truth operation log generated by the experiment script.

Metrics:
- event_recall
- event_precision
- missing_detection_accuracy
- move_detection_accuracy
- proposal_status_accuracy
- audit_completeness

Export:

experiment_results/history_audit/history_audit_results.csv
experiment_results/history_audit/ground_truth_events.jsonl
experiment_results/history_audit/metamirror_events.jsonl

Do not generate plots.

============================================================
PHASE 7: Large-file experiment
============================================================

Implement experiment:

large_files

Goal:
Evaluate the cost and behavior of shallow metadata extraction for large files.

Generate workspaces with different large-file ratios:
- 0%
- 1%
- 5%
- 10%
- 20%

Large files should be binary placeholder files with configurable size:
- default 101MB
- configurable via `--large-file-size-mb`

For each setting:
1. Generate workspace.
2. Run scan.
3. Measure:
   - scan time
   - number of large files
   - number of files skipped for full hashing
   - metadata_status distribution
   - DB size
   - total raw workspace size
   - average processing time per file type if available

Export:

experiment_results/large_files/large_file_results.csv

CSV columns:
- run_id
- file_count
- large_file_ratio
- large_file_size_mb
- scan_time_ms
- db_size_bytes
- total_workspace_size_bytes
- large_files
- skipped_hash_files
- basic_only_files
- ready_files
- avg_processing_time_small_file_ms
- avg_processing_time_large_file_ms

Do not generate plots.

============================================================
PHASE 8: Frequent-update experiment
============================================================

Implement experiment:

frequent_updates

Goal:
Evaluate how MetaMirror handles frequently modified files using dirty/stale metadata states.

Procedure:
1. Generate a workspace with text files, log files, code files, and temporary files.
2. Run initial scan.
3. Apply repeated updates to selected files at different update rates:
   - low: 1 update/sec
   - medium: 10 updates/sec
   - high: 100 updates/sec
4. If the project implements debounce, measure its effect.
5. After updates, run reconciliation.

Metrics:
- number of filesystem updates
- number of DB updates
- number of files marked dirty
- number of files marked stale
- time until metadata becomes ready again
- event-to-db latency
- missed event count
- reconciliation corrections

Export:

experiment_results/frequent_updates/frequent_update_results.csv
experiment_results/frequent_updates/update_events.jsonl

Do not generate plots.

============================================================
PHASE 9: Figure-ready CSV preparation
============================================================

Implement:

experiments/prepare_figure_data.py

Input:
experiment_results/

Output:
experiment_results/figure_data/

Generate these files when source experiment files exist:

1. figure_scan_scalability.csv
columns:
- file_count
- mean_scan_time_ms
- std_scan_time_ms
- mean_db_size_bytes
- mean_search_latency_ms
- mean_duplicate_detection_time_ms

2. figure_safety.csv
columns:
- baseline
- unauthorized_delete_count
- unauthorized_overwrite_count
- created_proposals
- soft_deleted_files
- recovery_possible_count

3. figure_metadata_utility.csv
columns:
- query_type
- precision_at_5
- precision_at_10
- recall_at_10
- mrr
- raw_file_reads

4. figure_large_files.csv
columns:
- large_file_ratio
- scan_time_ms
- skipped_hash_files
- basic_only_files
- db_size_bytes

5. figure_frequent_updates.csv
columns:
- update_rate
- db_update_count
- stale_file_count
- event_to_db_latency_ms
- reconciliation_corrections

The script should be robust:
- If an experiment result file is missing, skip it and print a warning.
- Do not fail unless there is a parsing error in an existing file.
- Do not generate plots.

============================================================
PHASE 10: Tests and documentation
============================================================

Add or update tests for:
- synthetic workspace generation
- experiment manifest generation
- scalability experiment smoke test
- metadata utility ground-truth evaluation
- safety experiment does not hard delete user files
- proposal-based soft-delete behavior
- figure-ready CSV preparation

Add:

experiments/README.md

The README should explain:
- how to generate synthetic workspaces
- how to run each experiment
- what output files are generated
- what each metric means
- how to prepare figure-ready CSVs
- that the repository does not include paper or plotting code

============================================================
Implementation strategy
============================================================

Please implement this incrementally.

Start with:
1. Experimental framework
2. Synthetic dataset generator
3. Scalability experiment
4. Safety experiment

After these pass tests, continue with:
5. Metadata utility
6. Large-file experiment
7. History/audit
8. Frequent updates
9. Figure-ready CSV preparation

At the end of each phase:
- run the relevant tests
- show the generated result file schemas
- summarize what was implemented
- mention any limitations or assumptions

Again:
Do not add paper text.
Do not generate plots.
Do not hard delete user files.
Do not run destructive tests outside generated temporary workspaces.