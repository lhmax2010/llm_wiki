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
- Initial frontend graph implementation: lightweight React/SVG with no graph
  layout dependency. This was enough for the MVP but became visually cramped
  with real larger data.

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

## 2026-07-13

### Force-Directed Graph Layout Follow-Up (PR #15)

- Real work-machine validation showed that the fixed circle layout becomes
  cramped once many published entries exist.
- Replaced the fixed ring layout with `d3-force@3.0.0` while keeping the
  existing React/SVG renderer and the existing `GET /api/graph` response.
- Backend graph rules did not change:
  - nodes remain published entries only;
  - edges remain `related` links whose source and target are both published;
  - research/staging/deprecated remain excluded from graph data.
- Implemented force layout with:
  - `forceManyBody` repulsion;
  - `forceLink` attraction for related edges;
  - `forceCenter` centering;
  - `forceCollide(radius = node.radius + 12, strength = 1, iterations = 2)`
    as the hard no-overlap guard.
- Added graph usability controls:
  - node radius scales by degree so hub knowledge is visually larger;
  - wheel zoom centered on the mouse position;
  - canvas drag/pan;
  - draggable nodes using the standard `fx`/`fy` + `alphaTarget` d3-force
    pattern;
  - click-vs-drag threshold to avoid opening entries while dragging;
  - Reset view;
  - Hide isolated toggle, enabled by default;
  - `requestAnimationFrame` throttling for simulation tick updates.
- New npm dependency:
  - `d3-force@3.0.0`;
  - `@types/d3-force` as a dev dependency;
  - local installed package footprint is about 163 KiB including
    `d3-dispatch`, `d3-quadtree`, and `d3-timer`.
- Runtime note: any machine pulling PR #15 or later must run `npm install`
  under `web/` before starting the frontend, otherwise Vite cannot resolve
  `d3-force`.

### Targeted Verification

- `npm.cmd run lint`
  - passed
- `npm.cmd run test`
  - `10 passed`
- `npm.cmd run build`
  - passed
- Local smoke:
  - `GET http://127.0.0.1:5174/api/graph` -> 200;
  - real local graph data returned 138 nodes and 6 edges.

### TODO / Follow-Up

- Large graph data fetching is still all-published-entry scan on `/api/graph`.
  Add server-side filtering/centering/caching if graph size grows further.
- Related duplicate-edge normalization is not enforced yet; graph display
  collapses reciprocal visual edges, but stored data can still contain repeated
  human entries.
