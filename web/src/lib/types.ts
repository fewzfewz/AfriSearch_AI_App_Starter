// Shapes of the AfriSearch API responses (see backend/main.py).

export interface AppConfig {
  version: string;
  auth: "none" | "supabase";
  supabase_url: string | null;
  supabase_anon_key: string | null;
  auth_providers: string[];
  max_upload_mb: number;
  max_files_per_upload: number;
  file_types: string[];
  sentry_dsn: string | null;
  environment: string;
  org_name: string | null;
  contact_email: string | null;
  workspace_quota_mb: number | null;
}

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Workspace {
  id: string;
  name: string;
  role: "owner" | "member";
  created_at: string;
  member_count?: number;
}

export interface Member {
  id: string;
  email: string;
  name: string;
  role: "owner" | "member";
  added_at: string;
}

export interface Provider {
  id: string;
  label: string;
  kind: "api" | "local";
  model: string;
  available: boolean;
  reason: string | null;
}

export interface Source {
  label: string;
  source_id: string;
  source_name: string;
  page: number | null;
  page_end: number | null;
  score: number;
  rerank_score: number | null;
  ocr: boolean;
  text: string;
}

export interface DocumentInfo {
  source_id: string;
  source_name: string;
  type: string;
  ocr: boolean;
  passages: number;
  pages: number | null;
  bytes: number | null;
  uploaded_at: string | null;
}

export interface OcrStatus {
  available: boolean;
  languages: string[];
  reason: string | null;
}

export interface DocumentsResponse {
  documents: DocumentInfo[];
  indexed_chunks: number;
  stale_documents: number;
  unindexed_files: number;
  storage: { used_bytes: number; quota_bytes: number | null };
  embedder: string;
  reranker: string | null;
  ocr: OcrStatus;
}

export interface Passage {
  chunk_id: string;
  source_name: string;
  page: number | null;
  page_end: number | null;
  ocr: boolean;
  text: string;
}

export interface FailedFile {
  source_id: string;
  filename: string;
  error: string;
}

export interface IndexResult {
  indexed_chunks: number;
  new_chunks: number;
  new_documents: string[];
  failed: FailedFile[];
}

export interface JobProgress {
  stage?: "reading" | "embedding" | "done";
  file?: string;
  file_number?: number;
  file_count?: number;
  page?: number | null;
  page_count?: number | null;
  passages?: number;
}

export interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  progress: JobProgress;
  result: IndexResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  saved: { filename: string; stored_name: string; bytes: number }[];
  errors: { filename: string; error: string }[];
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  questions: number;
}

export interface MessageData {
  provider?: string | null;
  model?: string | null;
  reranked?: boolean;
  covered?: boolean;
  sources?: Source[];
  removed_citations?: string[];
  error?: string | null;
  seconds?: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  data: MessageData;
  rating: "up" | "down" | null;
  created_at: string;
}

export interface ChatDetail extends ChatSummary {
  messages: Message[];
}

export type StreamEvent =
  | ({ type: "sources"; question: string; chat_id: string | null } & Required<
      Pick<MessageData, "provider" | "model" | "reranked" | "covered" | "sources">
    >)
  | { type: "token"; text: string }
  | { type: "done"; answer: string | null; removed_citations: string[]; message_id: string | null }
  | { type: "error"; detail: string };

export interface FeedbackRecord {
  rating: "up" | "down";
  question: string;
  answer: string | null;
  provider: string | null;
  comment: string;
  sources: string[];
  time: string;
  email: string | null;
}

export interface FeedbackSummary {
  total: number;
  up: number;
  down: number;
  recent: FeedbackRecord[];
}

export interface Insights {
  documents: number;
  passages: number;
  ocr_documents: number;
  bytes: number;
  questions: number;
  chats: number;
  people: number;
  not_covered: number;
  average_seconds: number | null;
  per_day: { day: string; questions: number }[];
  top_documents: { source_name: string; answers: number }[];
  feedback: FeedbackSummary;
}
