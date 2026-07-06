import { FormEvent, useEffect, useState } from "react";
import {
  approveReviewItem,
  getEntry,
  getGraph,
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
    setEditor(null);
    await selectEntry(id);
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
  onDecision
}: {
  queue: ReviewQueue;
  note: string;
  setNote: (value: string) => void;
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
          <article className="review-item" key={item.entry_id}>
            <div>
              <span className="eyebrow">{item.entry_id}</span>
              <h3>{item.title}</h3>
              <p className="result-meta">
                {item.module} / {item.entry_type} / {item.review_level}
              </p>
              <p className="result-snippet">
                {item.claim_type} / {item.support_strength} / {item.path}
              </p>
            </div>
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
    </section>
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
  const positions = graphPositions(graph.nodes, width, height);
  return (
    <section className="graph-panel" aria-label="Knowledge graph">
      <div className="detail-header">
        <div>
          <span className="eyebrow">knowledge graph</span>
          <h2>{graph.nodes.length} Nodes</h2>
        </div>
        <span className="status">{graph.edges.length} edges</span>
      </div>

      {graph.nodes.length === 0 ? (
        <p className="muted">No published graph nodes.</p>
      ) : (
        <svg className="graph-canvas" viewBox={`0 0 ${width} ${height}`} role="img">
          <title>Published KB related graph</title>
          {graph.edges.map((edge) => {
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
          {graph.nodes.map((node) => {
            const position = positions[node.id];
            return (
              <g
                aria-label={`Open ${node.id}`}
                className="graph-node"
                key={node.id}
                onClick={() => onSelect(node.id)}
                role="button"
                tabIndex={0}
                transform={`translate(${position.x}, ${position.y})`}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(node.id);
                  }
                }}
              >
                <circle r="34" />
                <text className="node-id" y="-4">
                  {node.id.replace("KB-", "")}
                </text>
                <text className="node-title" y="14">
                  {truncate(node.title, 18)}
                </text>
              </g>
            );
          })}
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

function graphPositions(nodes: GraphResponse["nodes"], width: number, height: number) {
  const centerX = width / 2;
  const centerY = height / 2;
  if (nodes.length === 1) {
    return { [nodes[0].id]: { x: centerX, y: centerY } };
  }
  const radius = Math.min(width, height) * 0.34;
  return Object.fromEntries(
    nodes.map((node, index) => {
      const angle = (2 * Math.PI * index) / nodes.length - Math.PI / 2;
      return [
        node.id,
        {
          x: centerX + radius * Math.cos(angle),
          y: centerY + radius * Math.sin(angle)
        }
      ];
    })
  );
}

function truncate(value: string, maxLength: number) {
  return value.length > maxLength ? `${value.slice(0, maxLength - 1)}...` : value;
}

function errorMessage(exc: unknown) {
  return exc instanceof Error ? exc.message : "Unexpected error";
}

export default App;
