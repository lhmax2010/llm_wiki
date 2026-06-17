import { FormEvent, useEffect, useState } from "react";
import { getEntry, listCategories, searchEntries } from "./api";
import type { Categories, Entry, SearchResult } from "./types";
import "./styles.css";

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [selected, setSelected] = useState<Entry | null>(null);
  const [categories, setCategories] = useState<Categories | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const nextResults = await searchEntries(nextQuery);
      setResults(nextResults);
      if (nextResults.length > 0) {
        await selectEntry(nextResults[0].id);
      } else {
        setSelected(null);
      }
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

  return (
    <main className="app-shell">
      <section className="search-pane" aria-label="知识库搜索">
        <div className="toolbar">
          <div>
            <h1>Unified KB</h1>
            <p>{categories ? `${categories.modules.length} modules indexed` : "Loading index"}</p>
          </div>
          <span className="state-pill">readonly</span>
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

        {error && <p className="error">{error}</p>}
        {loading && <p className="muted">Loading...</p>}

        <div className="result-list" aria-label="搜索结果">
          {results.map((result) => (
            <button
              className={selected?.id === result.id ? "result active" : "result"}
              key={result.id}
              type="button"
              onClick={() => void selectEntry(result.id)}
            >
              <span className="result-title">{result.title}</span>
              <span className="result-meta">
                {result.id} · {result.module} · {result.credibility.claim_type}
              </span>
              <span className="result-snippet">{result.snippet}</span>
            </button>
          ))}
          {!loading && results.length === 0 && <p className="muted">No entries found.</p>}
        </div>
      </section>

      <section className="detail-pane" aria-label="条目详情">
        {selected ? <EntryDetail entry={selected} /> : <p className="muted">Select an entry.</p>}
      </section>
    </main>
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

function evidenceSummary(item: Record<string, unknown>) {
  const type = String(item.type ?? "evidence");
  const target = item.filepath ?? item.uri ?? item.ref ?? item.attachment_id ?? item.excerpt;
  return target ? `${type}: ${String(target)}` : type;
}

function errorMessage(exc: unknown) {
  return exc instanceof Error ? exc.message : "Unexpected error";
}

export default App;
