# Credibility Preservation on Web Edit — Plan

## Problem

Editing any field of an entry through the Web form rewrote the entry's
credibility. The edit form rebuilt `credibility` from scratch on every submit,
hard-coding three values, and the backend merged the PATCH body shallowly, so
the rebuilt object replaced the published one outright.

Editing only the title of a `fact` / `weak` entry holding three evidence items
proposed:

- `claim_type` → `observation` (hard-coded)
- `support_strength` → `strong` (hard-coded)
- `evidence` → one `human_note` built from a single textarea

Three losses, in ascending order of severity:

1. Evidence beyond what the textarea could represent was dropped
   (`code` filepath/line/sha, `log` attachment_id, `ticket` ref, and every
   item after the first).
2. `claim_type` was overwritten with a guess the form had no basis for.
3. **`support_strength` was inflated (weak → strong).** This is the worst of
   the three and the reason this was treated as a governance defect rather
   than a data-loss bug: losing evidence removes something, but inflating
   support strength makes the entry claim more confidence than its evidence
   supports. The KB then actively misleads instead of merely being incomplete.

A second, wider path was found during investigation and is unrelated to the
frontend: `WebEntryPatchRequest.credibility` was typed as the full
`Credibility` model, whose `evidence` field uses `default_factory=list`. Any
caller (curl included) that sent `credibility` while omitting `evidence` had it
filled with `[]` by Pydantic and persisted. Evidence cleared, no frontend
involved.

## Severity: medium-high, not high

Deliberately downgraded from the initial assessment after reading the
governance chain:

- All Web writes are forced to `staging` by `_require_web_staging_target`;
  nothing can land in `entries/` directly.
- `claimed_change_scopes = ["web_edit"]`, and `"web_edit"` is in neither
  `AUTO_SCOPES` nor `LIGHT_SCOPES`, so `_classify_claimed_change` returns
  `heavy` unconditionally. Every Web edit is a heavy review.

So corruption required a reviewer to approve it. The risk is real — the
reviewer sees a proposal labelled "title change" and the credibility diff is
easy to wave through — but there is a human gate, and calling it "silently
lands in the KB" would have been wrong.

The same fact removes a risk from the fix: because the claimed scope pins the
level at `heavy` regardless, **this change cannot alter review routing.** There
is no path where a previously-heavy edit becomes light and slips through.

## Contract

Two changes, landing in a fixed order (FIX-2 first, see below).

### FIX-1 — the form stops speaking for credibility

- `updatePayload` omits the `credibility` key entirely.
- Omit rather than echo the values read at load time. Echoing reintroduces the
  same class of bug through a different door: it would clobber a concurrent
  edit with values that were correct only when the form opened. An absent key
  means "I have nothing to say about this field", which is true of this form.
- Create still sends `credibility`. There is no published entry to inherit a
  verdict from, and the author's note is a legitimate first piece of evidence.
- In edit mode the Evidence box becomes read-only, listing every item, with a
  note stating what the edit preserves. An editable box that silently discards
  what the user types would be worse than the original bug.

Principle: **what this form cannot represent, it must not touch.**

### FIX-2 — the backend stops accepting a wholesale credibility replace

- `credibility` merges at sub-field level; an omitted sub-field keeps its
  published value.
- Every other top-level field keeps replacing wholesale.

| patch | result |
|---|---|
| no `credibility` key | all three sub-fields preserved |
| `{"support_strength": "moderate"}` | only that changes |
| `{"evidence": [...]}` | evidence list replaced whole; other two preserved |
| `{"evidence": []}` | explicit clear (distinct from omitting) |
| `{}` | no-op |

Boundary, deliberately narrow and written into both the helper docstring and
`docs/design.md` §4.1.2:

- `section_credibility` — still a whole-value replace.
- `code_binding` — still a whole-value replace.
- The `evidence` list itself — supplying it replaces it. Evidence items have
  no stable identity, so item-level merging cannot be implemented safely.

## Order: FIX-2 first, and it cannot be reversed

For a complete credibility object, `{**previous, **complete}` is identical to
`complete`. FIX-2 is therefore a no-op for the existing frontend and can land
alone with zero behaviour change. Behaviour only changes once FIX-1 follows.

Landing FIX-1 first would technically work — a patch with no `credibility` key
preserves the published value even under a shallow merge — but the protection
would rest entirely on the frontend, and reverting FIX-1 would leave the system
unprotected.

## Explicit Non-Goals

- Structured evidence entry UI (the real fix for editing evidence from the
  web). Deferred; FIX-2's sub-field merge already accepts
  `{"credibility": {"evidence": [...]}}`, so that work will not need another
  backend change.
- Deep-merging `section_credibility` or `code_binding`. Same class of risk,
  deliberately out of scope to keep the blast radius small.
- Item-level evidence merging.
- Auditing other write paths (MCP, governed-api) for the same shallow-merge
  defect. Tracked as a separate investigation; `propose_update_from_web` is
  web-only and MCP does not reuse it, so it does not block this change.
