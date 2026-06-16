"""Validate Phase 10a agent skill contracts."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SkillSpec:
    filename: str
    required_headings: tuple[str, ...]
    required_terms: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkillValidationIssue:
    path: Path
    code: str
    message: str


INGEST_SPEC = SkillSpec(
    filename="ingest_skill.md",
    required_headings=(
        "# 入库 Skill（行为契约）",
        "## 目标",
        "## 适用场景",
        "## 使用的 MCP 工具",
        "## 流程",
        "## 证据纪律",
        "## 禁止事项",
    ),
    required_terms=(
        "search_kb",
        "get_entry",
        "propose_entry",
        "propose_update",
        "entry_type",
        "evidence",
        "claim_type",
        "warnings",
        "errors",
        "P1-P5",
    ),
)

MAINTENANCE_SPEC = SkillSpec(
    filename="maintenance_skill.md",
    required_headings=(
        "# 维护 Skill（行为契约）",
        "## 目标",
        "## 适用场景",
        "## 使用的 MCP 工具",
        "## 强制维护检查点",
        "## stale 判断",
        "## 证据纪律",
        "## 禁止事项",
    ),
    required_terms=(
        "search_kb",
        "get_entry",
        "propose_update",
        "code_binding",
        "stale",
        "stale_reason",
        "evidence",
        "claim_type",
        "诊断报告",
        "P1-P5",
    ),
)

REQUIRED_SKILLS: tuple[SkillSpec, ...] = (INGEST_SPEC, MAINTENANCE_SPEC)
ALLOWED_MCP_TOOLS: frozenset[str] = frozenset(
    {"search_kb", "get_entry", "propose_entry", "propose_update"}
)
KNOWN_MCP_TOOLS: frozenset[str] = frozenset(
    {
        "search_kb",
        "get_entry",
        "list_categories",
        "browse",
        "propose_entry",
        "propose_update",
        "search_research_for_hints",
    }
)
PROHIBITION_MARKERS: tuple[str, ...] = (
    "不",
    "不要",
    "不得",
    "不能",
    "不允许",
    "禁止",
    "严禁",
    "只能",
    "只允许",
    "绝不",
)
TOOL_RE = re.compile(
    r"\b(search_kb|get_entry|list_categories|browse|propose_entry|"
    r"propose_update|search_research_for_hints)\b"
)
DANGEROUS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "DIRECT_KB_WRITE",
        re.compile(
            r"(?:请|务必|必须|应该|可以|允许|需要|agent\s*(?:应|可以)|you\s+(?:may|must|should))"
            r".{0,16}(?:直接|手动|自行|自己)?"
            r".{0,12}(?:写入|写|修改|改动|创建|移动|删除|write|edit|modify|create|delete)"
            r".{0,32}(?:kb/)?(?:entries|staging|deprecated|indexes|audit|sqlite|published)",
            re.IGNORECASE,
        ),
    ),
    (
        "BYPASS_GOVERNANCE",
        re.compile(
            r"(?:请|务必|必须|应该|可以|允许|需要|agent\s*(?:应|可以)|you\s+(?:may|must|should))"
            r".{0,16}(?:绕过|跳过|不走|避开|bypass|skip)"
            r".{0,24}(?:治理|审核|review|MCP|pipeline|propose|P1-P5)",
            re.IGNORECASE,
        ),
    ),
    (
        "SELF_ASSERT_CLAIM_TYPE",
        re.compile(
            r"(?:请|务必|必须|应该|可以|允许|需要|agent\s*(?:应|可以)|you\s+(?:may|must|should))"
            r".{0,20}(?:自报|声明|指定|declare|set)"
            r".{0,20}(?:高可信|fact|spec|claim_type)",
            re.IGNORECASE,
        ),
    ),
)


def validate_all(repo_root: Path) -> list[SkillValidationIssue]:
    issues: list[SkillValidationIssue] = []
    skills_root = repo_root / "kb" / "skills"
    for spec in REQUIRED_SKILLS:
        issues.extend(validate_skill(skills_root / spec.filename, spec))
    return issues


def validate_skill(path: Path, spec: SkillSpec | None = None) -> list[SkillValidationIssue]:
    issues: list[SkillValidationIssue] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [SkillValidationIssue(path, "E_ENCODING", f"not valid UTF-8: {exc}")]
    except OSError as exc:
        return [SkillValidationIssue(path, "E_MISSING", f"cannot read skill: {exc}")]

    if spec is not None:
        issues.extend(_validate_required_shape(path, text, spec))
    issues.extend(_validate_mcp_tools(path, text))
    issues.extend(_validate_dangerous_instructions(path, text))
    return issues


def _validate_required_shape(
    path: Path,
    text: str,
    spec: SkillSpec,
) -> list[SkillValidationIssue]:
    issues: list[SkillValidationIssue] = []
    headings = {line.strip() for line in text.splitlines() if line.startswith("#")}
    for heading in spec.required_headings:
        if heading not in headings:
            issues.append(SkillValidationIssue(path, "E_SECTION", f"missing heading: {heading}"))
    for term in spec.required_terms:
        if term not in text:
            issues.append(SkillValidationIssue(path, "E_TERM", f"missing required term: {term}"))
    return issues


def _validate_mcp_tools(path: Path, text: str) -> list[SkillValidationIssue]:
    issues: list[SkillValidationIssue] = []
    mentioned = {tool for tool in TOOL_RE.findall(text) if tool in KNOWN_MCP_TOOLS}
    for tool in sorted(mentioned - ALLOWED_MCP_TOOLS):
        issues.append(
            SkillValidationIssue(
                path,
                "E_TOOL",
                f"P10a skill must not direct agents to use MCP tool: {tool}",
            )
        )
    return issues


def _validate_dangerous_instructions(path: Path, text: str) -> list[SkillValidationIssue]:
    issues: list[SkillValidationIssue] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        normalized = line.strip()
        if not normalized or _is_prohibition_line(normalized):
            continue
        for code, pattern in DANGEROUS_PATTERNS:
            if pattern.search(normalized):
                issues.append(
                    SkillValidationIssue(
                        path,
                        code,
                        f"line {line_number} looks like a governance-bypass instruction",
                    )
                )
    return issues


def _is_prohibition_line(line: str) -> bool:
    return any(marker in line[:12] for marker in PROHIBITION_MARKERS)


def format_issues(issues: Sequence[SkillValidationIssue]) -> str:
    return "\n".join(f"{issue.path}: {issue.code}: {issue.message}" for issue in issues)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate kb/skills agent contracts")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)

    issues = validate_all(args.repo_root)
    if issues:
        print(format_issues(issues), file=sys.stderr)
        return 1
    print("skill contracts validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
