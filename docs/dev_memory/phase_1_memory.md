# Phase 1 Memory: Content Core + Schema + Validation

## Context

Phase 1 implements the content-core foundation from `docs/design.md` v1.3:
schema models, pure validation, SQLite ID issuance, markdown/frontmatter storage,
and physical directory/trust_state consistency.

## Key Decisions

- Dependency choice approved by developer: `pydantic>=2,<3` for schema models and
  validators; `PyYAML>=6,<7` for frontmatter parsing and writing.
- SQLite ID issuance uses one transactional allocator table keyed by year. Allocation
  uses `BEGIN IMMEDIATE` so concurrent writers serialize at the database write lock.
  This prioritizes uniqueness and allows gaps, matching design §4.2.1.
- ID allocator rebuild scans `kb/entries`, `kb/staging`, `kb/drafts`, and
  `kb/deprecated`, excluding `kb/research`, then seeds next number as max+1. The
  return value is the effective post-rebuild next number, so it never reports a value
  lower than an already-live SQLite sequence.
- Rebuild and storage reads fail fast on non-UTF-8 entry files instead of silently
  ignoring bad bytes. This preserves ID uniqueness during rebuild and gives a clear
  operator error.
- Evidence mapping is evidence-driven, not author-declared. Downgradable mismatches
  emit `W_DOWNGRADE`; non-downgradable mismatches emit errors.
- Section-level credibility with local evidence materializes any inherited-claim
  downgrade onto the normalized section result, keeping warnings and returned state
  aligned.
- Directory is the primary trust-state boundary. A path under a state directory whose
  frontmatter `trust_state` disagrees is `E_SCHEMA`, never a warning.
- Phase 1 validates `code_binding` field shape and formats only. It does not calculate
  actual `path_hash`, `symbol_hash`, or stale state; clangd/tree-sitter stays out of P1.
- Markdown section detection ignores fenced code blocks and rejects duplicate headings,
  so embedded log/code snippets do not create false `E_SCHEMA` heading errors.
- Repository-relative path validation rejects POSIX traversal, Windows backslashes, and
  Windows drive prefixes such as `C:/x` and `C:x`.
- Pydantic keeps enum instances internally and serializes enum values at YAML/JSON output
  time. This avoids string-vs-enum comparison mistakes in validators.
- PyYAML is treated as an untyped third-party boundary with a narrow
  `# type: ignore[import-untyped]`; no extra `types-PyYAML` dependency was added.

## Implemented Files

- `core/models.py`: Pydantic models and enums for design §4.4.
- `core/errors.py`: design error/warning code enum and `ValidationIssue`.
- `core/validation.py`: entry schema validation, section skeleton checks, evidence mapping,
  evidence existence checks, directory/trust_state checks, and code_binding shape checks.
- `core/id_allocator.py`: SQLite ID allocator with transactional `BEGIN IMMEDIATE`
  allocation and rebuild seeding.
- `core/storage.py`: Markdown + YAML frontmatter read/write helpers.
- `tests/core/`: unit/integration coverage for schema, evidence mapping, ID allocation,
  directory consistency, code_binding shape, and storage roundtrip.

## Commands Run So Far

- `uv add --system-certs "pydantic>=2,<3" "PyYAML>=6,<7"`: installed
  `pydantic==2.13.4`, `pyyaml==6.0.3`.
- `uv run ruff format .`: `10 files left unchanged` after final formatting.
- `uv run ruff check .`: `All checks passed!`.
- `uv run mypy core tests`: `Success: no issues found in 10 source files`.
- `uv run pytest -q`: `26 passed in 1.81s`; core coverage total `97.26%`.
- Final `uv run pytest -q`: `38 passed in 2.62s`; core coverage total `96.01%`.

Intermediate failures and fixes:

- First `uv sync` needed `--system-certs` due enterprise TLS interception.
- First `ruff check` found `SIM102` and `B009`; fixed the nested `if` and typed test helper.
- First `pytest` collection could not import `core`; added `pythonpath = ["."]` under pytest
  config.
- First `mypy` run flagged untyped `yaml`; contained the untyped import in `core/storage.py`.
- Initial `core/validation.py` coverage was only ~82%; added targeted high-risk branch tests
  until validation coverage reached 97%.
- Claude diff/read-only review found and confirmed fixes for: tautological heading tests,
  rebuild return value drift, non-UTF-8 silent skips, inherited section downgrade mismatch,
  non-git repo handling, ID overflow, Windows drive paths, fenced-code heading false
  positives, duplicate heading detection, and storage UTF-8 errors.
- `codex review --uncommitted` could not inspect the diff in this Windows environment:
  every nested shell invocation failed with `CreateProcessWithLogonW failed: 1385`.
  This is recorded as review blocked, not approval.

## Test Coverage Snapshot

Final `uv run pytest -q`:

```text
38 passed in 2.62s
core\__init__.py      100%
core\errors.py        100%
core\id_allocator.py   92%
core\models.py        100%
core\storage.py        91%
core\validation.py     96%
TOTAL                  96.01%
```

## Remaining Work

- Prepare PR and high-risk review package for external ChatGPT/Kimi review.
- R14 review closure and checkpoint tag happen after review findings are handled and the
  developer approves merge.
