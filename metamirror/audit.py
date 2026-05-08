from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from metamirror.db import metamirror_dir


AUDIT_FILENAME = "audit.jsonl"


def audit_file_path(workspace: str | Path) -> Path:
    return metamirror_dir(workspace) / AUDIT_FILENAME


def ensure_audit_file(workspace: str | Path) -> Path:
    path = audit_file_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    return path


def write_audit_event(
    workspace: str | Path,
    action: str,
    status: str = "ok",
    details: dict[str, Any] | None = None,
) -> None:
    path = ensure_audit_file(workspace)
    payload: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "status": status,
        "details": details or {},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=True) + "\n")
