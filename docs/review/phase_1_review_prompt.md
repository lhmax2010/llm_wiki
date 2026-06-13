# Phase 1 Review Prompt

PR: pending
Risk: High
Review routing: Claude + ChatGPT + Kimi

## Scope

Phase 1 implements the content core:

- Pydantic schema models for design §4.4.
- Pure validation for entry skeletons, evidence mapping, evidence existence, directory
  trust_state consistency, and code_binding shape/format.
- SQLite ID allocator with transactional uniqueness and rebuild seeding.
- Markdown + YAML frontmatter storage helpers.

Explicitly out of scope: Governed API pipeline, MCP tools, staging/review workflow,
search/indexing, true hash calculation, clangd/tree-sitter symbol extraction, stale
detection, frontend, and collector.

## Design References

- `docs/design.md` §3.4 data model / section skeletons
- `docs/design.md` §4.1.3 evidence mapping rules
- `docs/design.md` §4.2.1 SQLite ID issuance and rebuild
- `docs/design.md` §4.2.2 physical state directories
- `docs/design.md` §4.4 schema types
- `docs/design.md` §7 Phase 1 scope and DoD
- `docs/hash_spec.md` for code_binding shape/format only

## Changed Files

- `.gitignore`
- `pyproject.toml`
- `uv.lock`
- `docs/design.md`
- `docs/design_changes/change_1.md`
- `docs/review/design_review_phase_1.md`
- `docs/dev_memory/INDEX.md`
- `docs/dev_memory/phase_1_memory.md`
- `core/__init__.py`
- `core/errors.py`
- `core/models.py`
- `core/validation.py`
- `core/id_allocator.py`
- `core/storage.py`
- `tests/core/conftest.py`
- `tests/core/test_validation.py`
- `tests/core/test_id_allocator.py`
- `tests/core/test_storage.py`

## Verification Commands

```text
uv run ruff format .
-> 10 files left unchanged

uv run ruff check .
-> All checks passed!

uv run mypy core tests
-> Success: no issues found in 10 source files

uv run pytest -q
-> 38 passed in 2.62s
-> TOTAL coverage 96.01%
-> core/validation.py 96%, core/id_allocator.py 92%, core/storage.py 91%
```

## Local Review Results

Claude read-only review:

- First pass found actionable issues around section-heading test tautology, rebuild return
  values, UTF-8 strictness, inherited section downgrade materialization, non-git repo
  handling, ID overflow, Windows drive paths, fenced-code headings, duplicate headings,
  and storage non-UTF-8 errors.
- All high/medium findings were fixed and covered by tests.
- Follow-up Claude read-only review verdict: no remaining correctness blockers or
  high/medium issues.

Codex local review:

- Attempted `codex review --uncommitted`.
- Result: blocked by Windows sandbox process creation failure. Codex reported it could
  not inspect current changes because shell invocations failed with
  `CreateProcessWithLogonW failed: 1385`.
- Treat this as not approved by local Codex; rely on this PR diff plus external
  ChatGPT/Kimi review for the remaining high-risk review legs.

## Review Focus

Please review for:

- Evidence mapping correctness: downgrade vs reject behavior must match design §4.1.3.
- Section-level credibility: inherited claims with local section evidence must return a
  normalized section state that matches emitted downgrade warnings.
- Markdown body skeletons: required headings must match design literals, duplicate
  headings must be `E_SCHEMA`, and `##` inside fenced code blocks must not count as
  section headings.
- Evidence existence checks: `code` evidence via `git ls-files`, `log/attachment` under
  `kb/attachments/`; non-git `repo_root` is `E_SCHEMA`, not mass
  `E_EVIDENCE_NOT_FOUND`.
- SQLite ID allocator race safety: `BEGIN IMMEDIATE`, yearly sequence, rebuild scans
  `entries/staging/drafts/deprecated`, research excluded, rebuild returns effective
  next numbers, non-UTF-8 entries fail fast, and exhausted 4-digit sequences do not emit
  invalid IDs.
- Directory trust-state boundary: path state mismatch must be `E_SCHEMA`, not warning.
- code_binding shape-only boundary: validate hash formats and enums, do not compute real
  hashes or call clangd/tree-sitter. Path shape rejects traversal, backslashes, and
  Windows drive prefixes.
- Pydantic schema strictness and future compatibility with P2 middleware.
- Test gaps around high-risk behavior.

## Known Non-Issues / Intentional Boundaries

- `PyYAML` import is untyped and locally ignored at the import boundary; no extra stub
  dependency was added.
- `code_binding` hash values are checked for format only.
- `research/` is intentionally excluded from official KB ID rebuild scanning.
- `E_RESEARCH_AS_EVIDENCE` enforcement is Phase 6 research isolation scope per
  `docs/design.md` §7 Phase 6, not implemented in Phase 1.
- Checkpoint tag is deferred until review closure and merge approval per SOP.

## Coverage Exceptions

None for core business logic. Remaining uncovered lines are defensive error branches.
