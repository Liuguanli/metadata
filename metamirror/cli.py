from __future__ import annotations

import argparse
from pathlib import Path

from metamirror.audit import ensure_audit_file, write_audit_event
from metamirror.db import (
    fetch_recent_events,
    fetch_status_summary,
    find_duplicates,
    init_db,
    list_proposals,
    metamirror_dir,
    search_files,
)
from metamirror.scanner import scan_workspace
from metamirror.watcher import watch_workspace
from metamirror.proposals import (
    approve_delete_proposal,
    create_delete_proposal,
    expire_proposal,
    reject_proposal,
    restore_soft_deleted_file,
)


def cmd_init(workspace: str) -> int:
    ws_path = Path(workspace).resolve()
    mm_dir = metamirror_dir(ws_path)
    derived_dir = mm_dir / "derived"
    summaries_dir = derived_dir / "summaries"
    trash_dir = mm_dir / "trash"

    mm_dir.mkdir(parents=True, exist_ok=True)
    derived_dir.mkdir(parents=True, exist_ok=True)
    summaries_dir.mkdir(parents=True, exist_ok=True)
    trash_dir.mkdir(parents=True, exist_ok=True)
    db_path = init_db(ws_path)
    audit_path = ensure_audit_file(ws_path)

    write_audit_event(
        workspace=ws_path,
        action="init",
        status="ok",
        details={
            "workspace": str(ws_path),
            "metadata_db": str(db_path),
            "audit_file": str(audit_path),
        },
    )

    print(f"Initialized MetaMirror workspace: {ws_path}")
    print(f"Metadata DB: {db_path}")
    print(f"Audit log:   {audit_path}")
    return 0


