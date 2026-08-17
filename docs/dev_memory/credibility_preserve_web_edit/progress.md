# Credibility Preservation on Web Edit — Progress

## 2026-08-17

### Investigation

- Reproduced the reported symptom first (Evidence box empty when editing) with
  a throwaway vitest probe against a mocked backend, rather than reasoning from
  the code. Two distinct findings came out of it:
  - The Evidence box was **not** always empty. `evidenceText` read
    `evidence[0]` and only recognised `excerpt / ref / uri / filepath`, so it
    returned `""` whenever the first item was e.g. `{type: "log",
    attachment_id: ...}`. For a `human_note` first item it filled correctly.
  - The empty box was not the data-loss path. The Evidence textarea was
    `required`, so an empty box blocked submission entirely — the entry could
    not be edited at all, and no PATCH was sent.
- The actual data loss happened when the box was **non**-empty: the probe
  captured the PATCH body for a title-only edit of a `fact` / `weak` entry with
  three evidence items and showed
  `{"claim_type":"observation","support_strength":"strong","evidence":[<1 item>]}`.
- Confirmed the read path was innocent: `get_entry` returns
  `model_dump(mode="json")` with credibility intact, and the frontend reads
  `entry.credibility.evidence`. Neither "backend does not return it" nor
  "backfill is missing" was true.
- Traced the governance chain to size the severity honestly:
  `_require_web_staging_target` forces staging, and `claimed_change_scopes =
  ["web_edit"]` is outside `LIGHT_SCOPES`, so `_classify_claimed_change`
  returns `heavy` for every Web write. Corruption needed reviewer approval.
  Downgraded medium-high from high on that basis, and established that the fix
  cannot change review routing.
- Found the second, frontend-independent path while reading the patch model:
  `Credibility.evidence` uses `default_factory=list`, so `exclude_none=True`
  could not stop an omitted `evidence` from being dumped as `[]` and persisted.

### FIX-2 — backend (commit `c0cd6ea`)

- Added `CredibilityPatch` with all three sub-fields optional and defaulting to
  `None`. This is the mechanism the whole fix rests on: `exclude_none=True` is
  recursive, but it can only drop `None`. With the old `default_factory=list`,
  an omitted `evidence` became `[]`, which is not `None`, so it survived the
  dump and wiped the published list. `[]` → `None` is what makes "omitted"
  distinguishable from "explicitly cleared".
- Pointed `WebEntryPatchRequest.credibility` at it, replacing the full
  `Credibility` model.
- Replaced `payload.update(patch)` with `_merge_patch_into_payload`, which
  replaces top-level fields wholesale and merges `credibility` sub-field-wise.
- Documented the boundary in the helper docstring and `docs/design.md` §4.1.2.

### FIX-1 — frontend (commit `aef2677`)

- `updatePayload` no longer sends `credibility`. `sharedEditorPayload`'s return
  type narrowed to `Omit<EntryWritePayload, "entry_type" | "credibility">`, so
  the compiler now prevents credibility from leaking back into the update path;
  create adds it explicitly.
- Evidence box in edit mode became a read-only textarea listing every item via
  `evidenceSummary()` (which handles all evidence shapes, unlike the old
  per-key lookup in `evidenceText`), plus a note naming what is preserved.
- Added `evidenceCount` to `EditorState` rather than counting lines in the
  joined string. An `excerpt` may contain a newline; a message that says "this
  edit preserves all N evidence items" and gets N wrong is exactly the kind of
  UI lie this change exists to remove.
- Dropping `required` in edit mode also unblocked entries with an empty
  evidence list (`KB-2026-0007`, `KB-2026-0008` in the live KB), which
  previously could not be edited at all.

## Verification

- `.venv/Scripts/python.exe -m pytest` passed: 244 passed, coverage 88.32%.
- `.venv/Scripts/python.exe -m ruff check .` passed.
- `MYPYPATH=governed-api .venv/Scripts/python.exe -m mypy web_api core` passed.
  (`MYPYPATH` mirrors the `pythonpath = [".", "governed-api"]` in
  `pyproject.toml`; without it mypy cannot resolve `governed_api` because the
  package lives in a hyphenated directory. Pre-existing, unrelated to this
  change.)
- `npm run lint` (`tsc --noEmit`) passed.
- `npm run test` passed: 12 passed.
- `npm run build` passed.

### Which tests are real regression guards

Checked each new test against the pre-fix code instead of assuming. This
matters for review: three of the tests named in the plan pass on old code.

| test | old code | guards |
|---|---|---|
| B6 / B7 / B8 | **fail** (422 — old model required a complete credibility) | FIX-2 |
| F1 | **fail** (`expect(element).toHaveAttribute("readonly")`) | FIX-1 |
| B4 / B5 / B9 | pass | the post-FIX-1 contract, not FIX-2 |

B4/B5/B9 send only `title`, and a title-only PATCH never carried a
`credibility` key, so the backend's shallow merge was never wrong for that
case — the bug was in what the frontend sent. They lock the contract in place
going forward; they do not demonstrate the FIX-2 defect.

## Notes

- The `fact` / `weak` fixture writes a real log attachment to
  `repo_root/kb/attachments/`. Without it `_has_fact_evidence` fails,
  `_normalize_credibility` downgrades `claim_type` to `observation`, and
  `_validate_evidence_existence` raises `E_EVIDENCE_NOT_FOUND`. The test would
  then have been asserting against a silently-downgraded observation rather
  than a real `fact`, which is precisely the failure it exists to catch.
- `_merge_patch_into_payload` builds a filtered copy rather than `pop`-ing from
  `patch`, so it does not mutate its second argument.
