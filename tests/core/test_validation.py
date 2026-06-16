from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from core.errors import IssueCode, ValidationIssue
from core.models import Entry, EntryType
from core.validation import headings_for_entry_type, trust_state_for_path, validate_entry


def test_entry_section_headings_match_frozen_design_literals() -> None:
    assert headings_for_entry_type(EntryType.DEFECT_CASE) == (
        "现象",
        "环境",
        "根因",
        "解决方案",
        "验证方法",
        "经验教训",
    )
    assert headings_for_entry_type(EntryType.TRIAGE_RULE) == (
        "症状特征",
        "判据",
        "责任方",
        "置信度与适用边界",
        "例证",
    )
    assert headings_for_entry_type(EntryType.CODE_FLOW) == (
        "场景",
        "流程描述",
        "关键函数与调用链",
        "前置条件",
        "版本绑定说明",
    )
    assert headings_for_entry_type(EntryType.LOG_BASELINE) == (
        "场景",
        "正确日志",
        "关键标志行",
        "采集环境",
        "版本绑定说明",
    )


def test_all_entry_types_validate(make_entry: Callable[..., Entry]) -> None:
    for entry_type in ("defect_case", "triage_rule", "code_flow", "log_baseline"):
        report = validate_entry(make_entry(entry_type=entry_type), check_evidence_exists=False)

        assert report.ok, report.errors


def test_section_credibility_unknown_heading_is_schema_error(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        section_credibility={
            "unknown-section": {
                "claim_type": "observation",
                "evidence": [{"type": "human_note"}],
            }
        }
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "section_credibility.unknown-section")


def test_body_skeleton_reports_missing_and_allows_extra_headings(
    make_entry: Callable[..., Entry],
) -> None:
    first_heading = headings_for_entry_type(EntryType.DEFECT_CASE)[0]
    entry = make_entry(body=f"## {first_heading}\nok\n\n## unknown-section\nextra\n")

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "body")
    assert any("missing required section heading" in issue.message for issue in report.errors)
    assert not any("unknown section heading" in issue.message for issue in report.errors)


def test_body_skeleton_accepts_extra_headings_when_core_headings_exist(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry()
    entry.body = f"{entry.body}\n\n## unknown-section\nextra\n"

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok, report.errors


def test_body_skeleton_ignores_headings_inside_fenced_code(
    make_entry: Callable[..., Entry],
) -> None:
    body = """## 现象
ok

```markdown
## not-a-section
```

## 环境
ok

## 根因
ok

## 解决方案
ok

## 验证方法
ok

## 经验教训
ok
"""
    entry = make_entry(body=body)

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok, report.errors


def test_body_skeleton_rejects_duplicate_headings(
    make_entry: Callable[..., Entry],
) -> None:
    body = """## 现象
ok

## 环境
ok

## 根因
ok

## 根因
duplicate

## 解决方案
ok

## 验证方法
ok

## 经验教训
ok
"""
    entry = make_entry(body=body)

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "body")
    assert any("duplicate section heading: 根因" in issue.message for issue in report.errors)


