# MetaMirror Implementation Spec (PoC v0.1)

## Scope

Workspace-local metadata mirror with safe proposal-based deletion.

## Workspace layout

```
.metamirror/
  metadata.db
  audit.jsonl
  derived/
  trash/
```

## Required CLI commands

- `python3 -m metamirror init <workspace>`
- `python3 -m metamirror scan <workspace>`
- `python3 -m metamirror watch <workspace> [--interval S] [--max-cycles N]`
- `python3 -m metamirror search <workspace> "<query>" [--limit N]`
- `python3 -m metamirror duplicates <workspace>`
- `python3 -m metamirror recent <workspace> --days N [--limit N]`
- `python3 -m metamirror propose-delete <workspace> <file_id> --reason "..." --evidence "..."`
- `python3 -m metamirror proposals <workspace> [--status STATUS] [--limit N]`
- `python3 -m metamirror approve <workspace> <proposal_id>`
- `python3 -m metamirror reject <workspace> <proposal_id>`
- `python3 -m metamirror restore <workspace> <file_id> [--target-path REL_PATH]`
- `python3 -m metamirror expire <workspace> <proposal_id>`
- `python3 -m metamirror status <workspace>`

## Scan behavior

- Excludes `.git/`, `.metamirror/`, `node_modules/`, `.venv/`, `__pycache__/`, `.DS_Store`.
- Computes `sha256` for files `<=100MB`.
- Sets `sha256=NULL` and `metadata_status=basic_only` for files `>100MB`.
- Inserts/updates `files`.
- Inserts default `file_policy` row per file when missing.
- Marks missing files as `status=missing` instead of deleting DB rows.
- Writes `created`, `modified`, `missing` events.

## Summary extraction (MVP placeholder)

- For `.txt`, `.md`, `.py`, `.sql`, `.json`, `.yaml`, `.yml`: stores a first-4KB normalized preview in `file_metadata.summary`.
- Unsupported types remain basic metadata only.
- No external LLM APIs.

## Safety requirements

- No hard delete command exists.
- Raw file delete only through proposal workflow:
  - `propose-delete` creates pending proposal only.
  - `approve` moves file to `.metamirror/trash/<date>/` and marks `soft_deleted` with proposal status `approved`.
  - `reject` marks proposal rejected.
  - `expire` marks pending proposal as `expired` without touching raw file.
  - `restore` moves a soft-deleted file back to an active workspace path.
- All operations append audit records.
