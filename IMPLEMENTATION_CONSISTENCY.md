# Implementation Consistency Checklist

Date: 2026-05-01

## Spec source

- [`IMPLEMENTATION_SPEC.md`](./IMPLEMENTATION_SPEC.md)

## Command coverage

- [x] `init`
- [x] `scan`
- [x] `watch` (polling loop with interval)
- [x] `search`
- [x] `duplicates`
- [x] `recent`
- [x] `propose-delete`
- [x] `proposals`
- [x] `approve`
- [x] `reject`
- [x] `restore`
- [x] `expire`
- [x] `status`

## Data behavior coverage

- [x] Excluded paths are skipped by scanner.
- [x] Small files (`<=100MB`) get `sha256`.
- [x] Large files (`>100MB`) keep `sha256=NULL`.
- [x] Missing files are marked `missing` and retained in DB.
- [x] Default `file_policy` inserted when missing.
- [x] Text preview summary stored for supported text extensions.

## Safety coverage

- [x] No hard-delete command is exposed.
- [x] `propose-delete` does not move/delete raw file.
- [x] `approve` performs soft-delete into `.metamirror/trash/<date>/`.
- [x] `reject` only changes proposal status and writes event/audit.
- [x] `restore` moves soft-deleted file back to active path and logs restore events.
- [x] `expire` supports controlled pending->expired proposal transition.
- [x] Audit log is written for operational commands.

## Verification commands

```bash
pytest -k init -q
pytest -k scan -q
pytest -k missing -q
pytest -k duplicate -q
pytest -k proposal -q
pytest -k exclude -q
```
