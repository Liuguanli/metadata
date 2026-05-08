from __future__ import annotations

from pathlib import Path


SUPPORTED_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".sql",
    ".json",
    ".yaml",
    ".yml",
}
EXTRACTOR_VERSION = "v0.1-basic-preview"


def extract_summary_preview(file_path: Path) -> str | None:
    extension = file_path.suffix.lower()
    if extension not in SUPPORTED_TEXT_EXTENSIONS:
        return None

    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    preview = content[:4096]
    normalized = " ".join(preview.split())
    if not normalized:
        return None
    return normalized[:280]
