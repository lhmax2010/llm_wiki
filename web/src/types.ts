export type Credibility = {
  claim_type: string;
  support_strength: string;
  evidence: Array<Record<string, unknown>>;
};

export type SearchResult = {
  id: string;
  title: string;
  entry_type: string;
  module: string;
  snippet: string;
  matched_section?: string | null;
  credibility: Credibility;
  trust_state: string;
  stale?: boolean;
  score?: number;
};

export type Entry = SearchResult & {
  schema_version: number;
  body: string;
  tags: string[];
  symptom_keywords: string[];
  error_codes: string[];
  log_signatures: string[];
  aliases: string[];
  versions_affected: string[];
  hardware: string[];
  severity?: string | null;
  section_credibility: Record<string, Record<string, unknown>>;
  code_binding?: {
    stale?: boolean | null;
    stale_reason?: string | null;
    paths?: string[];
  } | null;
  related: Array<Record<string, unknown>>;
  created: string;
  updated: string;
};

export type Categories = {
  modules: string[];
  entry_types: string[];
  tags: string[];
  error_codes: string[];
};

export type WriteIssue = {
  code: string;
  field: string;
  message: string;
};

export type WriteResult = {
  ok: boolean;
  id?: string;
  proposed_id?: string;
  status?: string;
  target_dir?: string;
  review_level?: string;
  error?: WriteIssue;
  validation_errors: WriteIssue[];
  validation_warnings: WriteIssue[];
};

export type EntryWritePayload = {
  entry_type: string;
  title: string;
  module: string;
  body: string;
  tags: string[];
  credibility: Credibility;
};
