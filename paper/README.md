# Paper Sync Notes

This folder is for managing code-paper synchronization metadata only.
Do not store LaTeX source, bibliography, or paper text here.

## Canonical Paper Workspace

- `/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management`

## VLDB Vision Workflow

Use the playbook:

- `paper/VLDB_VISION_PLAYBOOK.md`
- `paper/PLAN_6_ROUNDS_ITERATIVE.md`

Create a new review cycle file:

- `bash paper/new_review_cycle.sh <cycle-id>`
- Example: `bash paper/new_review_cycle.sh c2026-05-08-v1`

Then complete the generated file under:

- `paper/reviews/<cycle-id>.md`

## Figure Sync to Overleaf

Use:

- `bash paper/sync_figure_to_overleaf.sh --source <local-image> --target-name <name> --caption "<caption>" --label <fig:label>`

This script will:
1. copy the image into Overleaf `figures/`
2. append the figure block into `VLDB.tex` (before `\bibliography{}` when found)
3. print the inserted LaTeX block

## Update Checklist (Code -> Paper)

1. Record what changed in code (module/script/result file).
2. Record which figure/table/section in paper must be updated.
3. Confirm whether experiment outputs were regenerated.
4. Mark sync status as `pending` or `done`.

## Change Log Template

- Date:
- Code change:
- Paper impact:
- Overleaf update status:
- Notes:

## Sync Log

- Date: 2026-05-08
- Code change:
  - Added six-round iterative workflow and review records.
  - Added figure-sync workflow and synced preliminary safety/scalability figures.
  - Updated `VLDB.tex` with revised abstract/contributions, real tables, and preliminary results analysis.
- Paper impact:
  - Draft now has fewer placeholders and stronger claim-evidence alignment.
- Overleaf update status:
  - done
- Notes:
  - Pending c2 priorities: threat model paragraph, comparison table, reproducibility protocol paragraph.

- Date: 2026-05-08 (reviewer-focused revision)
- Code change:
  - Added 3-reviewer detailed review report with strong/weak/detailed evaluation.
  - Updated `VLDB.tex` to address reviewer weaknesses (positioning table, reproducibility protocol, threat model subsection).
- Paper impact:
  - Reduced novelty-risk and validity-risk in reviewer perspective.
- Overleaf update status:
  - done
- Notes:
  - Next step: tighten baseline-scope wording and page-budget compression.

- Date: 2026-05-08 (structure + implementation-focused revision)
- Code change:
  - Rewrote introduction for stronger first-page hook.
  - Compressed related work to short high-density form while retaining citation coverage.
  - Removed command-list verbosity from PoC section and emphasized metadata-management implementation path.
  - Kept one overview figure placeholder and one concrete implementation-path placeholder.
  - Upgraded round requirements and initialized c2 review files.
- Paper impact:
  - Manuscript now better matches 7-8 section style and implementation-centered narrative.
- Overleaf update status:
  - done
- Notes:
  - c2 review files: `paper/reviews/c2026-05-08-r1c2.md` ... `c2026-05-08-r6c2.md`.

## Quick Rule

Every substantial code/experiment change must have:
1. Overleaf update in `/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management`
2. One completed review cycle record in `paper/reviews/`

## Reference Papers

- Vision example (saved local copy): `paper/references/vision_examples/p2180-liu.pdf`
