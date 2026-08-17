# Summary Field Progress

## 2026-08-17

- Added optional `Entry.summary` with default empty string and 200-character
  limit.
- Added whitespace normalization so pasted multi-line summaries become a single
  line before validation.
- Added `summary` to `EntryUpdate`, Web create/patch DTOs, Web editor payloads,
  entry detail display, MCP browse summaries, and design schema docs.
- Added `summary` to P2 `LIGHT_FIELDS`; summary-only updates are light content
  changes, not unknown/heavy changes.
- Added search matching/scoring:
  - title: +10
  - summary: +8
  - error_codes: +5
  - body: +2
- Search snippets prefer summary when present/matching, and fall back to the
  existing title/body behavior when summary is empty.
- Updated `kb/skills/ingest_skill.md` and
  `kb/skills/whisper_ingest_skill.md`: agents draft summary and show it during
  human confirmation; KB does not generate it internally.

## Verification

- `uv run ruff check .` passed.
- `uv run mypy .` passed.
- `uv run pytest` passed: 238 passed, coverage 88.24%.
- `npm.cmd run lint` passed.
- `npm.cmd run test` passed: 10 passed.
- `npm.cmd run build` passed.

## Notes

- `summary` is intentionally not part of evidence mapping. Test coverage locks
  that adding summary does not upgrade a weak `fact` claim.
- Search index SQLite schema is unchanged; SQLite stores path metadata only.
  Search reads entries at query time, so summary matching requires no metadata
  migration.
