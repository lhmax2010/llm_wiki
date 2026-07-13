import {
  FormEvent,
  PointerEvent as ReactPointerEvent,
  WheelEvent as ReactWheelEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation
} from "d3-force";
import {
  approveReviewItem,
  getEntry,
  getGraph,
  getReviewDetail,
  listCategories,
  listReviewQueue,
  proposeEntry,
  proposeUpdate,
  rejectReviewItem,
  searchEntries
} from "./api";
import type {
  Categories,
  Entry,
  EntryWritePayload,
  GraphResponse,
  ReviewDetail,
  ReviewQueue,
  ReviewResult,
  SearchResult,
  WriteResult
} from "./types";
import "./styles.css";

type EditorMode = "new" | "edit";

type EditorState = {
  mode: EditorMode;
  title: string;
  module: string;
  entryType: string;
  body: string;
  tags: string;
  related: string;
  evidence: string;
};

const EMPTY_EDITOR: EditorState = {
  mode: "new",
  title: "",
  module: "",
  entryType: "defect_case",
  body: "",
  tags: "",
  related: "",
  evidence: ""
};
const SEARCH_PAGE_SIZE = 100;

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [hasMoreResults, setHasMoreResults] = useState(false);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [categories, setCategories] = useState<Categories | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [writer, setWriter] = useState("");
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [writeResult, setWriteResult] = useState<WriteResult | null>(null);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueue | null>(null);
  const [reviewDetail, setReviewDetail] = useState<ReviewDetail | null>(null);
  const [showReviewQueue, setShowReviewQueue] = useState(false);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewResult, setReviewResult] = useState<ReviewResult | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [showGraph, setShowGraph] = useState(false);

  useEffect(() => {
    void listCategories()
      .then(setCategories)
      .catch((exc: unknown) => setError(errorMessage(exc)));
    void runSearch("");
  }, []);

  async function runSearch(nextQuery: string) {
    setLoading(true);
    setError(null);
    try {
      const response = await searchEntries(nextQuery, SEARCH_PAGE_SIZE, 0);
      setResults(response.entries);
      setHasMoreResults(response.hasMore);
      if (response.entries.length > 0) {
        await selectEntry(response.entries[0].id);
      } else {
        setSelected(null);
      }
    } catch (exc) {
      setError(errorMessage(exc));
      setHasMoreResults(false);
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreResults() {
    setLoading(true);
    setError(null);
    try {
      const response = await searchEntries(query, SEARCH_PAGE_SIZE, results.length);
      setResults((current) => [...current, ...response.entries]);
      setHasMoreResults(response.hasMore);
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setLoading(false);
    }
  }

  async function selectEntry(id: string) {
    setError(null);
    try {
      setSelected(await getEntry(id));
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void runSearch(query);
  }

  function startNewEntry() {
    setWriteResult(null);
    setReviewResult(null);
    setShowReviewQueue(false);
    setReviewDetail(null);
    setShowGraph(false);
    setEditor(EMPTY_EDITOR);
  }

  function startEditEntry() {
    if (!selected) {
      return;
    }
    setWriteResult(null);
    setReviewResult(null);
    setShowReviewQueue(false);
    setReviewDetail(null);
    setShowGraph(false);
    setEditor({
      mode: "edit",
      title: selected.title,
      module: selected.module,
      entryType: selected.entry_type,
      body: selected.body,
      tags: selected.tags.join(", "),
      related: relatedText(selected),
      evidence: evidenceText(selected)
    });
  }

  async function submitEditor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor) {
      return;
    }
    setError(null);
    setWriteResult(null);
    try {
      const result =
        editor.mode === "new"
          ? await proposeEntry(createPayload(editor), writer.trim())
          : await proposeUpdate(selected?.id ?? "", updatePayload(editor), writer.trim());
      setWriteResult(result);
      if (result.ok) {
        setEditor(null);
        await runSearch(query);
      }
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  async function loadReviewQueue() {
    setError(null);
    setReviewResult(null);
    try {
      const queue = await listReviewQueue(writer.trim());
      setReviewQueue(queue);
      setReviewDetail(null);
      setShowReviewQueue(true);
      setShowGraph(false);
      setEditor(null);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  async function loadGraph() {
    setError(null);
    setWriteResult(null);
    setReviewResult(null);
    setReviewDetail(null);
    try {
      setGraph(await getGraph());
      setShowGraph(true);
      setShowReviewQueue(false);
      setEditor(null);
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  async function openEntry(id: string) {
    setShowGraph(false);
    setShowReviewQueue(false);
    setReviewDetail(null);
    setEditor(null);
    await selectEntry(id);
  }

  async function loadReviewDetail(id: string) {
    setError(null);
    try {
      setReviewDetail(await getReviewDetail(id, writer.trim()));
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  async function decideReview(id: string, decision: "approve" | "reject") {
    setError(null);
    setReviewResult(null);
    try {
      const result =
        decision === "approve"
          ? await approveReviewItem(id, writer.trim(), reviewNote)
          : await rejectReviewItem(id, writer.trim(), reviewNote);
      setReviewResult(result);
      if (result.ok) {
        setReviewQueue(await listReviewQueue(writer.trim()));
        setReviewDetail(null);
        await runSearch(query);
      }
    } catch (exc) {
      setError(errorMessage(exc));
    }
  }

  return (
    <main className="app-shell">
      <section className="search-pane" aria-label="Knowledge search">
        <div className="toolbar">
          <div>
            <h1>Unified KB</h1>
            <p>{categories ? `${categories.modules.length} modules indexed` : "Loading index"}</p>
          </div>
          <span className="state-pill">editable</span>
        </div>

        <form className="search-form" onSubmit={onSubmit}>
          <label htmlFor="kb-search">Search</label>
          <div className="search-row">
            <input
              id="kb-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="8k, photo, error code..."
            />
            <button type="submit">Search</button>
          </div>
        </form>

        <div className="write-actions">
          <label htmlFor="kb-user">User</label>
          <input
            id="kb-user"
            value={writer}
            onChange={(event) => setWriter(event.target.value)}
            placeholder="user id"
          />
          <button type="button" onClick={startNewEntry}>
            New
          </button>
          <button type="button" disabled={!selected} onClick={startEditEntry}>
            Edit
          </button>
          <button type="button" onClick={() => void loadReviewQueue()}>
            Review
          </button>
          <button type="button" onClick={() => void loadGraph()}>
            Graph
          </button>
        </div>

        {error && <p className="error">{error}</p>}
        {writeResult && <WriteResultPanel result={writeResult} />}
        {reviewResult && <ReviewResultPanel result={reviewResult} />}
        {loading && <p className="muted">Loading...</p>}

        <div className="result-list" aria-label="Search results">
          {results.map((result) => (
            <button
              className={selected?.id === result.id ? "result active" : "result"}
              key={result.id}
              type="button"
              onClick={() => void openEntry(result.id)}
            >
              <span className="result-title">{result.title}</span>
              <span className="result-meta">
                {result.id} / {result.module} / {result.credibility.claim_type}
              </span>
              <span className="result-snippet">{result.snippet}</span>
            </button>
          ))}
          {hasMoreResults && (
            <button
              className="load-more"
              type="button"
              disabled={loading}
              onClick={() => void loadMoreResults()}
            >
              {loading ? "Loading..." : "Load more"}
            </button>
          )}
          {!loading && results.length === 0 && <p className="muted">No entries found.</p>}
        </div>
      </section>

      <section className="detail-pane" aria-label="Entry detail">
        {editor ? (
          <EntryEditor editor={editor} setEditor={setEditor} onSubmit={submitEditor} />
        ) : showReviewQueue && reviewQueue ? (
          <ReviewPanel
            queue={reviewQueue}
            note={reviewNote}
            setNote={setReviewNote}
            detail={reviewDetail}
            onSelect={(id) => void loadReviewDetail(id)}
            onDecision={(id, decision) => void decideReview(id, decision)}
          />
        ) : showGraph && graph ? (
          <GraphPanel graph={graph} onSelect={(id) => void openEntry(id)} />
        ) : selected ? (
          <EntryDetail entry={selected} />
        ) : (
          <p className="muted">Select an entry.</p>
        )}
      </section>
    </main>
  );
}

function ReviewPanel({
  queue,
  note,
  setNote,
  detail,
  onSelect,
  onDecision
}: {
  queue: ReviewQueue;
  note: string;
  setNote: (value: string) => void;
  detail: ReviewDetail | null;
  onSelect: (id: string) => void;
  onDecision: (id: string, decision: "approve" | "reject") => void;
}) {
  return (
    <section className="review-panel" aria-label="Review queue">
      <div className="detail-header">
        <div>
          <span className="eyebrow">review queue</span>
          <h2>{queue.backlog_count} Pending</h2>
        </div>
        {queue.backlog_warning && <span className="status stale">backlog</span>}
      </div>

      <label className="review-note">
        Note
        <textarea value={note} onChange={(event) => setNote(event.target.value)} />
      </label>

      <div className="review-list">
        {queue.items.map((item) => (
          <article
            className={detail?.entry_id === item.entry_id ? "review-item active" : "review-item"}
            key={item.entry_id}
          >
            <button
              type="button"
              className="review-summary"
              onClick={() => onSelect(item.entry_id)}
            >
              <span className="eyebrow">{item.entry_id}</span>
              <h3>{item.title}</h3>
              <p className="result-meta">
                {item.module} / {item.entry_type} / {item.review_level}
              </p>
              <p className="result-snippet">
                {item.claim_type} / {item.support_strength} / {item.path}
              </p>
            </button>
            <div className="review-actions">
              <button type="button" onClick={() => onDecision(item.entry_id, "approve")}>
                Approve
              </button>
              <button type="button" className="secondary" onClick={() => onDecision(item.entry_id, "reject")}>
                Reject
              </button>
            </div>
          </article>
        ))}
        {queue.items.length === 0 && <p className="muted">No pending entries.</p>}
      </div>

      {detail ? (
        <ReviewDetailPanel detail={detail} />
      ) : (
        queue.items.length > 0 && <p className="muted">Select a pending item to inspect it.</p>
      )}
    </section>
  );
}

function ReviewDetailPanel({ detail }: { detail: ReviewDetail }) {
  const proposal = detail.proposal;
  return (
    <section className="review-detail" aria-label="Review detail">
      <div className="detail-header">
        <div>
          <span className="eyebrow">{detail.entry_id}</span>
          <h2>{proposal.title}</h2>
        </div>
        <span className="status">{detail.operation}</span>
      </div>

      <dl className="facts">
        <div>
          <dt>Review</dt>
          <dd>{detail.review_level}</dd>
        </div>
        <div>
          <dt>State</dt>
          <dd>{proposal.trust_state}</dd>
        </div>
        <div>
          <dt>Module</dt>
          <dd>{proposal.module}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{proposal.entry_type}</dd>
        </div>
      </dl>

      {detail.diff_available && detail.published ? (
        <DiffPanel detail={detail} />
      ) : (
        <section>
          <h3>Diff</h3>
          <p className="muted">Net-new proposal. No published entry to compare.</p>
        </section>
      )}

      <EntryDetail entry={proposal} />
    </section>
  );
}

function DiffPanel({ detail }: { detail: ReviewDetail }) {
  const proposal = detail.proposal;
  const published = detail.published;
  if (!published) {
    return null;
  }
  return (
    <section>
      <h3>Changed Fields</h3>
      {detail.changed_fields.length > 0 ? (
        <TokenList values={detail.changed_fields} />
      ) : (
        <p className="muted">No field differences from the current published entry.</p>
      )}
      <div className="diff-grid">
        <DiffValue label="Title" before={published.title} after={proposal.title} />
        <DiffValue label="Module" before={published.module} after={proposal.module} />
        <DiffValue
          label="Claim"
          before={`${published.credibility.claim_type} / ${published.credibility.support_strength}`}
          after={`${proposal.credibility.claim_type} / ${proposal.credibility.support_strength}`}
        />
        <DiffValue
          label="Tags"
          before={published.tags.join(", ")}
          after={proposal.tags.join(", ")}
        />
      </div>
      {detail.changed_fields.includes("body") && (
        <div className="body-diff">
          <div>
            <h3>Published Body</h3>
            <pre className="entry-body">{published.body}</pre>
          </div>
          <div>
            <h3>Proposal Body</h3>
            <pre className="entry-body">{proposal.body}</pre>
          </div>
        </div>
      )}
    </section>
  );
}

function DiffValue({ label, before, after }: { label: string; before: string; after: string }) {
  const changed = before !== after;
  return (
    <div className={changed ? "diff-value changed" : "diff-value"}>
      <span className="eyebrow">{label}</span>
      <p>
        <strong>Published:</strong> {before || "OPEN"}
      </p>
      <p>
        <strong>Proposal:</strong> {after || "OPEN"}
      </p>
    </div>
  );
}

function GraphPanel({
  graph,
  onSelect
}: {
  graph: GraphResponse;
  onSelect: (id: string) => void;
}) {
  const width = 920;
  const height = 560;
  const svgRef = useRef<SVGSVGElement | null>(null);
  const panRef = useRef<PanGesture | null>(null);
  const nodeDragRef = useRef<NodeDragGesture | null>(null);
  const [hideIsolated, setHideIsolated] = useState(true);
  const [viewport, setViewport] = useState<GraphViewport>({ x: 0, y: 0, scale: 1 });
  const visibleGraph = useMemo(
    () => visibleGraphData(graph, hideIsolated),
    [graph, hideIsolated]
  );
  const { positions, radii, dragNode, releaseNode } = useForceGraphLayout(
    visibleGraph.nodes,
    visibleGraph.edges,
    visibleGraph.degrees,
    width,
    height
  );

  function resetView() {
    setViewport({ x: 0, y: 0, scale: 1 });
  }

  function pointFromEvent(event: Pick<ReactPointerEvent | ReactWheelEvent, "clientX" | "clientY">) {
    return svgPoint(svgRef.current, event.clientX, event.clientY, width, height);
  }

  function graphPointFromEvent(
    event: Pick<ReactPointerEvent | ReactWheelEvent, "clientX" | "clientY">
  ) {
    return viewportToGraphPoint(pointFromEvent(event), viewport);
  }

  function onWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const svgPointValue = pointFromEvent(event);
    const graphPointValue = viewportToGraphPoint(svgPointValue, viewport);
    const factor = event.deltaY > 0 ? 0.88 : 1.12;
    const nextScale = clamp(viewport.scale * factor, 0.25, 2.8);
    setViewport({
      scale: nextScale,
      x: svgPointValue.x - graphPointValue.x * nextScale,
      y: svgPointValue.y - graphPointValue.y * nextScale
    });
  }

  function onCanvasPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    const target = event.target;
    if (target instanceof Element && target.closest(".graph-node")) {
      return;
    }
    setPointerCaptureIfAvailable(event.currentTarget, event.pointerId);
    panRef.current = {
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startViewport: viewport
    };
  }

  function onCanvasPointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    const pan = panRef.current;
    if (!pan || pan.pointerId !== event.pointerId) {
      return;
    }
    const rect = svgRef.current?.getBoundingClientRect();
    const scaleX = rect && rect.width > 0 ? width / rect.width : 1;
    const scaleY = rect && rect.height > 0 ? height / rect.height : 1;
    setViewport({
      ...pan.startViewport,
      x: pan.startViewport.x + (event.clientX - pan.startClientX) * scaleX,
      y: pan.startViewport.y + (event.clientY - pan.startClientY) * scaleY
    });
  }

  function onCanvasPointerUp(event: ReactPointerEvent<SVGSVGElement>) {
    if (panRef.current?.pointerId === event.pointerId) {
      panRef.current = null;
      releasePointerCaptureIfAvailable(event.currentTarget, event.pointerId);
    }
  }

  function onNodePointerDown(event: ReactPointerEvent<SVGGElement>, nodeId: string) {
    event.preventDefault();
    event.stopPropagation();
    setPointerCaptureIfAvailable(event.currentTarget, event.pointerId);
    const point = graphPointFromEvent(event);
    nodeDragRef.current = {
      nodeId,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      moved: false
    };
    dragNode(nodeId, point);
  }

  function onNodePointerMove(event: ReactPointerEvent<SVGGElement>) {
    const drag = nodeDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    const movedDistance = Math.hypot(
      event.clientX - drag.startClientX,
      event.clientY - drag.startClientY
    );
    if (movedDistance > 4) {
      drag.moved = true;
    }
    dragNode(drag.nodeId, graphPointFromEvent(event));
  }

  function onNodePointerUp(event: ReactPointerEvent<SVGGElement>, nodeId: string) {
    const drag = nodeDragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) {
      return;
    }
    releasePointerCaptureIfAvailable(event.currentTarget, event.pointerId);
    nodeDragRef.current = null;
    releaseNode(nodeId);
    if (!drag.moved) {
      onSelect(nodeId);
    }
  }

  return (
    <section className="graph-panel" aria-label="Knowledge graph">
      <div className="detail-header">
        <div>
          <span className="eyebrow">knowledge graph</span>
          <h2>{visibleGraph.nodes.length} Nodes</h2>
        </div>
        <div className="graph-actions">
          <label>
            <input
              checked={hideIsolated}
              onChange={(event) => setHideIsolated(event.target.checked)}
              type="checkbox"
            />
            Hide isolated
          </label>
          <button type="button" onClick={resetView}>
            Reset view
          </button>
          <span className="status">{visibleGraph.edges.length} edges</span>
        </div>
      </div>

      {visibleGraph.nodes.length === 0 ? (
        <p className="muted">
          {graph.nodes.length === 0
            ? "No published graph nodes."
            : "No connected nodes. Turn off Hide isolated to show standalone entries."}
        </p>
      ) : (
        <svg
          className="graph-canvas"
          onPointerDown={onCanvasPointerDown}
          onPointerLeave={onCanvasPointerUp}
          onPointerMove={onCanvasPointerMove}
          onPointerUp={onCanvasPointerUp}
          onWheel={onWheel}
          ref={svgRef}
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          <title>Published KB related graph</title>
          <g transform={`translate(${viewport.x}, ${viewport.y}) scale(${viewport.scale})`}>
            {visibleGraph.edges.map((edge) => {
              const source = positions[edge.source];
              const target = positions[edge.target];
              if (!source || !target) {
                return null;
              }
              const midX = (source.x + target.x) / 2;
              const midY = (source.y + target.y) / 2;
              return (
                <g className="graph-edge" key={`${edge.source}-${edge.target}`}>
                  <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
                  <text x={midX} y={midY - 8}>
                    {edge.bidirectional ? "<-> " : ""}
                    {edge.types.join(", ")}
                  </text>
                </g>
              );
            })}
            {visibleGraph.nodes.map((node) => {
              const position = positions[node.id] ?? { x: width / 2, y: height / 2 };
              const radius = radii[node.id] ?? 30;
              return (
                <g
                  aria-label={`Open ${node.id}`}
                  className="graph-node"
                  key={node.id}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(node.id);
                    }
                  }}
                  onPointerDown={(event) => onNodePointerDown(event, node.id)}
                  onPointerMove={onNodePointerMove}
                  onPointerUp={(event) => onNodePointerUp(event, node.id)}
                  role="button"
                  tabIndex={0}
                  transform={`translate(${position.x}, ${position.y})`}
                >
                  <circle r={radius} />
                  <text className="node-id" y="-4">
                    {node.id.replace("KB-", "")}
                  </text>
                  <text className="node-title" y="14">
                    {truncate(node.title, Math.max(12, Math.floor(radius / 2)))}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      )}
    </section>
  );
}

function EntryEditor({
  editor,
  setEditor,
  onSubmit
}: {
  editor: EditorState;
  setEditor: (next: EditorState | null) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <form className="entry-editor" onSubmit={onSubmit}>
      <div className="detail-header">
        <div>
          <span className="eyebrow">{editor.mode === "new" ? "new proposal" : "edit proposal"}</span>
          <h2>{editor.mode === "new" ? "New Entry" : "Edit Entry"}</h2>
        </div>
        <button type="button" onClick={() => setEditor(null)}>
          Cancel
        </button>
      </div>

      <div className="editor-grid">
        <label>
          Title
          <input
            value={editor.title}
            onChange={(event) => setEditor({ ...editor, title: event.target.value })}
            required
          />
        </label>
        <label>
          Module
          <input
            value={editor.module}
            onChange={(event) => setEditor({ ...editor, module: event.target.value })}
            required
          />
        </label>
        <label>
          Type
          <select
            value={editor.entryType}
            onChange={(event) => setEditor({ ...editor, entryType: event.target.value })}
          >
            <option value="defect_case">defect_case</option>
            <option value="triage_rule">triage_rule</option>
            <option value="code_flow">code_flow</option>
            <option value="log_baseline">log_baseline</option>
          </select>
        </label>
        <label>
          Tags
          <input
            value={editor.tags}
            onChange={(event) => setEditor({ ...editor, tags: event.target.value })}
          />
        </label>
      </div>

      <label className="editor-block">
        Related
        <textarea
          value={editor.related}
          onChange={(event) => setEditor({ ...editor, related: event.target.value })}
          placeholder="KB-2026-0002 related optional-note"
        />
      </label>

      <label className="editor-block">
        Evidence
        <textarea
          value={editor.evidence}
          onChange={(event) => setEditor({ ...editor, evidence: event.target.value })}
          required
        />
      </label>

      <label className="editor-block">
        Body
        <textarea
          className="body-input"
          value={editor.body}
          onChange={(event) => setEditor({ ...editor, body: event.target.value })}
          required
        />
      </label>

      <button type="submit">Submit</button>
    </form>
  );
}

function WriteResultPanel({ result }: { result: WriteResult }) {
  return (
    <div className={result.ok ? "write-result" : "write-result error-box"}>
      <strong>{result.ok ? `Submitted: ${result.status}` : result.error?.message}</strong>
      {result.review_level && <span>Review: {result.review_level}</span>}
      {result.proposed_id && <span>ID: {result.proposed_id}</span>}
      {result.validation_warnings.length > 0 && (
        <ul>
          {result.validation_warnings.map((issue, index) => (
            <li key={index}>{issue.message}</li>
          ))}
        </ul>
      )}
      {result.validation_errors.length > 0 && (
        <ul>
          {result.validation_errors.map((issue, index) => (
            <li key={index}>{issue.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewResultPanel({ result }: { result: ReviewResult }) {
  return (
    <div className={result.ok ? "write-result" : "write-result error-box"}>
      <strong>
        {result.ok
          ? `${result.decision}: ${result.status ?? "done"}`
          : result.error?.message}
      </strong>
      {result.review_level && <span>Review: {result.review_level}</span>}
      {result.id && <span>ID: {result.id}</span>}
      {result.validation_warnings.length > 0 && (
        <ul>
          {result.validation_warnings.map((issue, index) => (
            <li key={index}>{issue.message}</li>
          ))}
        </ul>
      )}
      {result.validation_errors.length > 0 && (
        <ul>
          {result.validation_errors.map((issue, index) => (
            <li key={index}>{issue.message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EntryDetail({ entry }: { entry: Entry }) {
  const stale = Boolean(entry.code_binding?.stale);
  return (
    <article>
      <div className="detail-header">
        <div>
          <span className="eyebrow">{entry.id}</span>
          <h2>{entry.title}</h2>
        </div>
        <span className={stale ? "status stale" : "status"}>{stale ? "stale" : "current"}</span>
      </div>

      <dl className="facts">
        <div>
          <dt>Module</dt>
          <dd>{entry.module}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{entry.entry_type}</dd>
        </div>
        <div>
          <dt>Trust</dt>
          <dd>{entry.trust_state}</dd>
        </div>
        <div>
          <dt>Claim</dt>
          <dd>
            {entry.credibility.claim_type} / {entry.credibility.support_strength}
          </dd>
        </div>
      </dl>

      <section>
        <h3>Signals</h3>
        <TokenList values={[...entry.tags, ...entry.symptom_keywords, ...entry.error_codes]} />
      </section>

      <section>
        <h3>Evidence</h3>
        {entry.credibility.evidence.length > 0 ? (
          <ul className="evidence-list">
            {entry.credibility.evidence.map((item, index) => (
              <li key={index}>{evidenceSummary(item)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No evidence attached.</p>
        )}
      </section>

      <section>
        <h3>Related</h3>
        {entry.related.length > 0 ? (
          <ul className="evidence-list">
            {entry.related.map((item, index) => (
              <li key={index}>{relatedSummary(item)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No related entries.</p>
        )}
      </section>

      <section>
        <h3>Source Refs</h3>
        {entry.source_refs.length > 0 ? (
          <ul className="evidence-list">
            {entry.source_refs.map((item, index) => (
              <li key={index}>{sourceRefSummary(item)}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No source refs.</p>
        )}
      </section>

      <section>
        <h3>Metadata</h3>
        <dl className="facts compact">
          <div>
            <dt>Created</dt>
            <dd>{entry.created}</dd>
          </div>
          <div>
            <dt>Updated</dt>
            <dd>{entry.updated}</dd>
          </div>
          <div>
            <dt>Author</dt>
            <dd>{entry.author ?? "OPEN"}</dd>
          </div>
          <div>
            <dt>Reviewer</dt>
            <dd>{entry.reviewer ?? "OPEN"}</dd>
          </div>
        </dl>
      </section>

      {stale && entry.code_binding?.stale_reason && (
        <section>
          <h3>Stale Reason</h3>
          <p>{entry.code_binding.stale_reason}</p>
        </section>
      )}

      <section>
        <h3>Body</h3>
        <pre className="entry-body">{entry.body}</pre>
      </section>
    </article>
  );
}

function TokenList({ values }: { values: string[] }) {
  const unique = [...new Set(values)].filter(Boolean);
  if (unique.length === 0) {
    return <p className="muted">No signals.</p>;
  }
  return (
    <div className="tokens">
      {unique.map((value) => (
        <span key={value}>{value}</span>
      ))}
    </div>
  );
}

function createPayload(editor: EditorState): EntryWritePayload {
  return {
    ...sharedEditorPayload(editor),
    entry_type: editor.entryType
  };
}

function updatePayload(editor: EditorState): Partial<EntryWritePayload> {
  return sharedEditorPayload(editor);
}

function sharedEditorPayload(editor: EditorState): Omit<EntryWritePayload, "entry_type"> {
  return {
    title: editor.title,
    module: editor.module,
    body: editor.body,
    tags: editor.tags
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    related: parseRelated(editor.related),
    credibility: {
      claim_type: "observation",
      support_strength: "strong",
      evidence: [{ type: "human_note", excerpt: editor.evidence }]
    }
  };
}

function parseRelated(value: string) {
  return value
    .replace(/,/g, "\n")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [target, type = "related", ...noteParts] = line.split(/\s+/);
      return {
        target,
        type,
        origin: "human",
        note: noteParts.join(" ") || undefined
      };
    });
}

function relatedText(entry: Entry) {
  return entry.related
    .map((item) =>
      [item.target, item.type ?? "related", item.note ?? ""]
        .map((part) => String(part).trim())
        .filter(Boolean)
        .join(" ")
    )
    .join("\n");
}

function evidenceText(entry: Entry) {
  const evidence = entry.credibility.evidence[0];
  if (!evidence) {
    return "";
  }
  return String(evidence.excerpt ?? evidence.ref ?? evidence.uri ?? evidence.filepath ?? "");
}

function relatedSummary(item: { target?: string | null; type?: string | null; note?: string | null }) {
  const type = item.type ?? "related";
  const note = item.note ? ` / ${item.note}` : "";
  return `${type}: ${item.target ?? "unknown"}${note}`;
}

function evidenceSummary(item: Record<string, unknown>) {
  const type = String(item.type ?? "evidence");
  const target = item.filepath ?? item.uri ?? item.ref ?? item.attachment_id ?? item.excerpt;
  return target ? `${type}: ${String(target)}` : type;
}

function sourceRefSummary(item: Record<string, unknown>) {
  const type = String(item.type ?? "source");
  const role = item.role ? ` / ${String(item.role)}` : "";
  const target = item.text ?? item.attachment_id ?? item.content_hash ?? item.ref ?? item.uri;
  return target ? `${type}${role}: ${String(target)}` : `${type}${role}`;
}

type GraphPoint = {
  x: number;
  y: number;
};

type GraphViewport = GraphPoint & {
  scale: number;
};

type ForceGraphNode = GraphResponse["nodes"][number] & {
  degree: number;
  radius: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
};

type ForceGraphLink = {
  source: string | ForceGraphNode;
  target: string | ForceGraphNode;
};

type PanGesture = {
  pointerId: number;
  startClientX: number;
  startClientY: number;
  startViewport: GraphViewport;
};

type NodeDragGesture = {
  nodeId: string;
  pointerId: number;
  startClientX: number;
  startClientY: number;
  moved: boolean;
};

function visibleGraphData(graph: GraphResponse, hideIsolated: boolean) {
  const degreeEntries = graph.nodes.map((node) => [node.id, 0] as const);
  const degrees = new Map<string, number>(degreeEntries);
  for (const edge of graph.edges) {
    degrees.set(edge.source, (degrees.get(edge.source) ?? 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) ?? 0) + 1);
  }
  const nodes = hideIsolated
    ? graph.nodes.filter((node) => (degrees.get(node.id) ?? 0) > 0)
    : graph.nodes;
  const visibleIds = new Set(nodes.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) => visibleIds.has(edge.source) && visibleIds.has(edge.target)
  );
  return { nodes, edges, degrees };
}

function useForceGraphLayout(
  nodes: GraphResponse["nodes"],
  edges: GraphResponse["edges"],
  degrees: Map<string, number>,
  width: number,
  height: number
) {
  const nodeMapRef = useRef<Map<string, ForceGraphNode>>(new Map());
  const simulationRef = useRef<Simulation<ForceGraphNode, ForceGraphLink> | null>(null);
  const frameRef = useRef<number | null>(null);
  const [layout, setLayout] = useState(() => forceLayoutSnapshot(nodes, degrees, width, height));

  useEffect(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    simulationRef.current?.stop();

    const forceNodes = nodes.map((node, index) => {
      const position = initialGraphPosition(index, nodes.length, width, height);
      const degree = degrees.get(node.id) ?? 0;
      return {
        ...node,
        degree,
        radius: graphNodeRadius(degree),
        x: position.x,
        y: position.y
      };
    });
    const forceLinks: ForceGraphLink[] = edges.map((edge) => ({
      source: edge.source,
      target: edge.target
    }));
    nodeMapRef.current = new Map(forceNodes.map((node) => [node.id, node]));
    setLayout(snapshotFromForceNodes(forceNodes));

    if (forceNodes.length === 0) {
      simulationRef.current = null;
      return;
    }

    const simulation = forceSimulation<ForceGraphNode>(forceNodes)
      .force(
        "link",
        forceLink<ForceGraphNode, ForceGraphLink>(forceLinks)
          .id((node) => node.id)
          .distance(155)
          .strength(0.48)
      )
      .force("charge", forceManyBody<ForceGraphNode>().strength((node) => -380 - node.degree * 70))
      .force(
        "collide",
        forceCollide<ForceGraphNode>()
          .radius((node) => node.radius + 12)
          .strength(1)
          .iterations(2)
      )
      .force("center", forceCenter<ForceGraphNode>(width / 2, height / 2).strength(0.12))
      .alpha(0.95)
      .alphaDecay(0.035)
      .velocityDecay(0.42)
      .on("tick", () => {
        if (frameRef.current !== null) {
          return;
        }
        frameRef.current = requestAnimationFrame(() => {
          frameRef.current = null;
          setLayout(snapshotFromForceNodes(forceNodes));
        });
      });
    simulationRef.current = simulation;

    return () => {
      simulation.stop();
      if (frameRef.current !== null) {
        cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      }
    };
  }, [nodes, edges, degrees, width, height]);

  function dragNode(id: string, point: GraphPoint) {
    const node = nodeMapRef.current.get(id);
    if (!node) {
      return;
    }
    node.x = point.x;
    node.y = point.y;
    node.fx = point.x;
    node.fy = point.y;
    simulationRef.current?.alphaTarget(0.25).restart();
    setLayout(snapshotFromForceNodes([...nodeMapRef.current.values()]));
  }

  function releaseNode(id: string) {
    const node = nodeMapRef.current.get(id);
    if (!node) {
      return;
    }
    node.fx = null;
    node.fy = null;
    simulationRef.current?.alphaTarget(0);
  }

  return {
    positions: layout.positions,
    radii: layout.radii,
    dragNode,
    releaseNode
  };
}

function forceLayoutSnapshot(
  nodes: GraphResponse["nodes"],
  degrees: Map<string, number>,
  width: number,
  height: number
) {
  const forceNodes = nodes.map((node, index) => {
    const position = initialGraphPosition(index, nodes.length, width, height);
    const degree = degrees.get(node.id) ?? 0;
    return {
      ...node,
      degree,
      radius: graphNodeRadius(degree),
      x: position.x,
      y: position.y
    };
  });
  return snapshotFromForceNodes(forceNodes);
}

function snapshotFromForceNodes(nodes: ForceGraphNode[]) {
  const positions: Record<string, GraphPoint> = {};
  const radii: Record<string, number> = {};
  for (const node of nodes) {
    positions[node.id] = {
      x: node.x ?? 0,
      y: node.y ?? 0
    };
    radii[node.id] = node.radius;
  }
  return { positions, radii };
}

function initialGraphPosition(index: number, count: number, width: number, height: number) {
  const centerX = width / 2;
  const centerY = height / 2;
  if (count <= 1) {
    return { x: centerX, y: centerY };
  }
  const radius = Math.min(width, height) * 0.26;
  const angle = (2 * Math.PI * index) / count - Math.PI / 2;
  return {
    x: centerX + radius * Math.cos(angle),
    y: centerY + radius * Math.sin(angle)
  };
}

function graphNodeRadius(degree: number) {
  return clamp(26 + degree * 4, 26, 52);
}

function svgPoint(
  svg: SVGSVGElement | null,
  clientX: number,
  clientY: number,
  width: number,
  height: number
): GraphPoint {
  const rect = svg?.getBoundingClientRect();
  if (!rect || rect.width === 0 || rect.height === 0) {
    return { x: width / 2, y: height / 2 };
  }
  return {
    x: ((clientX - rect.left) / rect.width) * width,
    y: ((clientY - rect.top) / rect.height) * height
  };
}

function viewportToGraphPoint(point: GraphPoint, viewport: GraphViewport): GraphPoint {
  return {
    x: (point.x - viewport.x) / viewport.scale,
    y: (point.y - viewport.y) / viewport.scale
  };
}

function setPointerCaptureIfAvailable(element: Element, pointerId: number) {
  const target = element as Element & { setPointerCapture?: (pointerId: number) => void };
  target.setPointerCapture?.(pointerId);
}

function releasePointerCaptureIfAvailable(element: Element, pointerId: number) {
  const target = element as Element & { releasePointerCapture?: (pointerId: number) => void };
  target.releasePointerCapture?.(pointerId);
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function truncate(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function errorMessage(exc: unknown) {
  return exc instanceof Error ? exc.message : "Unexpected error";
}

export default App;
