from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from metamirror.scanner import scan_workspace


@dataclass
class WatchResult:
    cycles: int
    total_scanned_files: int


def watch_workspace(
    workspace: str | Path,
    interval_seconds: float = 2.0,
    max_cycles: int | None = None,
) -> WatchResult:
    cycles = 0
    total_scanned_files = 0
    ws_path = Path(workspace).resolve()

    while True:
        result = scan_workspace(ws_path)
        cycles += 1
        total_scanned_files += result.scanned_files
        print(f"[watch] cycle={cycles} scanned={result.scanned_files}")

        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(interval_seconds)

    return WatchResult(cycles=cycles, total_scanned_files=total_scanned_files)
