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

async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { error?: { message?: string } };
      message = payload.error?.message ?? message;
    } catch {
      // Keep the HTTP status message if the server did not return JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export async function searchEntries(query: string): Promise<SearchResult[]> {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  const payload = await readJson<{ entries: SearchResult[] }>(
    await fetch(`/api/entries?${params.toString()}`)
  );
  return payload.entries;
}

export async function getEntry(id: string): Promise<Entry> {
  const payload = await readJson<{ entry: Entry }>(await fetch(`/api/entries/${id}`));
  return payload.entry;
}

export async function listCategories(): Promise<Categories> {
  return readJson<Categories>(await fetch("/api/categories"));
}

export async function getGraph(): Promise<GraphResponse> {
  return readJson<GraphResponse>(await fetch("/api/graph"));
}

export async function proposeEntry(payload: EntryWritePayload, user: string): Promise<WriteResult> {
  return readWriteJson(
    await fetch("/api/entries", {
      method: "POST",
      headers: writeHeaders(user),
      body: JSON.stringify(payload)
    })
  );
}

export async function proposeUpdate(
  id: string,
  payload: Partial<EntryWritePayload>,
  user: string
): Promise<WriteResult> {
  return readWriteJson(
    await fetch(`/api/entries/${id}`, {
      method: "PATCH",
      headers: writeHeaders(user),
      body: JSON.stringify(payload)
    })
  );
}

export async function listReviewQueue(user: string): Promise<ReviewQueue> {
  return readJson<ReviewQueue>(
    await fetch("/api/review/queue", {
      headers: userHeaders(user)
    })
  );
}

export async function approveReviewItem(
  id: string,
  user: string,
  note: string
): Promise<ReviewResult> {
  return readReviewJson(
    await fetch(`/api/review/${id}/approve`, {
      method: "POST",
      headers: writeHeaders(user),
      body: JSON.stringify(reviewBody(note))
    })
  );
}

export async function rejectReviewItem(
  id: string,
  user: string,
  note: string
): Promise<ReviewResult> {
  return readReviewJson(
    await fetch(`/api/review/${id}/reject`, {
      method: "POST",
      headers: writeHeaders(user),
      body: JSON.stringify(reviewBody(note))
    })
  );
}

function userHeaders(user: string): Record<string, string> {
  return {
    "X-KB-User": user
  };
}

function writeHeaders(user: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-KB-User": user,
    "X-KB-Write-Intent": "web-edit"
  };
}

function reviewBody(note: string): Record<string, string> {
  return note.trim() ? { note: note.trim() } : {};
}

async function readWriteJson(response: Response): Promise<WriteResult> {
  const payload = (await response.json()) as WriteResult;
  if (!response.ok && !Array.isArray(payload.validation_errors)) {
    throw new Error(payload.error?.message ?? `${response.status} ${response.statusText}`);
  }
  return payload;
}

async function readReviewJson(response: Response): Promise<ReviewResult> {
  const payload = (await response.json()) as ReviewResult;
  if (!response.ok && !Array.isArray(payload.validation_errors)) {
    throw new Error(payload.error?.message ?? `${response.status} ${response.statusText}`);
  }
  return payload;
}
