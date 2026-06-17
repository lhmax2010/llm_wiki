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

- [ ] Add cache/rate-limit controls for network read endpoints. P7a keeps the
  P4 thousand-entry MVP behavior, but exposing all-request scans through HTTP
  can amplify P4 M1 performance risk. Add caching and request throttling before
  broader intranet rollout.
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

## Web Review Hardening

- [ ] Review P4/P5 SQLite connection lifecycle and standardize `closing()` usage
  where needed. Phase 8b review noted ResourceWarning risk in inherited index /
  review paths, but it is not specific to the Web review wrapper.
- [ ] Rename `_write_user` or split a `_review_user` dependency. Phase 8b uses
  the same intranet `X-KB-User` boundary for `GET /api/review/queue`, which is
  reviewer-only but not a write action.
- [ ] Revisit queue visibility by review level if the reviewer pool grows.
  Current MVP lets any reviewer-capable user see the queue metadata; future
  role separation can hide heavy items from light-only reviewers.
