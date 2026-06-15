"""V1 append-only audit log."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from governed_api.types import AuditRecord, MiddlewareContext


def build_audit_record(context: MiddlewareContext) -> AuditRecord:
    entry = context["entry"]
    auth = context["auth"]
    persisted_path = context["persisted_path"]
    kb_root = context["kb_root"]
    try:
        relative_path = persisted_path.resolve().relative_to(kb_root.resolve()).as_posix()
    except ValueError:
        relative_path = persisted_path.name
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "user": auth["user"],
        "role": auth["role"],
        "operation": context["operation"],
        "entry_id": entry.id,
        "target_dir": context["target_dir"],
        "path": relative_path,
    }


def preflight_audit_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n"):
        pass


def append_audit_record(path: Path, record: AuditRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        handle.write("\n")
