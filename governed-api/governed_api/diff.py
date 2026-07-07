"""Shared entry diff helpers for governance decisions and review detail."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from core.models import Entry

EntryPayloadSource = Entry | dict[str, Any] | None


def changed_fields_between(previous: EntryPayloadSource, current: EntryPayloadSource) -> set[str]:
    """Return top-level fields whose normalized JSON payloads differ."""

    previous_payload = normalized_entry_payload(previous)
    current_payload = normalized_entry_payload(current)
    if previous_payload is None or current_payload is None:
        return set()
    return {
        field
        for field in set(previous_payload) | set(current_payload)
        if previous_payload.get(field) != current_payload.get(field)
    }


def normalized_entry_payload(source: EntryPayloadSource) -> dict[str, Any] | None:
    if source is None:
        return None
    if isinstance(source, Entry):
        return source.model_dump(mode="json")
    try:
        return Entry.model_validate(source).model_dump(mode="json")
    except ValidationError:
        return source