def test_section_key_must_match_existing_body_heading(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(
        body="## 现象\nok\n\n## 环境\nok\n\n## 根因\nok\n\n## 解决方案\nok\n\n## 验证方法\nok\n",
        section_credibility={"经验教训": {"claim_type": "observation"}},
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "section_credibility.经验教训")


def test_fact_downgrades_to_observation_when_fact_evidence_missing(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(claim_type="fact", evidence=[{"type": "human_note", "excerpt": "note"}])

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok
    assert report.entry.credibility.claim_type == "observation"
    assert _has_issue(report.warnings, IssueCode.W_DOWNGRADE, "credibility.claim_type")


def test_section_credibility_can_be_downgraded_independently(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        section_credibility={
            "根因": {
                "claim_type": "fact",
                "support_strength": "moderate",
                "evidence": [{"type": "human_note", "excerpt": "section note"}],
            }
        }
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok
    assert report.entry.section_credibility["根因"].claim_type == "observation"
    assert report.entry.section_credibility["根因"].support_strength == "moderate"


def test_section_local_evidence_materializes_downgraded_inherited_claim(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        claim_type="fact",
        evidence=[{"type": "spec", "uri": "spec://decoder", "version": "v1"}],
        section_credibility={
            "根因": {
                "evidence": [{"type": "human_note", "excerpt": "section-only note"}],
            }
        },
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok
    assert report.entry.section_credibility["根因"].claim_type == "observation"
    assert _has_issue(report.warnings, IssueCode.W_DOWNGRADE, "section_credibility.根因")


def test_pure_inherited_section_does_not_repeat_mapping_errors(
    make_entry: Callable[..., Entry],
) -> None:
    heading = headings_for_entry_type(EntryType.DEFECT_CASE)[0]
    entry = make_entry(
        claim_type="static_inference",
        evidence=[{"type": "human_note", "excerpt": "not code evidence"}],
        section_credibility={heading: {"support_strength": "weak"}},
    )

    report = validate_entry(entry, check_evidence_exists=False)

    evidence_errors = [
        issue for issue in report.errors if issue.code == IssueCode.E_EVIDENCE_MISSING
    ]
    assert len(evidence_errors) == 1
    assert evidence_errors[0].field == "credibility.evidence"


def test_observation_without_observation_evidence_downgrades_to_llm_hypothesis(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(claim_type="observation", evidence=[])

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok
    assert report.entry.credibility.claim_type == "llm_hypothesis"
    assert _has_issue(report.warnings, IssueCode.W_DOWNGRADE, "credibility.claim_type")


def test_static_inference_without_code_evidence_is_rejected(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        claim_type="static_inference",
        evidence=[{"type": "human_note", "excerpt": "looks like code"}],
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_MISSING, "credibility.evidence")


def test_spec_without_version_is_rejected(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(claim_type="spec", evidence=[{"type": "spec", "uri": "spec://decoder"}])

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_MISSING, "credibility.evidence")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "credibility.evidence[0]")


def test_historical_pattern_without_historical_entry_downgrades(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        claim_type="historical_pattern", evidence=[{"type": "ticket", "ref": "BUG-1"}]
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.ok
    assert report.entry.credibility.claim_type == "llm_hypothesis"
    assert _has_issue(report.warnings, IssueCode.W_DOWNGRADE, "credibility.claim_type")


def test_code_binding_shape_errors_are_schema_errors(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(entry_type="code_flow")
    assert entry.code_binding is not None
    entry.code_binding.paths = ["C:/secret.c", "C:secret.c"]
    entry.code_binding.path_hashes["src\\decoder.c"] = "ABC"
    entry.code_binding.symbol_hashes["decode_hdr_frame"] = "ABC"
    entry.code_binding.build_config_hash = "too-short"

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding.paths")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding.path_hashes")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding.symbol_hashes")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding.build_config_hash")


def test_code_binding_requires_git_sha_for_bound_entry(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(entry_type="log_baseline")
    assert entry.code_binding is not None
    entry.code_binding.git_sha = None

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding.git_sha")


def test_code_flow_requires_code_binding(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(entry_type="code_flow", include_code_binding=False)

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "code_binding")


def test_directory_state_mismatch_is_schema_error(
    tmp_path: Path,
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(trust_state="published")
    entry_path = tmp_path / "kb" / "staging" / "KB-2026-0001.md"

    report = validate_entry(entry, entry_path=entry_path, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "trust_state")


def test_directory_state_uses_real_kb_segment_when_ancestor_is_named_kb(
    tmp_path: Path,
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(trust_state="published")
    entry_path = tmp_path / "kb" / "workspace" / "kb" / "staging" / "KB-2026-0001.md"

    report = validate_entry(entry, entry_path=entry_path, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "trust_state")


def test_directory_state_accepts_path_relative_to_kb_root(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(trust_state="published")

    report = validate_entry(
        entry, entry_path=Path("entries") / "KB-2026-0001.md", check_evidence_exists=False
    )

    assert report.ok


def test_directory_state_rejects_traversal_without_kb_root(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(trust_state="published")
    entry_path = Path("kb") / "entries" / ".." / "research" / "KB-2026-0001.md"

    report = validate_entry(entry, entry_path=entry_path, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "entry_path")


def test_trust_state_for_path_maps_kb_state_dirs(tmp_path: Path) -> None:
    kb_root = tmp_path / "kb"
    assert trust_state_for_path(kb_root / "entries" / "a.md", kb_root) == "published"
    assert trust_state_for_path(tmp_path / "outside.md", kb_root) is None


def test_code_and_attachment_evidence_existence(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    _git(["init"], tmp_path)
    source = tmp_path / "src" / "decoder.c"
    source.parent.mkdir()
    source.write_text("int decode(void) { return 0; }\n", encoding="utf-8")
    _git(["add", "src/decoder.c"], tmp_path)
    attachment = tmp_path / "kb" / "attachments" / "public" / "boot.log"
    attachment.parent.mkdir(parents=True)
    attachment.write_text("ok\n", encoding="utf-8")

    entry = make_entry(
        claim_type="fact",
        evidence=[
            {"type": "code", "filepath": "src/decoder.c"},
            {"type": "log", "attachment_id": "boot.log"},
        ],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert report.ok, report.errors


def test_missing_evidence_targets_are_errors(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    _git(["init"], tmp_path)
    entry = make_entry(
        claim_type="fact",
        evidence=[
            {"type": "code", "filepath": "src/missing.c"},
            {"type": "log", "attachment_id": "missing.log"},
        ],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "filepath")
    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "attachment_id")


def test_evidence_existence_requires_repo_root_by_default(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        claim_type="fact",
        evidence=[
            {"type": "code", "filepath": "src/missing.c"},
            {"type": "log", "attachment_id": "missing.log"},
        ],
    )

    report = validate_entry(entry)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "repo_root")


def test_code_evidence_existence_requires_git_repo(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    source = tmp_path / "src" / "decoder.c"
    source.parent.mkdir()
    source.write_text("int decode(void) { return 0; }\n", encoding="utf-8")
    entry = make_entry(
        claim_type="static_inference",
        evidence=[{"type": "code", "filepath": "src/decoder.c"}],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "repo_root")
    assert not _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "filepath")


def test_code_evidence_uses_literal_pathspec_not_glob(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    _git(["init"], tmp_path)
    source = tmp_path / "src" / "decoder.c"
    source.parent.mkdir()
    source.write_text("int decode(void) { return 0; }\n", encoding="utf-8")
    _git(["add", "src/decoder.c"], tmp_path)
    entry = make_entry(
        claim_type="static_inference",
        evidence=[{"type": "code", "filepath": "src/*.c"}],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "filepath")


def test_code_evidence_directory_path_is_not_a_file(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    _git(["init"], tmp_path)
    source = tmp_path / "src" / "decoder.c"
    source.parent.mkdir()
    source.write_text("int decode(void) { return 0; }\n", encoding="utf-8")
    _git(["add", "src/decoder.c"], tmp_path)
    entry = make_entry(
        claim_type="static_inference",
        evidence=[{"type": "code", "filepath": "src"}],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "filepath")


def test_invalid_id_and_evidence_payload_shapes(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(
        evidence=[
            {"type": "code"},
            {"type": "log"},
            {"type": "ticket"},
            {"type": "historical_entry"},
            {"type": "human_note"},
            {"type": "repro"},
        ]
    )
    entry.id = "bad-id"

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "id")
    assert len([issue for issue in report.errors if issue.code == IssueCode.E_SCHEMA]) >= 6


def test_invalid_evidence_paths_fail_existence_checks(
    tmp_path: Path, make_entry: Callable[..., Entry]
) -> None:
    _git(["init"], tmp_path)
    entry = make_entry(
        claim_type="fact",
        evidence=[
            {"type": "code", "filepath": "../secret.c"},
            {"type": "attachment", "attachment_id": "../secret.log"},
        ],
    )

    report = validate_entry(entry, repo_root=tmp_path)

    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "filepath")
    assert _has_issue(report.errors, IssueCode.E_EVIDENCE_NOT_FOUND, "attachment_id")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "filepath")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "attachment_id")


def test_research_reference_cannot_be_formal_entry_evidence(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        claim_type="historical_pattern",
        evidence=[{"type": "historical_entry", "ref": "R-2026-0001"}],
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(
        report.errors,
        IssueCode.E_RESEARCH_AS_EVIDENCE,
        "credibility.evidence[0]",
    )


def test_research_reference_cannot_be_formal_section_evidence(
    make_entry: Callable[..., Entry],
) -> None:
    entry = make_entry(
        section_credibility={
            "?밧썱": {
                "claim_type": "historical_pattern",
                "evidence": [{"type": "historical_entry", "ref": "research/R-2026-0001.md"}],
            }
        }
    )

    report = validate_entry(entry, check_evidence_exists=False)

    assert _has_issue(
        report.errors,
        IssueCode.E_RESEARCH_AS_EVIDENCE,
        "section_credibility.?밧썱.evidence[0]",
    )


def test_bare_log_does_not_keep_fact_claim(make_entry: Callable[..., Entry]) -> None:
    entry = make_entry(claim_type="fact", evidence=[{"type": "log"}])

    report = validate_entry(entry, check_evidence_exists=False)

    assert report.entry.credibility.claim_type == "llm_hypothesis"
    assert _has_issue(report.warnings, IssueCode.W_DOWNGRADE, "credibility.claim_type")
    assert _has_issue(report.errors, IssueCode.E_SCHEMA, "credibility.evidence[0]")


def _git(args: list[str], cwd: Path) -> None:
    result = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def _has_issue(issues: list[ValidationIssue], code: IssueCode, field_fragment: str) -> bool:
    return any(issue.code == code and field_fragment in issue.field for issue in issues)
