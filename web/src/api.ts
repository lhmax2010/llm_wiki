import type { Categories, Entry, SearchResult } from "./types";

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
