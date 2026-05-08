# MetaMirror (Metadata Project)

This repository is the code and experiment workspace for the metadata-management paper project.

## Code-Paper Sync

To keep code and paper synchronized, we use a fixed external paper workspace path:

- Overleaf local workspace: `/Users/guanlil1/Dropbox/应用/Overleaf/Metadata-management`

Sync convention:

1. Code/experiment changes are implemented in this repository first.
2. Paper claims/figures/tables are then updated in the Overleaf workspace above.
3. Any paper-facing change in code should be logged in [`paper/README.md`](paper/README.md).

Review protocol for submission-quality evolution:

4. Run a VLDB-style three-role review cycle (`reader`, `reviewer`, `meta-reviewer`) using [`paper/VLDB_VISION_PLAYBOOK.md`](paper/VLDB_VISION_PLAYBOOK.md).
5. Store each cycle in `paper/reviews/<cycle-id>.md`.

## Project Layout

- `metamirror/`: core CLI and metadata logic
- `experiments/`: experiment runners and figure-data preparation
- `experiment_results/`: generated outputs
- `tests/`: test suite
- `paper/`: paper-sync notes and update checklist (no paper source files stored here)
