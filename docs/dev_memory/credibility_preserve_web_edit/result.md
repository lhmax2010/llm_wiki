# Credibility Preservation on Web Edit — Result

## Final Status

Merged via PR #17 after single-track Claude review. Two commits, individually
revertable, landed in the required order: `c0cd6ea` (FIX-2, backend) then
`aef2677` (FIX-1, frontend).

## What Changed

### Backend — `web_api/service.py`

- Added `CredibilityPatch`: a PATCH-only model whose `claim_type`,
  `support_strength`, and `evidence` are all optional and default to `None`.
- `WebEntryPatchRequest.credibility` now uses it instead of the full
  `Credibility` model.
- `propose_update_from_web` calls `_merge_patch_into_payload` instead of
  `payload.update(patch)`. Top-level fields still replace wholesale;
  `credibility` merges at sub-field level.

### Frontend — `web/src/App.tsx`

- `updatePayload` omits `credibility` entirely.
- `sharedEditorPayload` returns
  `Omit<EntryWritePayload, "entry_type" | "credibility">`, so the type system
  prevents credibility from re-entering the update path; `createPayload` adds
  it explicitly.
- Edit-mode Evidence box is read-only, lists every evidence item via
  `evidenceSummary()`, and states what the edit preserves.
- `EditorState` gained `evidenceCount`.
- `evidenceText` now renders all items instead of only `evidence[0]`'s excerpt.

### Docs

- `docs/design.md` §4.1.2 records the PATCH merge semantics and the boundary.

## Governance

- The Web edit form no longer expresses an opinion about credibility. What the
  form cannot represent, it does not touch.
- `claim_type` and `support_strength` on an existing entry are now changeable
  only through a caller that states them explicitly — not as a side effect of
  editing an unrelated field.
- **`support_strength` can no longer be inflated by an edit.** This was the
  most damaging symptom: a `weak` entry came out of a title edit claiming
  `strong`, asserting more confidence than its evidence supports. Losing
  evidence leaves the KB incomplete; inflating support strength makes it
  actively misleading, which is the failure mode an evidence-driven KB exists
  to prevent.
- Review routing is unchanged. `claimed_change_scopes = ["web_edit"]` sits
  outside `LIGHT_SCOPES`, so every Web write was and remains `heavy` + staging.
  No previously-heavy edit becomes light as a result of this change.
- Evidence is no longer editable from the Web form. This is a deliberate
  removal, not a regression: the previous behaviour collapsed N structured
  items into one `human_note`, so the capability was a net negative.

## Verification

- `.venv/Scripts/python.exe -m pytest` passed: 244 passed, coverage 88.32%.
- `.venv/Scripts/python.exe -m ruff check .` passed.
- `MYPYPATH=governed-api .venv/Scripts/python.exe -m mypy web_api core` passed.
- `npm run lint` passed.
- `npm run test` passed: 12 passed.
- `npm run build` passed.

Key coverage:

- **B4** `test_web_patch_unrelated_field_preserves_published_credibility` —
  `fact` / `weak` with three mixed evidence items, PATCH title only, staged
  proposal's credibility equal field-by-field to the published one.
- **B5** `test_web_patch_unrelated_field_does_not_inflate_support_strength` —
  standalone `!= "strong"` assertion, kept separate so a regression names the
  dangerous symptom directly.
- **B9** `test_web_patch_review_approve_preserves_credibility_end_to_end` —
  PATCH title → assert `review_level == "heavy"` → reviewer approve → published
  file's credibility identical to before. Covers the whole governed path
  (merge → validate → stage → approve), not just the staging hop.
- **B6 / B7 / B8** — sub-field merge semantics, whole-list evidence replacement,
  and `{}` as a no-op.
- **F1 / F2 / F3** — edit sends no credibility and shows evidence read-only;
  an entry with no evidence is editable again; create still sends a complete
  credibility.

Regression strength was verified against pre-fix code rather than assumed:
B6/B7/B8 fail on the old backend and F1 fails on the old frontend, so those
four are the real guards. B4/B5/B9 pass on old code — a title-only PATCH never
carried a `credibility` key, so the shallow merge was never wrong for that
case — and lock the post-FIX-1 contract rather than demonstrating the FIX-2
defect. Recorded explicitly so later readers do not overrate their proving
power.

## Motivation

An entry's trust verdict is the product the KB sells. If editing a typo can
silently raise `support_strength` or delete evidence, every published verdict
becomes unreliable in a way no reader can detect from the entry itself.

## Follow-Ups

- Structured evidence entry UI, so evidence is editable from the Web again
  without loss. FIX-2's sub-field merge already accepts
  `{"credibility": {"evidence": [...]}}`, so no further backend change is
  needed for it.
- Audit MCP and other write paths for the same shallow-merge defect
  (`propose_update_from_web` is web-only; MCP handlers do not reuse it).
- `section_credibility` and `code_binding` are still whole-value replaces on
  PATCH — same class of risk, left out of this change on purpose.
