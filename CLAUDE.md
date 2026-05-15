# MetaMirror — CLAUDE.md

## What this project is

MetaMirror is a Python library and CLI for metadata-first local file management.
High-risk file operations (delete, overwrite, move) go through a proposal → approval → execution flow backed by an audit trail.

## Install & setup

```bash
pip install -e .
python -m pytest tests/ -x -q          # run tests
```

## Module responsibilities

| Module | Role |
|--------|------|
| `metamirror/cli.py` | Entry point; routes commands |
| `metamirror/db.py` | SQLite metadata store |
| `metamirror/scanner.py` | File system scanning & indexing |
| `metamirror/extractor.py` | Metadata extraction per file type |
| `metamirror/policy.py` | Risk classification rules |
| `metamirror/proposals.py` | Proposal lifecycle (create/approve/reject) |
| `metamirror/audit.py` | Immutable event log |
| `metamirror/watcher.py` | File system event watching |

## Full CLI command reference

```bash
python -m metamirror init <workspace>
python -m metamirror scan <workspace>
python -m metamirror watch <workspace> [--interval S] [--max-cycles N]
python -m metamirror search <workspace> "<query>" [--limit N]
python -m metamirror duplicates <workspace>
python -m metamirror recent <workspace> --days N [--limit N]
python -m metamirror status <workspace>
python -m metamirror propose-delete <workspace> <file_id> --reason "..." --evidence "..."
python -m metamirror proposals <workspace> [--status pending|approved|rejected|executed|expired] [--limit N]
python -m metamirror approve <workspace> <proposal_id>
python -m metamirror reject <workspace> <proposal_id>
python -m metamirror expire <workspace> <proposal_id>
python -m metamirror restore <workspace> <file_id> [--target-path REL_PATH]
```

See `CLI_USAGE.md` for runnable examples with real SQLite queries.

## Database schema overview

Five tables in `.metamirror/metadata.db`:

| Table | Key fields |
|-------|-----------|
| `files` | `file_id`, `path`, `sha256`, `status`, `metadata_status`, `dirty` |
| `file_metadata` | `file_id`, `summary`, `tags`, `entities`, `topics` |
| `file_policy` | `file_id`, `sensitivity`, `ai_can_*`, `delete_requires_approval` |
| `file_events` | `event_id`, `file_id`, `event_type`, `actor`, `created_at` |
| `action_proposals` | `proposal_id`, `file_id`, `action_type`, `status`, `created_by` |

**`files.status`** values: `active`, `missing`, `deleted`, `soft_deleted`

**`files.metadata_status`** values: `basic_only`, `queued`, `indexing`, `ready`, `stale`, `failed`, `skipped`

**`file_events.event_type`** values: `created`, `modified`, `moved`, `missing`, `deleted`, `soft_deleted`, `restored`, `ai_proposed_delete`, `user_approved_delete`, `user_rejected_delete`

**`action_proposals.status`** values: `pending`, `approved`, `rejected`, `executed`, `expired`

## Scan behavior

- Excluded paths: `.git/`, `.metamirror/`, `node_modules/`, `.venv/`, `__pycache__/`, `.DS_Store`
- Files ≤ 100 MB: compute `sha256`
- Files > 100 MB: `sha256 = NULL`, `metadata_status = basic_only`
- Text types (`.txt`, `.md`, `.py`, `.sql`, `.json`, `.yaml`, `.yml`): first 4 KB stored as `summary` placeholder
- Missing DB entries stay in DB with `status = missing` — never hard-deleted from DB

## Safety invariants

- **No hard delete** — the only way to remove a file is the proposal → approve → soft-delete workflow.
- `propose-delete` creates a proposal row and event; the raw file is **not** touched.
- `approve` moves the file to `.metamirror/trash/<date>/` and sets `status = soft_deleted`.
- `reject` only changes proposal status and writes an event; raw file is unchanged.
- `expire` transitions a pending proposal to `expired`; raw file is unchanged.
- `restore` moves a soft-deleted file back to an active path and logs `restored`/`moved` events.
- Every metadata-changing operation writes an `audit.jsonl` entry.

## Experiments

```bash
python experiments/benchmark_runner.py --help
python experiments/benchmark_runner.py scalability --output experiment_results/scalability ...
python experiments/benchmark_runner.py metadata_consistency --output experiment_results/metadata_consistency ...
python experiments/prepare_figure_data.py --input experiment_results --output experiment_results/figure_data
python experiments/render_plots.py --input ... --output ...
```

Results land in `experiment_results/` (not committed).

**Experiment constraints (do not break these):**
- No paper text, LaTeX, bibliography, or Overleaf files in this repo.
- No plot generation inside `benchmark_runner.py` or `prepare_figure_data.py`; plotting is separate (`render_plots.py`).
- Destructive operations (delete, move, overwrite) only inside generated temporary workspaces — never on the user's real files.
- Use deterministic random seeds for reproducibility.
- Every experiment writes a `manifest.json` with `git_commit_hash`, `python_version`, `random_seed`, and `experiment_parameters`.

