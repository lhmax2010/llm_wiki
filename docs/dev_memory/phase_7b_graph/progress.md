# Phase 7b - Knowledge Graph + Related Editing / Progress

## 2026-06-18

### Decisions

- Risk: 中-高（偏高）。Related editing touches the Web write path, while graph
  visualization is read-only.
- Related write strategy: no new related write endpoint. Create/edit continue
  through P8 `POST /api/entries` and `PATCH /api/entries/{id}`, which call the
  Phase 2 governed pipeline.
- Related validation location: P1 `validate_entry()`. This makes Web, MCP, CLI,
  and later tools inherit the same rules.
- Related target rule:
  - accept only `KB-\d{4}-\d{4}`;
  - reject `R-*`/research by shape and by never consulting `research/`;
  - target must exist in `entries/`, `staging/`, or `deprecated/`;
  - self-related is rejected;
  - cycles such as A->B and B->A are allowed.
- Graph read rule: `GET /api/graph` uses the P7a/P4 published-only safe reader
  (`read_valid_entries_from_source(kb_root, "entries")`), then renders only
  edges whose source and target are both currently published.
- Graph cycle display: related remains directed data, but reciprocal A<->B is
  collapsed into one visual edge with `bidirectional: true` to avoid parallel
  line clutter.
- Frontend graph implementation: lightweight React/SVG, no new npm dependency.
  This avoids corporate npm/cert risk and is enough for the MVP.

### Implemented

- Added related target validation in `core/validation.py`.
- Added `GET /api/graph` in the Web API read surface.
- Added related editing to the React create/edit form.
- Added graph view with nodes, edges, and click-to-open detail.
- Added tests for:
  - malformed/research related ids;
  - missing targets;
  - staging/deprecated target acceptance;
  - self-edge rejection;
  - graph published-only filtering;
  - Web related writes through the existing propose endpoints;
  - no related-specific write endpoint;
  - frontend related payload and graph behavior.

### Targeted Verification

- `uv run pytest tests\core\test_validation.py -q --no-cov`
  - `43 passed`
- `uv run pytest tests\web_api\test_app.py -q --no-cov`
  - `38 passed, 1 warning`
- `npm.cmd test -- --run`
  - `7 passed`
- `npm.cmd run lint`
  - passed
- `npm.cmd run build`
  - passed

### TODO / Follow-Up

- Large graph performance is intentionally not optimized in this MVP. Add
  filtering/centering/caching if graph size grows.
- Related duplicate-edge normalization is not enforced yet; graph display
  collapses reciprocal visual edges, but stored data can still contain repeated
  human entries.
