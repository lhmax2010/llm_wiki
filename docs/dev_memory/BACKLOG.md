# Dev Memory Backlog

## Seed Data Robustness

- [ ] YAML implicit scalar normalization: real seed entry validation exposed that
  human-written YAML can parse unquoted `created` / `updated` timestamps as
  datetime objects and values such as `error_codes: [-1]` as integers, while
  the schema expects strings. The current workaround is to quote those values
  when writing seed data. A future hardening pass should normalize these fields
  in `read_entry` or validation, converting datetime/int scalars to strings so
  real human and agent input is more robust.

## Web Readonly Hardening

- [ ] Add cache/rate-limit controls or stronger index-side filtering for
  network read endpoints. P7a search and P7b graph both inherit the P4 M1
  behavior where indexes are mainly path catalogs and requests may fan out into
  full published-entry scans plus Pydantic validation. This is acceptable for
  the current small intranet KB, but broader rollout should either move more
  filtering into the P4 index or add edge caching and request throttling.
- [ ] Add human-view redaction policy for full `get_entry` JSON. P7a returns
  complete JSON to the frontend and relies on the UI to hide internal fields;
  later phases should formalize §5.2 desensitization for fields such as
  `author`, `git_sha`, and other internal metadata.

## Web Write Hardening

- [ ] Replace P8 `X-KB-User` intranet trust header with real authentication
  before broader rollout. The header is forgeable and only acceptable for the
  current inner-network MVP boundary.
- [ ] Replace P8 minimal write-intent header with a real CSRF/session/token
  model when proper Web authentication is introduced.
- [ ] Add a merge/replace flow for duplicate pending proposals. P8 currently
  rejects a second pending edit for the same entry with `E_DUP`.
- [ ] Add a per-entry Web edit lock or equivalent guard for concurrent PATCH
  TOCTOU around "pending proposal exists" checks.
- [ ] Revisit IDAllocator lifetime. P8 rebuilds allocation state before Web
  create, but allocator ownership/lifecycle is still app-service local.
- [ ] Clarify P8 update trust-state placeholder comments. Update payloads start
  from the published entry and `review_route` converts the proposal to pending;
  this is correct but easy to misread.

## Tooling Consistency

- [ ] Give `scripts/rebuild_indexes.py` the same `sys.path` bootstrap that
  `scripts/build_module_views.py` uses. Running it as plain
  `python scripts/rebuild_indexes.py` fails with
  `ModuleNotFoundError: No module named 'index'`, because direct script
  invocation puts `scripts/` on `sys.path` rather than the repo root; it only
  works under `uv run`. `scripts/validate_skills.py` is stdlib-only today, so
  it is unaffected, but it would hit the same wall the moment it imports from
  the project.
- [ ] Update `docs/DEPLOYMENT.md:127` when the above lands. It documents
  `uv run python scripts/rebuild_indexes.py --kb-root kb`, which is correct
  today but should be simplified alongside the bootstrap so the docs and the
  scripts agree on one invocation style.

## Credibility Integrity

- [ ] Structured evidence entry UI for the Web edit form. PR #17 made the edit
  form stop sending `credibility` at all, because a single textarea cannot
  represent `list[Evidence]` and the form has no basis for a
  `claim_type`/`support_strength` verdict. The consequence is that evidence is
  currently not editable from the Web; use MCP or CLI. The root fix is a
  structured editor (per-item type + type-specific fields). The backend is
  already ready for it: `_merge_patch_into_payload` accepts
  `{"credibility": {"evidence": [...]}}` and merges sub-field-wise, so this
  needs no further backend change.
- [ ] Audit the MCP and other write paths for the same shallow-merge defect
  PR #17 fixed in the Web path. `propose_update_from_web` is web-only and MCP
  handlers do not reuse it, so PR #17 did not touch them, but the pattern
  (`payload.update(patch)` over a previously published entry) may be repeated.
  Check specifically whether any path lets a partial `credibility` — or a
  `credibility` with an omitted `evidence` defaulting to `[]` — replace a
  published verdict.
- [ ] Consider extending sub-field merging to `section_credibility` and
  `code_binding` on PATCH. Both are still whole-value replaces, which is the
  same class of risk as the credibility bug. Left out of PR #17 deliberately to
  keep the blast radius small; the boundary is documented in
  `_merge_patch_into_payload` and `docs/design.md` §4.1.2 so it is not mistaken
  for a general deep merge.

## Web Review Hardening

- [ ] For future proposal subtypes, add paired approve/reject lifecycle tests
  when the subtype is introduced. PR #12 fixed the P8 approve-republish
  counterpart that was missing for update reject; new review modes should keep
  both directions symmetric from day one.
- [ ] Add search-time stale index detection or fallback. The P5 review service
  now refreshes human and agent search indexes after successful publish, but
  query-time detection would still help recover from manually edited files,
  copied KB data, or interrupted maintenance workflows.
- [ ] Replace publish-time full index rebuild with an incremental update or
  debounced background refresh once the KB grows. Full rebuild is acceptable for
  the current intranet-scale dataset and keeps P4 source-dir isolation simple.
- [ ] Review P4/P5 SQLite connection lifecycle and standardize `closing()` usage
  where needed. Phase 8b review noted ResourceWarning risk in inherited index /
  review paths, but it is not specific to the Web review wrapper.
- [ ] Rename `_write_user` or split a `_review_user` dependency. Phase 8b uses
  the same intranet `X-KB-User` boundary for `GET /api/review/queue`, which is
  reviewer-only but not a write action.
- [ ] Revisit queue visibility by review level if the reviewer pool grows.
  Current MVP lets any reviewer-capable user see the queue metadata; future
  role separation can hide heavy items from light-only reviewers.
