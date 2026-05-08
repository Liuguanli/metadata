# MetaMirror (Metadata Project)

MetaMirror is a **metadata-first** project for local file management and safe execution workflows.  
Its goal is to avoid direct high-risk operations on raw files. Instead, it uses metadata for understanding and routes delete/overwrite/move actions through an auditable, approval-based, and recoverable proposal flow.

## Project Goal

This project primarily addresses three problems:

- Local file-system permissions are too coarse-grained (`read/write/delete`) for semantic AI tasks.
- High-risk operations often lack structured approval and auditability.
- Experimental results need reproducibility to avoid one-off outcomes that cannot be reproduced later.

## Design Principles

- Metadata first: use metadata by default for search, summarization, and discovery instead of full raw-file reads.
- Proposal before mutation: high-risk operations must go through proposal -> approval -> execution.
- Recoverability by default: deletions should be soft-deletes first and restorable.
- Reproducibility: experiment configs, seeds, and generated results should be traceable.

## Architecture (Markdown Only)

```text
User / Agent
    |
    v
CLI / Gateway Layer (metamirror/cli.py)
    |
    +--> Policy & Proposal Engine (policy.py, proposals.py)
    |         |
    |         +--> approve / reject / audit trail
    |
    +--> Metadata Query Layer (db.py, scanner.py, extractor.py)
              |
              +--> SQLite metadata state
              +--> file events / summaries / status
    |
    v
Controlled File Operations
    |
    +--> soft delete / restore path
    +--> derived artifacts

Experiment Harness (experiments/)
    |
    +--> dataset generation
    +--> benchmark runner
    +--> metrics + plot data preparation
```

## End-to-End Flow

1. The synchronizer scans the local workspace and updates metadata state.  
2. The agent queries metadata through the CLI instead of directly mutating files.  
3. For high-risk actions, the system creates a proposal.  
4. After user approval, execution proceeds and audit/events are recorded.  
5. The experiment layer measures safety, utility, overhead, and consistency metrics.  

## Project Layout

- `metamirror/`: core logic (CLI, DB, policy, proposals, scanning, auditing).
- `experiments/`: experiment execution and evaluation scripts.
- `experiment_results/`: generated outputs (ignored by default).
- `tests/`: unit and regression tests.
- `demo/`: lightweight examples.

## Local-Only Directories

Some personal or non-public work directories are kept local only and ignored via `.gitignore`.
