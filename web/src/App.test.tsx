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
  body: "## symptom\n8k photo path fails.",
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
  related: [{ target: "KB-2026-0002", type: "related", origin: "human", note: "seed pair" }],
  created: "2026-06-17T00:00:00Z",
  updated: "2026-06-17T00:00:00Z",
  author_type: "human"
};

const graph = {
  nodes: [
    {
      id: "KB-2026-0001",
      title: "8k photo defect",
      entry_type: "defect_case",
      module: "photo",
      trust_state: "published",
      claim_type: "observation",
      support_strength: "moderate",
      stale: false,
      tags: ["photo"],
      updated: "2026-06-17T00:00:00Z"
    },
    {
      id: "KB-2026-0002",
      title: "Related decoder note",
      entry_type: "defect_case",
      module: "decoder",
      trust_state: "published",
      claim_type: "observation",
      support_strength: "strong",
      stale: false,
      tags: ["decoder"],
      updated: "2026-06-17T00:00:00Z"
    }
  ],
  edges: [
    {
      source: "KB-2026-0001",
      target: "KB-2026-0002",
      types: ["related"],
      origins: ["human"],
      notes: [],
      bidirectional: true
    }
  ]
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
    expect(screen.getByText("KB-2026-0001 / photo / observation")).toBeInTheDocument();
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

  it("submits a new entry proposal without governance fields", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("User"), "alice");
    await user.click(screen.getByRole("button", { name: "New" }));
    await user.type(screen.getByLabelText("Title"), "New decoder note");
    await user.type(screen.getByLabelText("Module"), "decoder");
    await user.type(screen.getByLabelText("Tags"), "decoder, 8k");
    await user.type(screen.getByLabelText("Related"), "KB-2026-0001 related seed-link");
    await user.type(screen.getByLabelText("Evidence"), "Observed by reviewer.");
    await user.type(screen.getByLabelText("Body"), "## symptom\nObserved body.");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      const postCall = fetchMock().mock.calls.find(
        ([url, init]) => url === "/api/entries" && init?.method === "POST"
      );
      expect(postCall).toBeTruthy();
      const init = postCall?.[1] as RequestInit;
      expect(init.headers).toMatchObject({
        "X-KB-User": "alice",
        "X-KB-Write-Intent": "web-edit"
      });
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      expect(body.title).toBe("New decoder note");
      expect(body.tags).toEqual(["decoder", "8k"]);
      expect(body.related).toEqual([
        {
          target: "KB-2026-0001",
          type: "related",
          origin: "human",
          note: "seed-link"
        }
      ]);
      expect(body.id).toBeUndefined();
      expect(body.trust_state).toBeUndefined();
      expect(body.author_type).toBeUndefined();
      expect(body.changed_fields).toBeUndefined();
    });
  });

  it("submits an edit proposal for the selected entry", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("User"), "alice");
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "Updated 8k photo defect");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      const patchCall = fetchMock().mock.calls.find(
        ([url, init]) => url === "/api/entries/KB-2026-0001" && init?.method === "PATCH"
      );
      expect(patchCall).toBeTruthy();
      const init = patchCall?.[1] as RequestInit;
      expect(init.headers).toMatchObject({
        "X-KB-User": "alice",
        "X-KB-Write-Intent": "web-edit"
      });
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      expect(body.title).toBe("Updated 8k photo defect");
      expect(body.entry_type).toBeUndefined();
      expect(body.related).toEqual([
        {
          target: "KB-2026-0002",
          type: "related",
          origin: "human",
          note: "seed pair"
        }
      ]);
      expect(body.id).toBeUndefined();
      expect(body.trust_state).toBeUndefined();
      expect(body.changed_fields).toBeUndefined();
    });
  });

  it("loads the review queue and approves with reviewer identity from the user field", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("User"), "reviewer");
    await user.click(screen.getByRole("button", { name: "Review" }));

    expect(await screen.findByLabelText("Review queue")).toBeInTheDocument();
    expect(screen.getByText("Pending runtime note")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Note"), "Looks good");
    await user.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      const queueCall = fetchMock().mock.calls.find(([url]) => url === "/api/review/queue");
      expect(queueCall?.[1]).toMatchObject({
        headers: { "X-KB-User": "reviewer" }
      });
      const approveCall = fetchMock().mock.calls.find(
        ([url, init]) => url === "/api/review/KB-2026-0002/approve" && init?.method === "POST"
      );
      expect(approveCall).toBeTruthy();
      const init = approveCall?.[1] as RequestInit;
      expect(init.headers).toMatchObject({
        "X-KB-User": "reviewer",
        "X-KB-Write-Intent": "web-edit"
      });
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      expect(body).toEqual({ note: "Looks good" });
      expect(body.reviewer).toBeUndefined();
      expect(body.role).toBeUndefined();
      expect(body.trust_state).toBeUndefined();
    });
  });

  it("rejects a review item through the review API", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("User"), "reviewer");
    await user.click(screen.getByRole("button", { name: "Review" }));
    await user.click(await screen.findByRole("button", { name: "Reject" }));

    await waitFor(() => {
      const rejectCall = fetchMock().mock.calls.find(
        ([url, init]) => url === "/api/review/KB-2026-0002/reject" && init?.method === "POST"
      );
      expect(rejectCall).toBeTruthy();
      expect(rejectCall?.[1]).toMatchObject({
        headers: {
          "X-KB-User": "reviewer",
          "X-KB-Write-Intent": "web-edit"
        }
      });
    });
  });

  it("loads the published graph and opens a node detail", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Graph" }));

    expect(await screen.findByLabelText("Knowledge graph")).toBeInTheDocument();
    expect(screen.getByText("2 Nodes")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/graph");
    await user.click(screen.getByLabelText("Open KB-2026-0001"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith("/api/entries/KB-2026-0001");
    });
  });
});

function mockFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const url = String(input);
  if (url === "/api/review/queue") {
    return ok({
      items: [
        {
          entry_id: "KB-2026-0002",
          title: "Pending runtime note",
          module: "runtime",
          entry_type: "defect_case",
          claim_type: "observation",
          support_strength: "strong",
          review_level: "heavy",
          updated: "2026-06-17T00:00:00Z",
          path: "staging/KB-2026-0002.md"
        }
      ],
      backlog_count: 1,
      backlog_warning: false,
      skipped_files: 0
    });
  }
  if (url === "/api/review/KB-2026-0002/approve" && init?.method === "POST") {
    return ok({
      ok: true,
      decision: "approve",
      id: "KB-2026-0002",
      status: "published",
      review_level: "heavy",
      validation_errors: [],
      validation_warnings: []
    });
  }
  if (url === "/api/review/KB-2026-0002/reject" && init?.method === "POST") {
    return ok({
      ok: true,
      decision: "reject",
      id: "KB-2026-0002",
      status: "deprecated",
      review_level: "heavy",
      validation_errors: [],
      validation_warnings: []
    });
  }
  if (url === "/api/graph") {
    return ok(graph);
  }
  if (url === "/api/entries" && init?.method === "POST") {
    return ok({
      ok: true,
      proposed_id: "KB-2026-0002",
      status: "pending",
      target_dir: "staging",
      review_level: "heavy",
      validation_errors: [],
      validation_warnings: []
    });
  }
  if (url === "/api/entries/KB-2026-0001" && init?.method === "PATCH") {
    return ok({
      ok: true,
      id: "KB-2026-0001",
      status: "pending",
      target_dir: "staging",
      review_level: "heavy",
      validation_errors: [],
      validation_warnings: []
    });
  }
  if (url.startsWith("/api/categories")) {
    return ok({
      modules: ["photo"],
      entry_types: ["defect_case"],
      tags: ["photo"],
      error_codes: ["-1"]
    });
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

function fetchMock() {
  return fetch as unknown as ReturnType<typeof vi.fn>;
}
