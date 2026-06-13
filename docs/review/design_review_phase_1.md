# Phase 1 Startup Design Review

Date: 2026-06-13
Scope: Phase 1 content core + schema + validation startup review.
Baseline: `docs/design.md` v1.2 Frozen, plus `docs/hash_spec.md`.

## Review Summary

Phase 1 is broadly implementable: the repository already has the expected monorepo
layout, Python 3.11+ toolchain, KB runtime directory skeleton, RBAC config, and frozen
design sections for Entry schema, evidence mapping, directory state boundaries, and
SQLite ID issuance.

However, the startup review found several contract mismatches that affect Phase 1
implementation. These should be resolved by the developer before coding begins, because
they change schema fields or validator behavior. `docs/design.md` remains unchanged.

## R12 Existing Asset Reuse

### Directly Reused

- `docs/design.md`: Frozen v1.2 source of truth for architecture, schema, API contracts,
  Phase DAG, and Phase 1 DoD.
- `docs/governance.md`: R1-R14 development rules, especially design immutability, R10,
  R12, R13, and R14.
- `docs/DEV_GUIDE.md`: single-machine development loop, risk tiers, three gates, and
  Phase closeout.
- `docs/hash_spec.md`: P1 prerequisite for `code_binding` hash semantics.
- `docs/PHASE1_STARTUP.md`: startup protocol already matches the current flow.
- `docs/test-guides/`: existing home for future third-gate checklists.
- `config/roles.yaml`: reusable RBAC seed config; YAML data is valid when read as UTF-8.
- `kb/entries`, `kb/staging`, `kb/drafts`, `kb/research`, `kb/deprecated`,
  `kb/attachments/{public,private}`, `kb/indexes`: reuse as the physical state and
  evidence boundary skeleton.
- `kb/skills/`: keep as existing skill-document location; not needed for Phase 1 code.
- `pyproject.toml` and `uv.lock`: use `uv run` for ruff, mypy, pytest, pytest-cov.
- `.gitattributes` and `.gitignore`: preserve LF policies and `.venv/` exclusion.

### Existing Asset Caveats

- `kb/skills/ingest_skill.md` and `kb/skills/maintenance_skill.md` appear mojibaked when
  read as UTF-8. This does not block Phase 1 schema code, but P10a should repair or
  regenerate these files before skill validation.
- `kb/synonyms.jsonl` appears mojibaked and likely invalid JSONL. This does not block
  Phase 1, but P4 should treat it as a broken seed asset, not trusted input.
- The repository directories `governed-api/` and `index/` are design-prescribed. For
  Python imports in later phases, use package-safe module names inside those directories
  rather than renaming the top-level directories without a design change.

### Phase 1 Write Targets

- `core/`: content-core package for schema models, validation, markdown/frontmatter
  storage, ID allocation, and directory-state checks.
- `tests/`: focused Phase 1 unit and integration tests.
- `docs/dev_memory/phase_1_memory.md` and `docs/dev_memory/INDEX.md`: after coding.
- `docs/review/phase_1_review_prompt.md`: after implementation and verification.
- `docs/checkpoints.md`: at Phase 1 closeout.

## Requirement Coverage

Covered for Phase 1:

- Four `entry_type` values are defined.
- Entry metadata and body shape are defined in §3.4 and §4.4.
- Section-level credibility is covered and keyed by Markdown heading text.
- Evidence types are enumerated in §4.4.
- Evidence mapping rules are defined in §4.1.3.
- Physical state directories and trust-state consistency are defined in §4.2.2.
- SQLite ID issuance and cold-start rebuild are defined in §4.2.1.
- Hash semantics are now supplied by `docs/hash_spec.md`.

Not fully covered without decision:

- Some hash-spec fields are missing from the frozen `CodeBinding` type.
- `observation` evidence eligibility is not exact enough for deterministic validation.
- Deprecated entries are omitted from SQLite sequence rebuild scanning, which can break
  global ID uniqueness.

## Module Decomposition

The module split is reasonable for the DAG:

- `core/` can own typed schema, pure validation, markdown/frontmatter IO, ID allocation,
  and path-state validation.
- `governed-api/` can later compose core validators into middleware.
- `mcp/`, `web/`, `collector/`, and `index/` can remain untouched in Phase 1.

No broad refactor is needed before Phase 1.

## Interface Contract Completeness

The §4.4 TypedDict definitions are sufficient as a baseline, but they are not sufficient
alone for a strict Pydantic implementation unless the issues below are resolved.

## Findings Requiring Decision

### [DESIGN_ISSUE] P1 scope still says "git-derived ID" while §4.2.1 requires SQLite-issued IDs

