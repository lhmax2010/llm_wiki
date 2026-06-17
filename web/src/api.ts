import type { Categories, Entry, EntryWritePayload, SearchResult, WriteResult } from "./types";

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

function writeHeaders(user: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-KB-User": user,
    "X-KB-Write-Intent": "web-edit"
  };
}

async function readWriteJson(response: Response): Promise<WriteResult> {
  const payload = (await response.json()) as WriteResult;
  if (!response.ok && !Array.isArray(payload.validation_errors)) {
    throw new Error(payload.error?.message ?? `${response.status} ${response.statusText}`);
  }
  return payload;
}