def cmd_scan(workspace: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    result = scan_workspace(ws_path)
    write_audit_event(
        workspace=ws_path,
        action="scan",
        status="ok",
        details={
            "workspace": str(ws_path),
            "scanned_files": result.scanned_files,
        },
    )
    print(f"Scanned files: {result.scanned_files}")
    return 0


def cmd_watch(workspace: str, interval: float, max_cycles: int | None) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = watch_workspace(
            workspace=ws_path,
            interval_seconds=interval,
            max_cycles=max_cycles,
        )
    except KeyboardInterrupt:
        write_audit_event(
            workspace=ws_path,
            action="watch",
            status="stopped",
            details={"workspace": str(ws_path), "reason": "keyboard_interrupt"},
        )
        print("Watch stopped by user.")
        return 0

    write_audit_event(
        workspace=ws_path,
        action="watch",
        status="ok",
        details={
            "workspace": str(ws_path),
            "cycles": result.cycles,
            "total_scanned_files": result.total_scanned_files,
            "interval_seconds": interval,
        },
    )
    print(
        f"Watch finished: cycles={result.cycles}, total_scanned_files={result.total_scanned_files}"
    )
    return 0


def cmd_status(workspace: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    summary = fetch_status_summary(ws_path)
    print(f"Workspace: {ws_path}")
    print(f"Total files:       {summary['total_files']}")
    print(f"Active files:      {summary['active_files']}")
    print(f"Missing files:     {summary['missing_files']}")
    print(f"Soft-deleted:      {summary['soft_deleted_files']}")
    print(f"Deleted:           {summary['deleted_files']}")
    print(f"Last seen at:      {summary['last_seen_at'] or 'N/A'}")
    return 0


def cmd_search(workspace: str, query: str, limit: int) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    results = search_files(ws_path, query=query, limit=limit)
    print(f"Results: {len(results)}")
    for row in results:
        print(
            " | ".join(
                [
                    row["file_id"] or "",
                    row["path"] or "",
                    row["filename"] or "",
                    row["summary"] or "",
                    row["tags"] or "",
                    row["status"] or "",
                    row["metadata_status"] or "",
                    row["sensitivity"] or "",
                ]
            )
        )
    return 0


def cmd_duplicates(workspace: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    groups = find_duplicates(ws_path)
    print(f"Duplicate groups: {len(groups)}")
    for group in groups:
        print(f"sha256={group['sha256']} count={group['count']}")
        for item in group["files"]:
            print(f"  - {item['path']} ({item['file_id']})")
    return 0


def cmd_recent(workspace: str, days: int, limit: int) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    events = fetch_recent_events(ws_path, days=days, limit=limit)
    print(f"Recent events: {len(events)} (days={days})")
    for event in events:
        print(
            " | ".join(
                [
                    event["created_at"] or "",
                    event["event_type"] or "",
                    event["file_id"] or "",
                    event["old_path"] or "",
                    event["new_path"] or "",
                    event["actor"] or "",
                    event["reason"] or "",
                ]
            )
        )
    return 0


def cmd_propose_delete(workspace: str, file_id: str, reason: str, evidence: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = create_delete_proposal(
            workspace=ws_path,
            file_id=file_id,
            reason=reason,
            evidence=evidence,
        )
    except ValueError as exc:
        write_audit_event(
            workspace=ws_path,
            action="propose_delete",
            status="error",
            details={"file_id": file_id, "error": str(exc)},
        )
        print(str(exc))
        return 2

    write_audit_event(
        workspace=ws_path,
        action="propose_delete",
        status="ok",
        details={
            "proposal_id": result.proposal_id,
            "file_id": result.file_id,
            "path": result.path,
            "reason": reason,
            "evidence": evidence,
        },
    )
    print(f"Created proposal: {result.proposal_id}")
    print(f"file_id: {result.file_id}")
    print(f"path:    {result.path}")
    print(f"status:  {result.status}")
    return 0


def cmd_proposals(workspace: str, status: str | None, limit: int) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    rows = list_proposals(ws_path, status=status, limit=limit)
    print(f"Proposals: {len(rows)}")
    for row in rows:
        print(
            " | ".join(
                [
                    row["proposal_id"] or "",
                    row["action_type"] or "",
                    row["file_id"] or "",
                    row["status"] or "",
                    row["created_by"] or "",
                    row["created_at"] or "",
                    row["approved_at"] or "",
                    row["executed_at"] or "",
                    row["reason"] or "",
                    row["evidence"] or "",
                    row["proposed_target"] or "",
                ]
            )
        )
    return 0


def cmd_approve(workspace: str, proposal_id: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = approve_delete_proposal(ws_path, proposal_id=proposal_id)
    except ValueError as exc:
        write_audit_event(
            workspace=ws_path,
            action="approve_proposal",
            status="error",
            details={"proposal_id": proposal_id, "error": str(exc)},
        )
        print(str(exc))
        return 2

    write_audit_event(
        workspace=ws_path,
        action="approve_proposal",
        status="ok",
        details={
            "proposal_id": result.proposal_id,
            "file_id": result.file_id,
            "old_path": result.old_path,
            "new_path": result.new_path,
            "proposal_status": result.proposal_status,
            "file_status": result.file_status,
        },
    )
    print(f"Approved proposal: {result.proposal_id}")
    print(f"file_id:          {result.file_id}")
    print(f"old_path:         {result.old_path}")
    print(f"new_path:         {result.new_path}")
    print(f"proposal_status:  {result.proposal_status}")
    print(f"file_status:      {result.file_status}")
    return 0


def cmd_reject(workspace: str, proposal_id: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = reject_proposal(ws_path, proposal_id=proposal_id)
    except ValueError as exc:
        write_audit_event(
            workspace=ws_path,
            action="reject_proposal",
            status="error",
            details={"proposal_id": proposal_id, "error": str(exc)},
        )
        print(str(exc))
        return 2

    write_audit_event(
        workspace=ws_path,
        action="reject_proposal",
        status="ok",
        details={
            "proposal_id": result.proposal_id,
            "file_id": result.file_id,
            "path": result.old_path,
            "proposal_status": result.proposal_status,
        },
    )
    print(f"Rejected proposal: {result.proposal_id}")
    print(f"file_id:           {result.file_id}")
    print(f"path:              {result.old_path}")
    print(f"proposal_status:   {result.proposal_status}")
    return 0


def cmd_restore(workspace: str, file_id: str, target_path: str | None) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = restore_soft_deleted_file(ws_path, file_id=file_id, restore_path=target_path)
    except ValueError as exc:
        write_audit_event(
            workspace=ws_path,
            action="restore_soft_deleted",
            status="error",
            details={"file_id": file_id, "target_path": target_path, "error": str(exc)},
        )
        print(str(exc))
        return 2

    write_audit_event(
        workspace=ws_path,
        action="restore_soft_deleted",
        status="ok",
        details={
            "file_id": result.file_id,
            "old_path": result.old_path,
            "new_path": result.new_path,
            "file_status": result.file_status,
        },
    )
    print(f"Restored file_id:  {result.file_id}")
    print(f"old_path:          {result.old_path}")
    print(f"new_path:          {result.new_path}")
    print(f"file_status:       {result.file_status}")
    return 0


def cmd_expire(workspace: str, proposal_id: str) -> int:
    ws_path = Path(workspace).resolve()
    init_db(ws_path)
    ensure_audit_file(ws_path)
    try:
        result = expire_proposal(ws_path, proposal_id=proposal_id)
    except ValueError as exc:
        write_audit_event(
            workspace=ws_path,
            action="expire_proposal",
            status="error",
            details={"proposal_id": proposal_id, "error": str(exc)},
        )
        print(str(exc))
        return 2

    write_audit_event(
        workspace=ws_path,
        action="expire_proposal",
        status="ok",
        details={
            "proposal_id": result.proposal_id,
            "file_id": result.file_id,
            "path": result.old_path,
            "proposal_status": result.proposal_status,
        },
    )
    print(f"Expired proposal: {result.proposal_id}")
    print(f"file_id:          {result.file_id}")
    print(f"path:             {result.old_path}")
    print(f"proposal_status:  {result.proposal_status}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metamirror",
        description="MetaMirror workspace-local CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize .metamirror in a workspace")
    init_parser.add_argument("workspace", help="Path to workspace")
    scan_parser = subparsers.add_parser("scan", help="Scan workspace files into metadata DB")
    scan_parser.add_argument("workspace", help="Path to workspace")
    watch_parser = subparsers.add_parser("watch", help="Continuously scan workspace files")
    watch_parser.add_argument("workspace", help="Path to workspace")
    watch_parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between scans (default: 2.0)",
    )
    watch_parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Optional max scan cycles before exit",
    )
    status_parser = subparsers.add_parser("status", help="Show workspace metadata status summary")
    status_parser.add_argument("workspace", help="Path to workspace")
    search_parser = subparsers.add_parser("search", help="Search files by metadata fields")
    search_parser.add_argument("workspace", help="Path to workspace")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--limit", type=int, default=50, help="Maximum results")
    duplicates_parser = subparsers.add_parser("duplicates", help="Find duplicate active files by sha256")
    duplicates_parser.add_argument("workspace", help="Path to workspace")
    recent_parser = subparsers.add_parser("recent", help="List recent file events")
    recent_parser.add_argument("workspace", help="Path to workspace")
    recent_parser.add_argument("--days", type=int, default=7, help="Days back from now")
    recent_parser.add_argument("--limit", type=int, default=200, help="Maximum events")
    propose_delete_parser = subparsers.add_parser(
        "propose-delete",
        help="Create a pending delete proposal for a file_id",
    )
    propose_delete_parser.add_argument("workspace", help="Path to workspace")
    propose_delete_parser.add_argument("file_id", help="Target file_id")
    propose_delete_parser.add_argument("--reason", required=True, help="Reason for proposal")
    propose_delete_parser.add_argument("--evidence", required=True, help="Evidence for proposal")
    proposals_parser = subparsers.add_parser("proposals", help="List action proposals")
    proposals_parser.add_argument("workspace", help="Path to workspace")
    proposals_parser.add_argument("--status", default=None, help="Filter by proposal status")
    proposals_parser.add_argument("--limit", type=int, default=200, help="Maximum proposals")
    approve_parser = subparsers.add_parser("approve", help="Approve and soft-delete a pending proposal")
    approve_parser.add_argument("workspace", help="Path to workspace")
    approve_parser.add_argument("proposal_id", help="Proposal ID to approve")
    reject_parser = subparsers.add_parser("reject", help="Reject a pending proposal")
    reject_parser.add_argument("workspace", help="Path to workspace")
    reject_parser.add_argument("proposal_id", help="Proposal ID to reject")
    restore_parser = subparsers.add_parser("restore", help="Restore a soft-deleted file back to active")
    restore_parser.add_argument("workspace", help="Path to workspace")
    restore_parser.add_argument("file_id", help="Soft-deleted file_id to restore")
    restore_parser.add_argument(
        "--target-path",
        default=None,
        help="Optional restore path relative to workspace",
    )
    expire_parser = subparsers.add_parser("expire", help="Expire a pending proposal")
    expire_parser.add_argument("workspace", help="Path to workspace")
    expire_parser.add_argument("proposal_id", help="Proposal ID to expire")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return cmd_init(args.workspace)
    if args.command == "scan":
        return cmd_scan(args.workspace)
    if args.command == "watch":
        return cmd_watch(args.workspace, args.interval, args.max_cycles)
    if args.command == "status":
        return cmd_status(args.workspace)
    if args.command == "search":
        return cmd_search(args.workspace, args.query, args.limit)
    if args.command == "duplicates":
        return cmd_duplicates(args.workspace)
    if args.command == "recent":
        return cmd_recent(args.workspace, args.days, args.limit)
    if args.command == "propose-delete":
        return cmd_propose_delete(args.workspace, args.file_id, args.reason, args.evidence)
    if args.command == "proposals":
        return cmd_proposals(args.workspace, args.status, args.limit)
    if args.command == "approve":
        return cmd_approve(args.workspace, args.proposal_id)
    if args.command == "reject":
        return cmd_reject(args.workspace, args.proposal_id)
    if args.command == "restore":
        return cmd_restore(args.workspace, args.file_id, args.target_path)
    if args.command == "expire":
        return cmd_expire(args.workspace, args.proposal_id)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