`docs/design.md` Phase 1 scope says "git-derived ID", but §4.2.1 and the schema comments
state that IDs are issued by SQLite (`KB-{year}-{NNNN}`), with uniqueness prioritized
over continuity. The current startup instruction also expects SQLite issuance.

Impact: implementing "git-derived ID" would violate the concurrency design; implementing
SQLite issuance technically contradicts the Phase 1 bullet.

Recommendation: update the Phase 1 scope wording to "SQLite-issued ID" and treat §4.2.1
as authoritative.

### [DESIGN_ISSUE] `docs/hash_spec.md` adds `CodeBinding` fields missing from §4.4

`docs/hash_spec.md` defines or uses:

- `symbol_hashes`
- `build_config_hash`
- `symbol_resolution`

The frozen §4.4 `CodeBinding` type contains `path_hashes`, `symbols`, and
`build_config_id`, but not those three fields.

Impact: a strict schema validator cannot both obey §4.4 and persist the hash-spec data.

Recommendation: extend `CodeBinding` in design with optional fields:

- `symbol_hashes: dict[str, str]`
- `build_config_hash: str`
- `symbol_resolution: Literal["exact", "fallback_path"]`

### [DESIGN_ISSUE] SQLite rebuild scan omits `deprecated/`, risking ID reuse after rebuild

§4.2.1 says SQLite rebuild scans `entries/` + `staging/` + `drafts/` and uses max ID + 1.
But `deprecated/` is also a physical state directory for former entries. If the highest
allocated ID exists only under `deprecated/`, a cold rebuild could allocate a duplicate
ID later.

Impact: global ID uniqueness can be broken after moving high-numbered entries to
deprecated and rebuilding SQLite.

Recommendation: include `deprecated/` in ID rebuild scanning. Keep `research/` out unless
research entries also use `KB-{year}-{NNNN}` IDs.

### [DESIGN_ISSUE] `observation` evidence rule is not deterministic enough

§4.1.3 says `observation` requires "观测记录", but §4.4 only enumerates generic evidence
types. It does not say which evidence types count as an observation record.

Impact: validators could diverge. One implementation might accept `human_note`, another
only `log` or `repro`, and both would appear plausible.

Recommendation: define `observation` evidence eligibility explicitly. Suggested rule:
accept `log`, `repro`, `ticket`, `human_note`, or `attachment` with a non-empty `excerpt`,
`ref`, or `attachment_id`; otherwise downgrade to `llm_hypothesis` with `W_DOWNGRADE`.

### [DESIGN_SUGGESTION] Clarify what Phase 1 validates for `symbol_hash`

`hash_spec.md` defines symbol-level hashing via clangd/tree-sitter. Phase 1 scope asks
for content-core schema and validation, while full stale detection appears later as an
offline health check.

Impact: implementing symbol extraction in Phase 1 would introduce parser dependencies
and expand scope. Only validating field shape and hash format may be enough for P1.

Recommendation: Phase 1 should validate `path_hashes`, `symbol_hashes`, and
`build_config_hash` shape/format, but not compute symbol hashes from source. Actual
symbol extraction can remain in the later stale health-check script unless the developer
explicitly expands Phase 1.

## Better-Approach Notes

- Keep `core/` dependency-light. Pydantic is a reasonable Phase 1 dependency, but it should
  be confirmed under R8 before coding.
- Keep storage and validation separable: model validation should not require a git working
  tree; evidence existence checks can accept a repository root.
- Treat markdown/frontmatter serialization as an adapter around typed Entry models, not as
  the canonical schema itself.

## Phase DAG Executability

The DAG is executable once the Phase 1 findings above are resolved. P1 can produce a
stable content-core API for P2 middleware, while P3/P4 can still branch from P2.

Critical path remains:

`P1 -> P2 -> P3 -> P5 -> P6 -> P8 -> P9`

## NFR Feasibility

- Security: directory-state validation and evidence existence checks are feasible in P1.
- Reliability: SQLite WAL + transaction-backed sequence allocation is feasible.
- Testability: P1 can cover schema, evidence mapping, directory mismatch, and concurrent
  ID allocation with unit/integration tests.
- Performance: P1 validation paths are local-file and SQLite operations, so no known
  performance blocker.

## Phase 1 Readiness Verdict

Developer decision: all DESIGN_ISSUE items and the code_binding shape-only suggestion were
accepted. `docs/design.md` was updated to v1.3 by the developer before Phase 1 coding.

Resolved status:

- SQLite-issued IDs are now authoritative, including the Phase 1 scope text.
- `CodeBinding` includes `symbol_hashes`, `build_config_hash`, and `symbol_resolution`.
- ID rebuild scanning includes `deprecated/`.
- `observation` evidence eligibility is explicit.
- Phase 1 validates `code_binding` field shape/format only; real hash computation and stale
  detection stay in the later health-check script.

Status: ready for Phase 1 coding.
