"""Markdown/frontmatter storage helpers for content-core entries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from core.models import Entry, TrustState
from core.validation import TRUST_STATE_BY_DIR

FRONTMATTER_MARKER = "---"


def read_entry(path: Path) -> Entry:
    frontmatter, body = read_frontmatter(path)
    payload = dict(frontmatter)
    payload["body"] = body
    return Entry.model_validate(payload)


def write_entry(path: Path, entry: Entry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = entry.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    document = (
        f"{FRONTMATTER_MARKER}\n"
        f"{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}"
        f"{FRONTMATTER_MARKER}\n"
        f"{entry.body.rstrip()}\n"
    )
    path.write_text(document, encoding="utf-8", newline="\n")


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"markdown entry is not valid UTF-8: {path}") from exc
    if not text.startswith(f"{FRONTMATTER_MARKER}\n"):
        raise ValueError("markdown entry must start with YAML frontmatter")
    try:
        _, metadata_text, body = text.split(f"{FRONTMATTER_MARKER}\n", 2)
    except ValueError as exc:
        raise ValueError("markdown entry has incomplete YAML frontmatter") from exc
    metadata = yaml.safe_load(metadata_text) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a YAML mapping")
    return metadata, body.rstrip("\n")


def target_dir_for_trust_state(trust_state: TrustState) -> str:
    for dirname, state in TRUST_STATE_BY_DIR.items():
        if state == trust_state:
            return dirname
    raise ValueError(f"unsupported trust_state: {trust_state}")
