from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.models import Entry, TrustState
from core.storage import read_entry, read_frontmatter, target_dir_for_trust_state, write_entry
from core.validation import validate_entry


def test_markdown_frontmatter_roundtrip(tmp_path: Path, make_entry: Callable[..., Entry]) -> None:
    entry = make_entry()
    path = tmp_path / "kb" / "entries" / "KB-2026-0001.md"

    write_entry(path, entry)
    loaded = read_entry(path)
    report = validate_entry(loaded, entry_path=path, check_evidence_exists=False)

    assert loaded == entry
    assert report.ok, report.errors


def test_write_entry_is_atomic_when_replace_fails(
    tmp_path: Path, make_entry: Callable[..., Entry], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "kb" / "entries" / "KB-2026-0001.md"
    path.parent.mkdir(parents=True)
    path.write_text("original\n", encoding="utf-8")

    def fail_replace(*args: object, **kwargs: object) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr("core.storage.os.replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_entry(path, make_entry())

    assert path.read_text(encoding="utf-8") == "original\n"
    assert list(path.parent.glob("*.tmp")) == []


def test_target_dir_for_trust_state() -> None:
    assert target_dir_for_trust_state(TrustState.PUBLISHED) == "entries"
    assert target_dir_for_trust_state(TrustState.PENDING) == "staging"
    assert target_dir_for_trust_state(TrustState.DRAFT) == "drafts"
    assert target_dir_for_trust_state(TrustState.RESEARCH) == "research"
    assert target_dir_for_trust_state(TrustState.DEPRECATED) == "deprecated"


def test_read_frontmatter_rejects_missing_or_invalid_frontmatter(tmp_path: Path) -> None:
    no_frontmatter = tmp_path / "no-frontmatter.md"
    no_frontmatter.write_text("body\n", encoding="utf-8")
    invalid_frontmatter = tmp_path / "invalid-frontmatter.md"
    invalid_frontmatter.write_text("---\n- not\n- mapping\n---\nbody\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must start"):
        read_frontmatter(no_frontmatter)
    with pytest.raises(ValueError, match="mapping"):
        read_frontmatter(invalid_frontmatter)


def test_read_frontmatter_rejects_non_utf8_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_bytes(b"---\nid: KB-2026-0001\n---\n\xff")

    with pytest.raises(ValueError, match="valid UTF-8"):
        read_frontmatter(path)


def test_entry_rejects_non_v3_schema(make_entry: Callable[..., Entry]) -> None:
    payload = make_entry().model_dump(mode="json")
    payload["schema_version"] = 2

    with pytest.raises(ValidationError, match="schema_version must be 3"):
        Entry.model_validate(payload)
