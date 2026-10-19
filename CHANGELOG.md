# Changelog

All notable changes to AfriSearch are listed here. The project uses [semantic versioning](https://semver.org/): until 1.0, minor versions may change the API or the index format.

## [Unreleased]

Ready for a pilot: security, limits, backups, legal pages and account controls.

### Added
- Per-user rate limits for questions and uploads, and a storage quota per workspace (`AFRISEARCH_*` settings).
- Upload checks by content; uploads stop being read at 15 MB; at most 20 files per request (the web app sends batches).
- Security headers: Content-Security-Policy, nosniff, no framing.
- Backups: `python -m backend.backup create|restore`, consistent while the app runs, with retention.
- Health check reports database and disk problems with 503, for uptime monitors.
- Optional Sentry error reporting for the API and the web app, without personal data.
- Privacy notice and terms pages, consent at sign-up, links in the footer and Settings.
- Download my data (zip) and delete my account in Settings; with `SUPABASE_SERVICE_ROLE_KEY`, the sign-in account is deleted too.
- "No passages" and "not covered" messages in Amharic and Swahili when the question is.
- Deployment guide (`docs/deploy.md`), Caddyfile and production compose file.

### Fixed
- Ratings could be attached to another member's message in a shared workspace.
- Two simultaneous first requests could create two default workspaces.

## [0.2.0] — 2026-10-19

Towards a hosted product: accounts, workspaces and a new web app.

### Added
- **Web app** (React, TypeScript, Tailwind) replacing the Streamlit UI: landing page, sign-in, chat-style Ask with saved conversations, Library with drag-and-drop upload and live indexing progress, Insights, Settings, light/dark mode, phone layout.
- **Accounts** with Supabase Auth (`AFRISEARCH_AUTH=supabase`): sign-up, sign-in, Google, password reset. Local mode (`none`) keeps working without accounts.
- **Workspaces**: separate documents, index, chats, feedback and insights per workspace; owners add members by email.
- **Saved chats** with follow-up questions that use the earlier conversation.
- **Background indexing** (`POST /api/documents/index?wait=false`, `GET /api/jobs/{id}`) with file and page progress.
- **"Not covered" answers**: when even the best passage scores low with the reranker, the model isn't asked and the closest passages are shown (`AFRISEARCH_MIN_RERANK_SCORE`).
- Answers in the question's language; explicit instruction for Amharic.
- Passages far below the best reranked one are no longer given to the model (`AFRISEARCH_RERANK_GAP`), which stopped small models mixing up facts.
- Local models on CPU load straight into memory instead of spilling to disk when RAM is short (answers took minutes).
- Open the original document at the cited page (`GET /api/documents/{id}/file`).
- Insights endpoint: questions per day, most-cited documents, ratings.

### Changed
- **All API endpoints moved under `/api`**; the API serves the built web app at `/`.
- Backend split into modules (`config`, `auth`, `db`, `store`, `jobs`, `extract`, `models`, `answers`, `text`); data now lives in `data/afrisearch.db` and `data/workspaces/<id>/`.
- Documents and ratings from 0.1 move into the local user's first workspace on first start.
- Docker: one service on port 8000 with a two-stage build (web app + API); `.env.example` added.

### Removed
- The Streamlit UI (`frontend/`, `.streamlit/`) and the `streamlit` and `requests` dependencies.

## [0.1.0] — 2026-10-19

First public release.

### Documents
- Upload PDF, TXT and images of pages (PNG, JPG, TIFF, WebP, BMP); exact duplicates are rejected.
- OCR for scanned PDFs and photos with Tesseract (English, Amharic and Swahili by default), page by page, so mixed PDFs work.
- Sentence-aware chunks that can span pages; Amharic sentences end at `።`, `፧` or `፡፡`.
- Incremental indexing, deletion, and automatic re-indexing prompts when the search model changes.

### Search and answers
- Multilingual search with `intfloat/multilingual-e5-small` (94 languages, cross-language matching).
- Multilingual reranker (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`), on by default and switchable per question.
- Relevance cutoff tuned per search model.
- Answers from Claude, ChatGPT, Gemini or local models (Qwen, Gemma, gpt-oss, Qwen 2.5 0.5B on CPU), with `[S1]` citations; invalid citations are removed.
- Streaming answers for local models (`POST /ask/stream`).
- Search limited to chosen documents (`source_ids`), and a passages-only mode.

### Interface
- Streamlit UI with light and dark themes and a phone-friendly layout.
- Ask tab: settings panel, document scope, streamed answers, citations that jump to their source, ratings, Markdown export of an answer or the whole session.
- Library tab: document table (type, pages, passages, OCR, size, date), passage viewer, delete with confirmation.
- Insights tab: library, session and feedback statistics.

### Quality and release
- Evaluation set of 45 questions in six languages, with a scoring script for search and answer models.
- 93 automated tests; GitHub Actions runs them on every push.
- Docker image with Tesseract included, and `docker compose up` for the API and UI.
- MIT license, contributor guide, security policy and roadmap.
