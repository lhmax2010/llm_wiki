"""Pure content-core validation for entries and evidence mapping."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.errors import IssueCode, ValidationIssue
from core.models import (
    ClaimType,
    Credibility,
    Entry,
    EntryType,
    Evidence,
    EvidenceType,
    SectionCredibility,
    TrustState,
)

ID_PATTERN = re.compile(r"^KB-(?P<year>\d{4})-(?P<number>\d{4})$")
RESEARCH_ID_PATTERN = re.compile(r"^R-\d{4}-\d{4}$")
HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
HEX_16_PATTERN = re.compile(r"^[0-9a-f]{16}$")
RELATIVE_POSIX_PATH_PATTERN = re.compile(r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$)).+[^/]$")
WINDOWS_DRIVE_PATH_PATTERN = re.compile(r"^[A-Za-z]:")
HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")

ENTRY_SECTION_HEADINGS: dict[EntryType, tuple[str, ...]] = {
    EntryType.DEFECT_CASE: ("现象", "环境", "根因", "解决方案", "验证方法", "经验教训"),
    EntryType.TRIAGE_RULE: ("症状特征", "判据", "责任方", "置信度与适用边界", "例证"),
    EntryType.CODE_FLOW: ("场景", "流程描述", "关键函数与调用链", "前置条件", "版本绑定说明"),
    EntryType.LOG_BASELINE: ("场景", "正确日志", "关键标志行", "采集环境", "版本绑定说明"),
}

TRUST_STATE_BY_DIR = {
    "entries": TrustState.PUBLISHED,
    "staging": TrustState.PENDING,
    "drafts": TrustState.DRAFT,
    "research": TrustState.RESEARCH,
    "deprecated": TrustState.DEPRECATED,
}


@dataclass(slots=True)
class ValidationReport:
    entry: Entry
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_entry(
    entry: Entry,
    *,
    repo_root: Path | None = None,
    kb_root: Path | None = None,
    entry_path: Path | None = None,
    check_evidence_exists: bool = True,
) -> ValidationReport:
    """Validate an entry and return normalized credibility downgrades plus issues."""

    normalized = entry.model_copy(deep=True)
    report = ValidationReport(entry=normalized)

    _validate_id(normalized, report)
    _validate_body_skeleton(normalized, report)
    _validate_directory_state(normalized, entry_path, kb_root, report)
    _validate_code_binding(normalized, report)

    normalized.credibility = _normalize_credibility(normalized.credibility, "credibility", report)
    for heading, section in normalized.section_credibility.items():
        if section.claim_type is None and section.evidence is None:
            continue
        effective = _section_effective_credibility(normalized.credibility, section)
        mapped = _normalize_credibility(effective, f"section_credibility.{heading}", report)
        if section.claim_type is not None or section.evidence is not None:
            section.claim_type = mapped.claim_type
        if section.support_strength is not None:
            section.support_strength = mapped.support_strength
        if section.evidence is not None:
            section.evidence = mapped.evidence

    _validate_evidence_shapes(normalized, report)
    _validate_research_not_evidence(normalized, report)
    if check_evidence_exists:
        if repo_root is None and _has_evidence_targets_to_check(normalized):
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_SCHEMA,
                    "repo_root",
                    "repo_root is required when evidence existence checks are enabled",
                )
            )
        elif repo_root is not None:
            _validate_evidence_existence(normalized, repo_root, report)

    return report


def headings_for_entry_type(entry_type: EntryType) -> tuple[str, ...]:
    return ENTRY_SECTION_HEADINGS[entry_type]


def markdown_headings(body: str) -> list[str]:
    headings: list[str] = []
    in_fence = False
    fence_marker: str | None = None
    for line in body.splitlines():
        stripped = line.strip()
        marker = stripped[:3]
        if marker in {"```", "~~~"}:
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        match = HEADING_PATTERN.match(line)
        if match is not None:
            headings.append(match.group(1).strip())
    return headings


def trust_state_for_path(path: Path, kb_root: Path) -> TrustState | None:
    try:
        relative = path.resolve().relative_to(kb_root.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    return TRUST_STATE_BY_DIR.get(relative.parts[0])


def _validate_id(entry: Entry, report: ValidationReport) -> None:
    if ID_PATTERN.match(entry.id) is None:
        report.errors.append(
            ValidationIssue(IssueCode.E_SCHEMA, "id", "id must match KB-{year}-{NNNN}")
        )


def _validate_body_skeleton(entry: Entry, report: ValidationReport) -> None:
    expected = headings_for_entry_type(EntryType(entry.entry_type))
    actual = markdown_headings(entry.body)
    actual_set = set(actual)
    expected_set = set(expected)

    missing = [heading for heading in expected if heading not in actual_set]
    duplicates = _duplicates(actual)

    for heading in missing:
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "body",
                f"missing required section heading: {heading}",
            )
        )
    for heading in duplicates:
        report.errors.append(
            ValidationIssue(IssueCode.E_SCHEMA, "body", f"duplicate section heading: {heading}")
        )
    for heading in entry.section_credibility:
        if heading not in expected_set:
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_SCHEMA,
                    f"section_credibility.{heading}",
                    "section credibility key is not in the entry section skeleton",
                )
            )
        elif heading not in actual_set:
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_SCHEMA,
                    f"section_credibility.{heading}",
                    "section credibility key has no matching markdown heading",
                )
            )


def _validate_directory_state(
    entry: Entry,
    entry_path: Path | None,
    kb_root: Path | None,
    report: ValidationReport,
) -> None:
    if entry_path is None:
        return
    if ".." in entry_path.parts:
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "entry_path",
                "entry_path must not contain traversal segments",
            )
        )
        return
    state = trust_state_for_path(entry_path, kb_root) if kb_root is not None else None
    if state is None:
        state = _trust_state_from_path_parts(entry_path)
    if state is None:
        return
    if TrustState(entry.trust_state) != state:
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "trust_state",
                f"trust_state={entry.trust_state!s} does not match path state {state.value}",
            )
        )


def _trust_state_from_path_parts(path: Path) -> TrustState | None:
    parts = path.parts
    if parts and parts[0] in TRUST_STATE_BY_DIR:
        return TRUST_STATE_BY_DIR[parts[0]]
    for index, part in enumerate(parts[:-1]):
        if part == "kb":
            state = TRUST_STATE_BY_DIR.get(parts[index + 1])
            if state is not None:
                return state
    return None


def _validate_code_binding(entry: Entry, report: ValidationReport) -> None:
    entry_type = EntryType(entry.entry_type)
    if entry_type in {EntryType.CODE_FLOW, EntryType.LOG_BASELINE} and entry.code_binding is None:
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "code_binding",
                "code_flow/log_baseline entries require code_binding",
            )
        )
        return
    if entry.code_binding is None:
        return

    binding = entry.code_binding
    if entry_type in {EntryType.CODE_FLOW, EntryType.LOG_BASELINE} and not binding.git_sha:
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "code_binding.git_sha",
                "code_flow/log_baseline code_binding requires git_sha",
            )
        )
    for field_name, paths in {
        "code_binding.paths": binding.paths,
        "code_binding.path_hashes": list(binding.path_hashes),
    }.items():
        for path in paths:
            if not _is_relative_posix_path(path):
                report.errors.append(
                    ValidationIssue(
                        IssueCode.E_SCHEMA,
                        field_name,
                        "paths must be repository-relative POSIX paths without traversal",
                    )
                )
    for path, digest in binding.path_hashes.items():
        if HEX_64_PATTERN.match(digest) is None:
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_SCHEMA,
                    f"code_binding.path_hashes.{path}",
                    "path_hash must be 64 lowercase hex characters",
                )
            )
    for symbol, digest in binding.symbol_hashes.items():
        if HEX_64_PATTERN.match(digest) is None:
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_SCHEMA,
                    f"code_binding.symbol_hashes.{symbol}",
                    "symbol_hash must be 64 lowercase hex characters",
                )
            )
    if (
        binding.build_config_hash is not None
        and HEX_16_PATTERN.match(binding.build_config_hash) is None
    ):
        report.errors.append(
            ValidationIssue(
                IssueCode.E_SCHEMA,
                "code_binding.build_config_hash",
                "build_config_hash must be 16 lowercase hex characters",
            )
        )


def _section_effective_credibility(
    entry_credibility: Credibility, section: SectionCredibility
) -> Credibility:
    return Credibility(
        claim_type=section.claim_type or entry_credibility.claim_type,
        support_strength=section.support_strength or entry_credibility.support_strength,
        evidence=section.evidence if section.evidence is not None else entry_credibility.evidence,
    )


def _normalize_credibility(
    credibility: Credibility,
    field_name: str,
    report: ValidationReport,
) -> Credibility:
    normalized = credibility.model_copy(deep=True)

    while True:
        claim = ClaimType(normalized.claim_type)
        evidence = normalized.evidence
        if claim == ClaimType.FACT and not _has_fact_evidence(evidence):
            _downgrade(normalized, ClaimType.OBSERVATION, field_name, report)
            continue
        if claim == ClaimType.OBSERVATION and not _has_observation_evidence(evidence):
            _downgrade(normalized, ClaimType.LLM_HYPOTHESIS, field_name, report)
            continue
        if claim == ClaimType.HISTORICAL_PATTERN and not _has_historical_evidence(evidence):
            _downgrade(normalized, ClaimType.LLM_HYPOTHESIS, field_name, report)
            continue
        if claim == ClaimType.STATIC_INFERENCE and not _has_code_evidence(evidence):
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_EVIDENCE_MISSING,
                    f"{field_name}.evidence",
                    "static_inference requires code evidence",
                )
            )
        if claim == ClaimType.SPEC and not _has_spec_evidence(evidence):
            report.errors.append(
                ValidationIssue(
                    IssueCode.E_EVIDENCE_MISSING,
                    f"{field_name}.evidence",
                    "spec requires spec evidence with version",
                )
            )
        return normalized


def _downgrade(
    credibility: Credibility,
    target: ClaimType,
    field_name: str,
    report: ValidationReport,
) -> None:
    source = credibility.claim_type
    credibility.claim_type = target
    report.warnings.append(
        ValidationIssue(
            IssueCode.W_DOWNGRADE,
            f"{field_name}.claim_type",
            f"claim_type downgraded from {source!s} to {target.value}",
        )
    )


def _has_fact_evidence(evidence: list[Evidence]) -> bool:
    return any(
        (item.type == EvidenceType.LOG and bool(item.attachment_id))
        or (item.type == EvidenceType.REPRO and bool(item.excerpt or item.ref))
        or (item.type == EvidenceType.SPEC and bool(item.uri and item.version))
        for item in evidence
    )


def _has_observation_evidence(evidence: list[Evidence]) -> bool:
    return any(
        (item.type in {EvidenceType.LOG, EvidenceType.ATTACHMENT} and bool(item.attachment_id))
        or (item.type == EvidenceType.REPRO and bool(item.excerpt or item.ref))
        or (item.type == EvidenceType.TICKET and bool(item.ref))
        or (item.type == EvidenceType.HUMAN_NOTE and bool(item.excerpt or item.ref))
        for item in evidence
    )


def _has_code_evidence(evidence: list[Evidence]) -> bool:
    return any(item.type == EvidenceType.CODE and bool(item.filepath) for item in evidence)


def _has_historical_evidence(evidence: list[Evidence]) -> bool:
    return any(item.type == EvidenceType.HISTORICAL_ENTRY and bool(item.ref) for item in evidence)


def _has_spec_evidence(evidence: list[Evidence]) -> bool:
    return any(
        item.type == EvidenceType.SPEC and bool(item.uri and item.version) for item in evidence
    )


def _validate_evidence_shapes(entry: Entry, report: ValidationReport) -> None:
    for field_name, evidence in _iter_evidence(entry):
        for index, item in enumerate(evidence):
            prefix = f"{field_name}.evidence[{index}]"
            if item.type == EvidenceType.CODE:
                if not item.filepath:
                    _evidence_schema_error(report, prefix, "code evidence requires filepath")
                elif not _is_relative_posix_path(item.filepath):
                    _evidence_schema_error(
                        report,
                        f"{prefix}.filepath",
                        "code evidence filepath must be repository-relative POSIX path",
                    )
            elif item.type in {EvidenceType.LOG, EvidenceType.ATTACHMENT}:
                if not item.attachment_id:
                    _evidence_schema_error(
                        report, prefix, f"{item.type.value} evidence requires attachment_id"
                    )
                elif not _is_relative_posix_path(item.attachment_id):
                    _evidence_schema_error(
                        report,
                        f"{prefix}.attachment_id",
                        f"{item.type.value} evidence attachment_id must be relative POSIX path",
                    )
            elif item.type == EvidenceType.SPEC and not (item.uri and item.version):
                _evidence_schema_error(report, prefix, "spec evidence requires uri and version")
            elif item.type in {EvidenceType.TICKET, EvidenceType.HISTORICAL_ENTRY} and not item.ref:
                _evidence_schema_error(report, prefix, f"{item.type.value} evidence requires ref")
            elif item.type == EvidenceType.HUMAN_NOTE and not (item.excerpt or item.ref):
                _evidence_schema_error(
                    report, prefix, "human_note evidence requires excerpt or ref"
                )
            elif item.type == EvidenceType.REPRO and not (item.excerpt or item.ref):
                _evidence_schema_error(report, prefix, "repro evidence requires excerpt or ref")


def _validate_research_not_evidence(entry: Entry, report: ValidationReport) -> None:
    for field_name, evidence in _iter_evidence(entry):
        for index, item in enumerate(evidence):
            research_ref = _research_reference(item)
            if research_ref is not None:
                report.errors.append(
                    ValidationIssue(
                        IssueCode.E_RESEARCH_AS_EVIDENCE,
                        f"{field_name}.evidence[{index}]",
                        f"research cannot be used as formal evidence: {research_ref}",
                    )
                )


def _research_reference(evidence: Evidence) -> str | None:
    for value in (
        evidence.filepath,
        evidence.attachment_id,
        evidence.uri,
        evidence.ref,
        evidence.excerpt,
    ):
        if value is None:
            continue
        normalized = value.replace("\\", "/")
        if RESEARCH_ID_PATTERN.fullmatch(normalized):
            return value
        if normalized.startswith(("research/", "kb/research/")) or "/research/" in normalized:
            return value
    return None


def _evidence_schema_error(report: ValidationReport, field_name: str, message: str) -> None:
    report.errors.append(ValidationIssue(IssueCode.E_SCHEMA, field_name, message))


def _validate_evidence_existence(entry: Entry, repo_root: Path, report: ValidationReport) -> None:
    root = repo_root.resolve()
    tracked_cache: dict[str, bool] = {}
    repo_checked = False
    repo_has_git = False
    reported_repo_error = False
    for field_name, evidence in _iter_evidence(entry):
        for index, item in enumerate(evidence):
            prefix = f"{field_name}.evidence[{index}]"
            if item.type == EvidenceType.CODE and item.filepath:
                if not repo_checked:
                    repo_has_git = _is_git_repo(root)
                    repo_checked = True
                if not repo_has_git:
                    if not reported_repo_error:
                        report.errors.append(
                            ValidationIssue(
                                IssueCode.E_SCHEMA,
                                "repo_root",
                                f"repo_root is not a git work tree: {root}",
                            )
                        )
                        reported_repo_error = True
                elif not _git_tracks_file(root, item.filepath, tracked_cache):
                    report.errors.append(
                        ValidationIssue(
                            IssueCode.E_EVIDENCE_NOT_FOUND,
                            f"{prefix}.filepath",
                            f"code evidence file is not tracked by git: {item.filepath}",
                        )
                    )
            elif (
                item.type in {EvidenceType.LOG, EvidenceType.ATTACHMENT}
                and item.attachment_id
                and not _attachment_exists(root, item.attachment_id)
            ):
                report.errors.append(
                    ValidationIssue(
                        IssueCode.E_EVIDENCE_NOT_FOUND,
                        f"{prefix}.attachment_id",
                        f"attachment evidence was not found: {item.attachment_id}",
                    )
                )


def _iter_evidence(entry: Entry) -> list[tuple[str, list[Evidence]]]:
    evidence_sets = [("credibility", entry.credibility.evidence)]
    for heading, section in entry.section_credibility.items():
        if section.evidence is not None:
            evidence_sets.append((f"section_credibility.{heading}", section.evidence))
    return evidence_sets


def _has_evidence_targets_to_check(entry: Entry) -> bool:
    return any(
        (item.type == EvidenceType.CODE and bool(item.filepath))
        or (item.type in {EvidenceType.LOG, EvidenceType.ATTACHMENT} and bool(item.attachment_id))
        for _, evidence in _iter_evidence(entry)
        for item in evidence
    )


def _git_tracks_file(root: Path, filepath: str, cache: dict[str, bool]) -> bool:
    if filepath in cache:
        return cache[filepath]
    if not _is_relative_posix_path(filepath):
        cache[filepath] = False
        return False
    pathspec = f":(literal){filepath}"
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", pathspec],
        capture_output=True,
        text=True,
        check=False,
    )
    tracked_paths = [line.strip().replace("\\", "/") for line in result.stdout.splitlines()]
    candidate = root.joinpath(*filepath.split("/"))
    cache[filepath] = result.returncode == 0 and tracked_paths == [filepath] and candidate.is_file()
    return cache[filepath]


def _attachment_exists(root: Path, attachment_id: str) -> bool:
    if not _is_relative_posix_path(attachment_id):
        return False
    attachment_root = (root / "kb" / "attachments").resolve()
    candidates = [
        (attachment_root / attachment_id).resolve(),
        (attachment_root / "public" / attachment_id).resolve(),
        (attachment_root / "private" / attachment_id).resolve(),
    ]
    return any(
        candidate.is_file() and _is_relative_to(candidate, attachment_root)
        for candidate in candidates
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_relative_posix_path(value: str) -> bool:
    return (
        RELATIVE_POSIX_PATH_PATTERN.match(value) is not None
        and "\\" not in value
        and WINDOWS_DRIVE_PATH_PATTERN.match(value) is None
    )


def _is_git_repo(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates
