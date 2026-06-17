import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const entry = {
  id: "KB-2026-0001",
  schema_version: 3,
  title: "8k photo defect",
  entry_type: "defect_case",
  module: "photo",
  snippet: "8k photo path fails",
  matched_section: null,
  credibility: {
    claim_type: "observation",
    support_strength: "moderate",
    evidence: [{ type: "human_note", excerpt: "Observed in local seed." }]
  },
  trust_state: "published",
  stale: false,
  score: 8,
  body: "## 现象\n8k photo path fails.",
  tags: ["photo"],
  symptom_keywords: ["8k"],
  error_codes: ["-1"],
  log_signatures: [],
  aliases: [],
  versions_affected: [],
  hardware: [],
  severity: null,
  section_credibility: {},
  code_binding: null,
  related: [],
  created: "2026-06-17T00:00:00Z",
  updated: "2026-06-17T00:00:00Z",
  author_type: "human"
};

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(mockFetch));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders search results and opens a human-readable detail view", async () => {
    render(<App />);

    expect(await screen.findAllByText("8k photo defect")).toHaveLength(2);
    expect(screen.getByText("KB-2026-0001 · photo · observation")).toBeInTheDocument();
    expect(await screen.findByText("human_note: Observed in local seed.")).toBeInTheDocument();
    expect(screen.getByText("published")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
    expect(screen.queryByText("schema_version")).not.toBeInTheDocument();
    expect(screen.queryByText("author_type")).not.toBeInTheDocument();
  });

  it("submits the query through the HTTP API", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.clear(await screen.findByLabelText("Search"));
    await user.type(screen.getByLabelText("Search"), "8k");
    await user.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith("/api/entries?q=8k");
    });
  });
});

function mockFetch(input: RequestInfo | URL): Promise<Response> {
  const url = String(input);
  if (url.startsWith("/api/categories")) {
    return ok({ modules: ["photo"], entry_types: ["defect_case"], tags: ["photo"], error_codes: ["-1"] });
  }
  if (url.startsWith("/api/entries/KB-2026-0001")) {
    return ok({ entry });
  }
  if (url.startsWith("/api/entries")) {
    return ok({ entries: [entry] });
  }
  return Promise.resolve(new Response("not found", { status: 404 }));
}

function ok(payload: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    })
  );
}
