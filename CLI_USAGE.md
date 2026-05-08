# MetaMirror CLI Usage

Install once (editable mode):

```bash
python3 -m pip install -e .
```

Then use either console mode or module mode:

```bash
metamirror <command> ...
```

```bash
python3 -m metamirror <command> ...
```

Examples below keep module mode:

```bash
python3 -m metamirror <command> ...
```

## 1) Initialize workspace

```bash
python3 -m metamirror init .
```

## 2) Scan files into metadata DB

```bash
python3 -m metamirror scan .
```

Or continuously scan:

```bash
python3 -m metamirror watch . --interval 2.0 --max-cycles 5
```

## 3) Show workspace status

```bash
python3 -m metamirror status .
```

## 4) Search files (filename/path/summary/tags)

```bash
python3 -m metamirror search . "report" --limit 20
```

## 5) Find duplicates by sha256

```bash
python3 -m metamirror duplicates .
```

## 6) Show recent events

```bash
python3 -m metamirror recent . --days 7 --limit 50
```

## 7) Propose safe delete (no raw deletion)

First get a file id:

```bash
file_id=$(sqlite3 .metamirror/metadata.db "select file_id from files where path='docs/example.txt' limit 1;")
```

Create proposal:

```bash
python3 -m metamirror propose-delete . "$file_id" --reason "duplicate" --evidence "same hash as canonical copy"
```

## 8) List proposals

```bash
python3 -m metamirror proposals . --limit 20
python3 -m metamirror proposals . --status pending --limit 20
python3 -m metamirror proposals . --status approved --limit 20
python3 -m metamirror proposals . --status expired --limit 20
```

## 9) Approve proposal (soft-delete to trash)

First get proposal id:

```bash
proposal_id=$(sqlite3 .metamirror/metadata.db "select proposal_id from action_proposals where status='pending' order by created_at desc limit 1;")
```

Approve:

```bash
python3 -m metamirror approve . "$proposal_id"
```

## 10) Reject proposal

```bash
python3 -m metamirror reject . "$proposal_id"
```

## 11) Restore a soft-deleted file

Find a soft-deleted file id:

```bash
file_id=$(sqlite3 .metamirror/metadata.db "select file_id from files where status='soft_deleted' order by last_seen_at desc limit 1;")
```

Restore:

```bash
python3 -m metamirror restore . "$file_id"
```

Optional custom target path:

```bash
python3 -m metamirror restore . "$file_id" --target-path docs/restored_example.txt
```

## 12) Expire a pending proposal

```bash
python3 -m metamirror expire . "$proposal_id"
```

## Notes

- No hard delete is exposed.
- Approved delete moves file into `.metamirror/trash/<date>/`.
- Approve flow now emits `moved` and `deleted` event types (plus soft-delete events).
- Restore flow emits `restored` and `moved` event types.