## Testing

Tests live in `tests/`. Run with `pytest`.

```bash
pytest -x -q                        # all tests, stop on first failure
pytest -k init -q                   # init tests
pytest -k scan -q                   # scan tests
pytest -k missing -q                # missing-file behavior
pytest -k duplicate -q              # duplicate detection
pytest -k proposal -q               # proposal + approval flow
pytest -k exclude -q                # excluded-path behavior
pytest tests/test_experiments_metadata_consistency.py -q
```

**Integration tests hit the real SQLite DB — do not mock the database layer.**

## Paper writing

**Target:** VLDB Vision track — metadata management / data governance / new data systems.

**Canonical locations:**

| Artifact | Path |
|----------|------|
| LaTeX source | `private_paper/VLDB.tex` (Overleaf project, synced via Dropbox) |
| Overleaf workspace | `/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management` |
| Compiled PDF | `private_paper/VLDB.pdf` |
| Figures | `private_paper/figures/` |
| Review records | `private_paper/reviews/` |
| Playbook | `private_paper/VLDB_VISION_PLAYBOOK.md` |
| Iterative plan | `private_paper/PLAN_6_ROUNDS_ITERATIVE.md` |

**Manuscript structure (8 sections):**
1. Introduction
2. Problem Model and Design Principles
3. Related Work
4. MetaMirror Architecture
5. Proof-of-Concept Implementation
6. Preliminary Evaluation
7. Open Challenges and Roadmap
8. Conclusion

**Figure sync to Overleaf:**
```bash
bash private_paper/sync_figure_to_overleaf.sh \
  --source <local-image> \
  --target-name <name> \
  --caption "<caption>" \
  --label <fig:label>
```

**Review cycle:**
```bash
bash private_paper/new_review_cycle.sh <cycle-id>
# e.g. c2026-05-15-r1
# Fill in private_paper/reviews/<cycle-id>.md
```

Each review cycle runs three roles (defined in the playbook):
- **Reader** — clarity, flow, accessibility
- **Reviewer (Technical)** — novelty, soundness, evidence quality
- **Meta-Reviewer** — synthesizes into ranked action list; decides accept-cycle or revise-again

Each review record must include three independent reviewer blocks (A/B/C), a weakness-to-edit mapping table, and a compact scorecard (Novelty/Soundness/Evidence/Clarity/Overall, 1–5).

**Code → paper sync rule:** every substantial code or experiment change requires:
1. Overleaf update (figures, tables, or text in `VLDB.tex`)
2. A completed review cycle record in `private_paper/reviews/`

**VLDB Vision framing rules:**
- Claims scoped as vision + preliminary evidence, not full validation.
- Emphasize architecture-level shift: metadata as control plane for agent-file interaction.
- Keep claims falsifiable and measurable.
- Separate clearly what is demonstrated now (prototype + preliminary results) from what is projected.

**Quality standards — read before any paper revision pass:**

`private_paper/WRITING_STANDARDS.md` defines hard rules for all four known quality gaps:

1. **Citations** — every factual/comparative claim needs `\cite{}`; no `\cite{TODO}` placeholders; minimum coverage table must be satisfied.
2. **Figures** — axis labels ≥ 11 pt, tick labels ≥ 9 pt; every caption ends with a `Takeaway:` sentence; captions width-matched to figure.
3. **Writing** — camera-ready: zero TODO/FIXME/[FILL] placeholders; abstract ≤ 5 sentences (problem→gap→approach→result→implication); contributions numbered, concrete, measurable; active voice for core claims.
4. **Plots** — Okabe-Ito color palette; key result annotated; error bars when multiple runs; each plot's takeaway written before the plot is generated.

Every revision cycle must run the 13-item checklist in `WRITING_STANDARDS.md` and report which items pass/fail before the cycle is closed.

**Loops** — invoke with `/loop Follow private_paper/loops/<name>.md`:

| Loop file | Fixes | Stop condition |
|---|---|---|
| `citation_loop.md` | Missing `\cite{}`, refs.bib entries | Checklist items 1–3 pass |
| `writing_loop.md` | Placeholders, weak prose, structure | Checklist items 7–9 pass |
| `figure_loop.md` | Font sizes, captions, Takeaway lines | Checklist items 4–6 pass |
| `plot_loop.md` | Palette, annotations, error bars | Checklist items 10–12 pass |
| `full_paper_loop.md` | All four above + Reader/Reviewer/Meta-Reviewer cycle | All 13 items pass + `accept-cycle` verdict |

## Development conventions

- Follow TDD: write a failing test before implementing a feature.
- No comments unless the *why* is non-obvious (hidden constraint, workaround for a specific bug).
- `file_id` is a UUID generated at insert time and never changes even if a file is moved.
- All new CLI commands must append an audit record via `metamirror/audit.py`.
- The `experiments/` layer must remain independent from the core library — no imports from `experiments/` inside `metamirror/`.
