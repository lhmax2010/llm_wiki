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
  related: RelatedEdge[];
  created: string;
  updated: string;
};

export type RelatedEdge = {
  target: string;
  type?: string | null;
  origin?: string | null;
  note?: string | null;
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

export type ReviewQueueItem = {
  entry_id: string;
  title: string;
  module: string;
  entry_type: string;
  claim_type: string;
  support_strength: string;
  review_level: string;
  updated: string;
  path: string;
};

export type ReviewQueue = {
  items: ReviewQueueItem[];
  backlog_count: number;
  backlog_warning: boolean;
  skipped_files: number;
};

export type ReviewResult = {
  ok: boolean;
  decision: "approve" | "reject";
  id?: string;
  status?: string;
  review_level?: string;
  error?: WriteIssue;
  warning?: WriteIssue;
  validation_errors: WriteIssue[];
  validation_warnings: WriteIssue[];
};

export type GraphNode = {
  id: string;
  title: string;
  entry_type: string;
  module: string;
  trust_state: string;
  claim_type: string;
  support_strength: string;
  stale?: boolean;
  tags: string[];
  updated: string;
};

export type GraphEdge = {
  source: string;
  target: string;
  types: string[];
  origins: string[];
  notes: string[];
  bidirectional: boolean;
};

export type GraphResponse = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type EntryWritePayload = {
  entry_type: string;
  title: string;
  module: string;
  body: string;
  tags: string[];
  related: RelatedEdge[];
  credibility: Credibility;
};
