# AfriSearch AI — Current Project Status & Architecture Audit

**Date of Audit:** November 9, 2026  
**Audited Version:** v0.2.0 (with uncommitted v0.2.1-dev changes)  
**Target Environment:** Local Development & Single-Node Production Deployment  

---

## 1. Executive Summary

AfriSearch AI is an AI-powered multilingual document search and research application engineered for organisations operating with African languages (specifically Amharic, Swahili, Somali, Hausa, Afaan Oromo) and English.

The project has evolved from an initial single-file Streamlit prototype (v0.1.0) into a production-capable, multi-tenant SaaS foundation (v0.2.0) consisting of:
- A modular **FastAPI** backend in Python 3.11/3.13;
- A modern, responsive **React 18 + TypeScript + Tailwind CSS** single-page application built with **Vite**;
- An embedded vector retrieval pipeline utilizing `intfloat/multilingual-e5-small` and `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` with NumPy and SQLite;
- Pluggable AI generation supporting cloud models (Anthropic Claude, OpenAI ChatGPT, Google Gemini) and local open-weight models (Qwen 2.5/3.8, Gemma 4, GPT-OSS);
- Production tooling including Tesseract OCR (with Ethiopic and Swahili scripts), transactional email, Sentry telemetry, automated backups, and Caddy reverse-proxy SSL configurations.

### Key Verification Findings
- **Backend Tests:** 218 / 218 tests passing in pytest (using Python 3.11 virtual environment `pytorch_env`), including full coverage for Organizations, Subscriptions DB, Entitlement Enforcement, Workspace RBAC, Payment Gateways & Invoicing, and Table-Aware Extraction.
- **Frontend Unit Tests:** 5 / 5 tests passing in Vitest.
- **Frontend Typecheck & Build:** `tsc -b` and `vite build` completed with 0 errors (2,119 modules transformed), outputting optimized bundles to `web/dist/`.
- **Multi-Tenant Foundation (SAAS-P0-01):** Completed and verified across database, authorization, REST APIs, and UI layers. Organizations own workspaces; isolation and containment strictly enforced server-side.
- **Subscriptions & Entitlements (SAAS-P0-02):** Completed and verified. Tiered plans (Free, Pro, Business, Enterprise), server-side quota enforcement on workspaces, seats, storage, documents, and monthly AI queries, with real-time UI usage meters.
- **Workspace RBAC (Owner, Admin, Member, Viewer):** Completed and verified. Hierarchical role validation on all document mutations, tagging, member invitations, role updates, and viewer query-only boundaries with responsive UI controls.
- **Payment Gateways & Invoicing (SAAS-P1-02):** Completed and verified. Dual-provider billing engine for Stripe (global credit cards, checkout sessions, customer portal) and Chapa (Ethiopian rails: Telebirr, CBE Birr in ETB), with HMAC signature verification, idempotent webhook journal (`webhook_events`), and audit-ready invoices ledger (`invoices`).
- **Table-Aware Extraction & Structured Markdown Preservation (TASK-P1-01):** Completed and verified. High-fidelity GitHub-flavored Markdown table extraction for Excel (`.xlsx`), CSV (`.csv`), and Word (`.docx`), table-boundary aware sentence splitting, and cross-chunk table header preservation for tabular RAG accuracy.
- **Core AI Insight:** Evaluation results confirm that while the semantic retrieval pipeline achieves **92.3% Hit@1** and **97.4% Hit@K** (MRR 0.944), the small local model (`Qwen 2.5 0.5B`) achieves only 36% answer accuracy (0% on African-language questions). Consequently, cloud API models (Claude, ChatGPT, Gemini) or larger local models are mandatory for reliable pilot deployments.

---

## 2. Current Architecture & Technology Stack

```
                                    +-----------------------------------------+
                                    |         User Browser / Mobile           |
                                    +-----------------------------------------+
                                                         |
                                                         v
                                    +-----------------------------------------+
                                    |       Reverse Proxy (Caddy / HTTPS)     |
                                    +-----------------------------------------+
                                                         |
                                                         v
+-------------------------------------------------------------------------------------------------------------+
|                                           FastAPI Application                                               |
|                                                                                                             |
|   +-----------------------+     +--------------------------+     +--------------------------------------+   |
|   |   Public / Static     |     |    Auth & Workspaces     |     |          Document Pipeline           |   |
|   | - Serves web/dist/    |     | - Supabase JWKS (ES/RS)  |     | - Content extraction (PDF, DOCX,     |   |
|   | - CSP & Security Hdr  |     | - Local mode (bypass)    |     |   XLSX, PPTX, HTML, TXT, OCR)        |   |
|   | - Health checks (/api)|     | - Tenant isolation       |     | - Sentence chunker (Ethiopic-aware)  |   |
|   +-----------------------+     +--------------------------+     +--------------------------------------+   |
|                                                                                    |                        |
|                                                                                    v                        |
|   +------------------------------------+     +----------------------------------------------------------+   |
|   |         Search & Retrieval         |     |                      AI Generation                       |   |
|   | - SentenceTransformer (e5-small)   |     | - Cloud: Claude Opus 5.5, ChatGPT 6.1, Gemini 4 Argon    |   |
|   | - CrossEncoder (mmarco reranker)   |     | - Local: Qwen 2.5 0.5B, Qwen 3.8, Gemma 4, GPT-OSS 20B   |   |
|   | - Relevance cutoff & gap pruning   |     | - NDJSON Token Streaming & Citation Sanitizer            |   |
|   +------------------------------------+     +----------------------------------------------------------+   |
+-------------------------------------------------------------------------------------------------------------+
               |                                             |                                   |
               v                                             v                                   v
+-------------------------------+             +------------------------------+     +--------------------------+
|  SQLite (afrisearch.db, WAL)  |             | Workspace Storage (data/ws/) |     | Transactional Mailer     |
| - users, workspaces, members  |             | - uploads/ (raw documents)   |     | - Resend API             |
| - invitations, chats, messages|             | - index.json & embeddings.npy|     | - SMTP (STARTTLS)        |
| - feedback, jobs, usage costs |             | - manifest.json & tags.json  |     | - Background worker      |
+-------------------------------+             +------------------------------+     +--------------------------+
```

### Technology Breakdown

| Component | Technology | Version / Specification | Purpose |
|---|---|---|---|
| **Backend Framework** | FastAPI + Starlette | `>=0.115` | Async REST API and static asset hosting |
| **Server** | Uvicorn | `>=0.30` | ASGI application server |
| **Primary Runtime** | Python | 3.11.13 (`pytorch_env`) | Backend runtime and ML execution |
| **Database** | SQLite 3 | WAL mode, Foreign Keys ON | Relational metadata, chats, feedback, usage |
| **Frontend Framework** | React | 18.3.1 | Single-page application UI |
| **Language** | TypeScript | 5.6.3 | Type-safe frontend codebase |
| **Styling** | Tailwind CSS | 3.4.14 | Responsive terracotta theme & dark mode |
| **Icons** | Lucide React | 0.454.0 | Modern icon set |
| **Bundler** | Vite | 5.4.10 | Frontend dev server and production builder |
| **Authentication** | Supabase Auth / JWKS | `@supabase/supabase-js` 2.45 | JWT token verification (ES256/RS256/HS256) |
| **Embeddings** | Sentence-Transformers | `intfloat/multilingual-e5-small` | 384-dim multilingual dense vectors (94 langs) |
| **Reranker** | Cross-Encoder | `mmarco-mMiniLMv2-L12-H384-v1` | Cross-attention query-passage relevance scoring |
| **Document Parsers** | pypdf, python-docx, openpyxl, python-pptx | Modern office formats | Structured text and metadata extraction |
| **OCR Engine** | Tesseract OCR + pypdfium2 | `eng+amh+swa` | Fallback OCR for scanned PDFs and image uploads |
| **Telemetry** | Sentry | `sentry-sdk`, `@sentry/browser` | Exception and performance monitoring |

---

## 3. Repository Structure & Entry Points

```
AfriSearch_AI_App_Starter/
├── backend/                  # FastAPI backend modules
│   ├── answers.py            # Prompt engineering, citations, follow-up suggestions, chat titles
│   ├── auth.py               # Supabase JWT token verification & current_user dependency
│   ├── backup.py             # SQLite backup API snapshot & tar.gz archive management
│   ├── config.py             # Environment variables, directory paths, quota configurations
│   ├── db.py                 # SQLite schema, WAL initialization, migrations, CRUD queries
│   ├── extract.py            # Text extraction: PDF, DOCX, XLSX, PPTX, HTML, TXT, OCR
│   ├── jobs.py               # Background indexing queue & throttled progress tracking
│   ├── limits.py             # Sliding-window rate limiters (uploads, questions)
│   ├── llm.py                # Cloud (Claude, GPT, Gemini) & Local (Transformers) providers
│   ├── mailer.py             # Transactional emails via Resend, SMTP, log or memory
│   ├── main.py               # HTTP routing under /api, middleware, CSP, web app mounting
│   ├── models.py             # Embedder & Reranker lazy loading and prefix configurations
│   ├── recover_workspace.py  # Admin CLI for recovering orphaned workspaces to organizations
│   ├── store.py              # Per-workspace DocumentStore: indexing, vectors, tags, retrieval
│   └── text.py               # Sentence splitting (Ethiopic-aware), chunking, citation sanitizer
├── web/                      # React frontend
│   ├── src/
│   │   ├── components/       # UI building blocks (Composer, Answer, CommandPalette, Modals)
│   │   ├── lib/              # API client, auth context, workspace context, formatting helpers
│   │   ├── pages/            # AppLayout, ChatPage, LibraryPage, InsightsPage, SettingsPage...
│   │   ├── App.tsx           # Route definitions and application shell
│   │   └── main.tsx          # React DOM entry point
│   ├── e2e/                  # Playwright browser tests
│   └── package.json          # Node dependencies and build scripts
├── evaluation/               # Accuracy and retrieval benchmark suite
│   ├── corpus/               # Test documents (agriculture, solar, mobile money, health)
│   ├── questions.json        # 45 benchmark questions in 6 languages
│   ├── run_eval.py           # Evaluation runner for embedders, rerankers, and LLMs
│   ├── scoring.py            # Deterministic fact-checking and refusal scoring
│   └── results/              # Historical benchmark logs
├── deploy/                   # Production deployment assets
│   ├── Caddyfile             # Automated HTTPS configuration with security headers
│   └── docker-compose.prod.yml # Production multi-container composition
├── docs/                     # Operations and deployment guides
├── tests/                    # Backend automated test suite (198 tests)
│   ├── conftest.py           # Pytest fixtures and mock embedder/model implementations
│   └── e2e/server.py         # Mock server for frontend Playwright integration tests
├── Dockerfile                # Multi-stage production container definition
├── docker-compose.yml        # Development container orchestration
└── pytest.ini                # Pytest configuration
```

### Key Entry Points
1. **Local Backend API:** `backend/main.py:app` via `uvicorn backend.main:app --host 127.0.0.1 --port 8000`
2. **Local Frontend Dev Server:** `web/` via `npm run dev` (proxies `/api` to port 8000)
3. **Evaluation Runner:** `evaluation/run_eval.py`
4. **Data Backup / Restore Tool:** `python -m backend.backup create|restore`
5. **E2E Test Mock Server:** `tests/e2e/server.py`

---

## 4. Feature Inventory & Implementation Status

Features are classified into:
- **Implemented:** Code complete, verified by test execution or direct code inspection.
- **Partially implemented:** Functional but lacking planned edge-case handling, scaling, or polish.
- **Broken:** Exists with identifiable runtime or logic defects.
- **Planned only:** Documented in roadmap/TODO but not present in code.
- **Missing:** Critical for product goals but not yet designed.
- **Unnecessary or duplicated:** Dead code or redundant artifacts.

| Feature Area | Feature Description | Status | Evidence / Location |
|---|---|---|---|
| **Document Ingestion** | PDF text extraction with per-page text inspection | Implemented | `backend/extract.py:extract_pdf` |
| **Document Ingestion** | Tesseract OCR for scanned PDF pages & images | Implemented | `backend/extract.py:ocr_pdf_page`, `ocr_image` |
| **Document Ingestion** | Office files: Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`) | Implemented | `backend/extract.py:extract_office` |
| **Document Ingestion** | Plain text, Markdown, CSV, and HTML visible text | Implemented | `backend/extract.py:html_text`, `store.py` |
| **Document Ingestion** | Content inspection (PDF magic bytes, image decode, binary check) | Implemented | `backend/store.py:content_problem`, `test_security.py` |
| **Document Ingestion** | Phone camera document capture | Implemented | `web/src/pages/LibraryPage.tsx:714` (`capture="environment"`) |
| **Document Management** | Multi-tenant workspace separation | Implemented | `backend/store.py:DocumentStore`, `backend/db.py` |
| **Document Management** | Document replacement preserving earlier turn citations | Implemented | `backend/main.py:replace_document`, `test_documents.py` |
| **Document Management** | Single & bulk document deletion | Implemented | `backend/main.py:delete_document`, `web/src/pages/LibraryPage.tsx` |
| **Document Management** | Folders & tags (categorization & filtering) | Implemented *(uncommitted)* | `backend/store.py:set_document_tags`, `LibraryPage.tsx`, `ChatPage.tsx` |
| **Document Management** | Automatic executive summary generation on upload | Planned only | Mentioned in `TODO.md:61`, not in `jobs.py` |
| **Chunking & Indexing** | Sentence-aware chunking with Ethiopic punctuation support | Implemented | `backend/text.py:chunk_document`, `test_text_processing.py` |
| **Chunking & Indexing** | Asynchronous background indexing with page progress | Implemented | `backend/jobs.py:_run`, `test_chats.py:test_background_indexing` |
| **Chunking & Indexing** | Index versioning and stale chunk detection | Implemented | `backend/models.py:INDEX_VERSION`, `backend/store.py` |
| **Chunking & Indexing** | Table and balance-sheet aware chunking | Planned only | Mentioned in `TODO.md:38`, `ROADMAP.md:62` |
| **Search & Retrieval** | Multilingual dense vector embeddings (E5-small) | Implemented | `backend/models.py`, `backend/store.py:retrieve` |
| **Search & Retrieval** | Cross-encoder passage reranking (mMiniLMv2) | Implemented | `backend/models.py:get_reranker`, `backend/store.py` |
| **Search & Retrieval** | Rerank score relevance floor (`MIN_RERANK_SCORE = -5.0`) | Implemented | `backend/models.py:MIN_RERANK_SCORE`, `backend/answers.py:is_covered` |
| **Search & Retrieval** | Relative score focus gap pruning (`RERANK_GAP = 5.0`) | Implemented | `backend/models.py:RERANK_GAP`, `backend/answers.py:focus` |
| **Search & Retrieval** | Document scope restriction (by document ID) | Implemented | `backend/store.py:retrieve(source_ids=...)` |
| **Search & Retrieval** | Tag / collection search scope restriction | Implemented *(uncommitted)* | `backend/store.py:retrieve(tags=...)`, `ChatPage.tsx` |
| **Search & Retrieval** | Multi-lingual benchmark evaluation suite | Implemented | `evaluation/run_eval.py`, `evaluation/scoring.py` |
| **Answer Generation** | Grounded prompt construction with strict citation rules | Implemented | `backend/answers.py:build_prompt` |
| **Answer Generation** | Cloud LLM integration: Anthropic Claude (Opus 5.5, fallbacks) | Implemented | `backend/llm.py:_claude_generate`, `_claude_stream` |
| **Answer Generation** | Cloud LLM integration: OpenAI ChatGPT (GPT 6.1 Sol) | Implemented | `backend/llm.py:_openai_generate`, `_openai_stream` |
| **Answer Generation** | Cloud LLM integration: Google Gemini (Gemini 4 Argon) | Implemented | `backend/llm.py:_gemini_generate`, `_gemini_stream` |
| **Answer Generation** | Local GPU/CPU LLM integration (Qwen, Gemma, GPT-OSS) | Implemented | `backend/llm.py:_local_generator`, `_chat_inputs` |
| **Answer Generation** | Token & cost tracking per workspace | Implemented | `backend/llm.py:cost_usd`, `backend/db.py:record_usage` |
| **Answer Generation** | Real-time NDJSON streaming with refusal discarding | Implemented | `backend/main.py:ask_stream`, `web/src/lib/ndjson.ts` |
| **Answer Generation** | "Passages only" search mode (bypassing LLM generation) | Implemented | `backend/main.py:AskRequest.generate_answer=False`, UI toggle |
| **Citations & Verification**| Citation linking `[S#]` to expandable source cards | Implemented | `web/src/components/answer.tsx:SourceCard`, `format.ts` |
| **Citations & Verification**| Hallucinated citation sanitizer (pruning invalid labels) | Implemented | `backend/text.py:clean_citations`, `test_text_processing.py` |
| **Citations & Verification**| Deep linking to original PDF at cited page (`#page=N`) | Implemented | `web/src/lib/api.ts:openDocument`, `main.py:document_file` |
| **Multilingual UX** | Question language detection (Amharic, Swahili, English) | Implemented | `backend/answers.py:question_language` |
| **Multilingual UX** | Localized "not covered" and "no sources" canned answers | Implemented | `backend/answers.py:CANNED` |
| **Multilingual UX** | Contextual suggested follow-up questions in 3 languages | Implemented | `backend/answers.py:generate_suggestions` |
| **Multilingual UX** | Multilingual chat title auto-generation | Implemented | `backend/answers.py:generate_chat_title` |
| **Multilingual UX** | Full UI localization (Amharic/Swahili interface strings) | Planned only | Mentioned in `TODO.md:101`, UI is currently English only |
| **Chat & History** | Saved conversation threads with message persistence | Implemented | `backend/db.py:create_chat`, `add_message`, `ChatPage.tsx` |
| **Chat & History** | Follow-up context re-querying for short questions | Implemented | `backend/answers.py:search_query`, `main.py:prepare_ask` |
| **Chat & History** | Chat sharing with workspace (read-only) | Implemented | `backend/db.py:set_chat_shared`, `AppLayout.tsx` |
| **Chat & History** | Answer feedback (thumbs up/down with comments) | Implemented | `backend/main.py:add_feedback`, `ChatPage.tsx` |
| **Chat & History** | Markdown conversation export | Implemented | `web/src/pages/ChatPage.tsx:exportMarkdown` |
| **User & Team Admin** | Local single-user mode (zero configuration) | Implemented | `backend/auth.py:LOCAL_USER` |
| **User & Team Admin** | Supabase Auth (Sign-up, Sign-in, Password Reset, Google) | Implemented | `web/src/pages/SignInPage.tsx`, `backend/auth.py` |
| **User & Team Admin** | Workspace member invitations by email (deferred join) | Implemented | `backend/main.py:add_member`, `backend/db.py:invite` |
| **User & Team Admin** | Role-Based Access Control (RBAC: Admin/Editor/Viewer) | Planned only | Mentioned in `TODO.md:53`, currently only owner/member |
| **Privacy & Security** | GDPR/Ethiopia Proclamation/Kenya DPA data export (zip) | Implemented | `backend/main.py:export_my_data`, `SettingsPage.tsx` |
| **Privacy & Security** | Complete account deletion (cascading workspaces & auth) | Implemented | `backend/main.py:delete_my_account`, `SettingsPage.tsx` |
| **Privacy & Security** | In-memory sliding-window rate limiting | Partially implemented | `backend/limits.py` (process-local; resets on restart) |
| **Privacy & Security** | Storage quota enforcement per workspace | Implemented | `backend/store.py:save_uploads`, `backend/config.py` |
| **Privacy & Security** | Content Security Policy with dynamic inline script SHA-256 | Implemented | `backend/main.py:content_security_policy` |
| **Operations** | Database snapshot backups and restore CLI | Implemented | `backend/backup.py:create`, `restore`, `test_backup.py` |
| **Operations** | Transactional emails (Resend & SMTP with STARTTLS) | Implemented | `backend/mailer.py`, `test_email.py` |
| **Operations** | System health probe (`/api/health` with DB & disk checks) | Implemented | `backend/main.py:health` |
| **Operations** | Distributed job queue (Redis + Celery/RQ) | Planned only | Mentioned in `TODO.md:94`, currently single in-memory thread |
| **Dead Code / Artifacts** | `frontend/` directory leftover from v0.1 Streamlit | Unnecessary | `frontend/__pycache__/app.cpython-313.pyc` is abandoned |

---

## 5. Verified Working Functionality

The following functionalities were directly verified through test execution and build commands:

1. **Test Suite Verification (177 backend tests passing):**
   - Command: `/home/fewzan/miniconda3/envs/pytorch_env/bin/pytest -q`
   - Output: `177 passed, 1 warning in 98.64s`
   - Covered suites:
     - `test_accounts.py` (11 tests): Supabase token verification, workspace isolation, data export, account deletion, invitations.
     - `test_ask.py` (12 tests): Retrieval, model refusal, error handling, follow-up suggestions, tag-based ask filtering.
     - `test_backup.py` (4 tests): Backup archive creation, rotation, safe restore, path traversal rejection.
     - `test_chats.py` (26 tests): Chat persistence, follow-ups, ratings, background indexing progress, question language detection.
     - `test_documents.py` (12 tests): Uploads, hash deduplication, indexing, tag CRUD, tag filtering, document replacement.
     - `test_email.py` (8 tests): SMTP, Resend, template formatting, outbox memory driver.
     - `test_evaluation_scoring.py` (14 tests): Scoring logic, citation attribution, refusal detection.
     - `test_formats.py` (11 tests): DOCX, XLSX, PPTX, HTML, Markdown, CSV, and invalid file rejection.
     - `test_library.py` (10 tests): File lists, passage reading, deletion, stale chunk indexing.
     - `test_ocr.py` (8 tests): Tesseract fallback, language priority, missing binary handling.
     - `test_providers.py` (19 tests): Mock API calls for Claude, ChatGPT, Gemini, local model loading logic.
     - `test_reranker.py` (9 tests): Reranking score ordering, cutoff enforcement, candidate window.
     - `test_search_model.py` (5 tests): E5 prefixing, index version mismatching, re-embedding.
     - `test_security.py` (9 tests): Content-based validation, size limits, quotas, rate limits, CSP headers.
     - `test_stream.py` (8 tests): NDJSON stream protocol, refusal mid-stream, network disconnect handling.
     - `test_text_processing.py` (14 tests): Sentence boundaries, Ethiopic characters, chunk overlap, citation cleaning, title generation.
     - `test_usage.py` (5 tests): Token accounting, cost tracking, refusal billing.

2. **Frontend Build & Unit Test Verification:**
   - Typechecking: `npm --prefix web run typecheck` (`tsc -b`) passed with 0 errors.
   - Unit Tests: `npm --prefix web run test` (`vitest run`) passed 5/5 tests in `format.test.ts`.
   - Production Build: `npm --prefix web run build` transformed 2,119 modules and generated `web/dist/` in 10.11s.

3. **Retrieval Benchmark Verification (`evaluation/results/eval-20261020-013050.json`):**
   - Corpus: 8 domain documents (solar systems, grain storage, mobile money, safe water, poultry farming, coffee care, device manuals).
   - Answerable Questions: 39 across 6 languages.
   - Hit@1: 36/39 (92.3%); Hit@K (top 4): 38/39 (97.4%); MRR: 0.944.
   - Language Hit Rates: English (25/25), Amharic (6/6), Swahili (5/5), Somali (1/1), Hausa (1/1), Afaan Oromo (0/1).
   - Off-topic Detection: 2/6 stopped at retrieval stage, 3/6 stopped by `MIN_RERANK_SCORE = -5.0`.

---

## 6. Broken or Incomplete Functionality & Technical Debt

### Identified Issues & Incomplete Areas

1. **Dead Artifact: Abandoned `frontend/` Directory**
   - **Path:** `frontend/__pycache__/app.cpython-313.pyc`
   - **Finding:** The original Streamlit frontend (`frontend/app.py`) was deleted in commit `fa2234d` when the React app was added. Only an obsolete `__pycache__` directory remains in `frontend/`.
   - **Impact:** Misleads developers inspecting directory structure.

2. **In-Memory Rate Limiter Not Scalable Across Processes**
   - **Path:** `backend/limits.py:check`
   - **Finding:** `_events: dict[str, deque[float]]` is held in process memory protected by a thread lock.
   - **Impact:** In production with multiple Uvicorn workers (`--workers 4`) or multi-container instances, each worker maintains its own independent window, effectively multiplying permitted limits. Server restarts wipe all active rate counters.

3. **Single-Worker Indexing Bottleneck**
   - **Path:** `backend/jobs.py:14` (`_executor = ThreadPoolExecutor(max_workers=1)`)
   - **Finding:** A single thread executor processes all workspace indexing jobs sequentially.
   - **Impact:** If Workspace A uploads a 100-page scanned document requiring heavy OCR, Workspace B's small 2-page upload is blocked in queue until Workspace A completes.

4. **NumPy Vector Store Scaling Limit**
   - **Path:** `backend/store.py:load`, `retrieve`
   - **Finding:** Chunks and embeddings are stored in `index.json` and `embeddings.npy` per workspace. Every retrieval performs a full in-memory linear cosine scan (`np.dot`).
   - **Impact:** Works well for small/medium workspaces (up to ~10,000 chunks). Becomes slow and memory-intensive if workspaces scale to hundreds of large PDF manuals or documents.

5. **Local Answer Generation Quality Gap in African Languages**
   - **Path:** `backend/llm.py:LOCAL_SPECS["qwen-small"]`
   - **Finding:** Benchmark records show `Qwen 2.5 0.5B` scored 14/39 overall and 0/14 on African-language questions.
   - **Impact:** If deployed in local mode without cloud API keys, non-English queries will yield incorrect or ungrounded answers.

6. **Chat History Pagination Missing**
   - **Path:** `backend/db.py:list_chats`
   - **Finding:** The endpoint uses an un-paginated query (`LIMIT 100`).
   - **Impact:** Long-term users with >100 conversations cannot access older chats from the sidebar.

7. **Table & Multi-Column Layout Flattening**
   - **Path:** `backend/extract.py:extract_office`, `extract_pdf`
   - **Finding:** Complex tables and multi-column PDFs are flattened into text streams. Cell relationships across rows can be fragmented during sentence splitting.

---

## 7. Test and Build Audit

| Tool | Scope | Status | Notes |
|---|---|---|---|
| **pytest 9.0.3** | Backend test suite | **PASS** (177/177) | Executed in 98.64s under Python 3.11.13 (`pytorch_env`). |
| **vitest 2.1.4** | Frontend unit tests | **PASS** (5/5) | Verified formatters, line splitters, citation linkers. |
| **tsc 5.6.3** | Frontend typecheck | **PASS** (0 errors) | Verified against strict TypeScript configuration. |
| **vite 5.4.10** | Production asset build | **PASS** | Output generated in `web/dist/` (assets gzipped: CSS ~10kB, JS vendor ~112kB). |
| **Playwright 1.48** | E2E Browser Journey | **Configured** | Requires local mock server `tests/e2e/server.py`. |

---

## 8. Security, Reliability & Performance Audit

### Security Posture
- **Authentication:** Supabase Auth verification uses standard JWKS cryptographic signature validation (`PyJWKClient` caching public keys) with expiration checks (`exp`, `sub`).
- **Authorization:** Multi-tenant workspace data boundaries are enforced at the query level (`workspace_id` filter on all SQLite operations and file path isolation under `data/workspaces/<id>/`).
- **Input Validation:** Strict file type validation inspecting file content headers, decompression bomb protection on images, 15 MB upload ceilings, and 20 files per upload batch limit.
- **HTTP Security Headers:** Strict Content-Security-Policy (CSP) that dynamically hashes inline dark-mode scripts, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`.
- **Secret Handling:** Zero API keys or sensitive JWT secrets are committed to the repository; `.env.example` provides documentation templates without default credentials.

### Reliability & Resilience
- **Database Snapshots:** SQLite backup API utilized in `backend/backup.py` guarantees transactionally consistent live backups without locking the active web service.
- **Fail-safe Job Recovery:** Lifespan startup hook (`db.fail_interrupted_jobs()`) marks jobs that were interrupted by a server crash or reboot as `failed` rather than hanging in `running`.
- **Model Refusal Protection:** Mid-stream refusal detection discards partial streamed output if a safety classifier rejects answering halfway through.

---

## 9. Deployment Readiness & Blockers

### Readiness Status: **Near Pilot-Ready (Requires Configuration)**

### Production Blockers (P0)
1. **VM & Domain Provisioning:** The production Docker Compose (`deploy/docker-compose.prod.yml`) and `deploy/Caddyfile` are written and validated, but require a target Linux VM with a public DNS record.
2. **Cloud Model API Keys:** Since the local 0.5B model fails on African-language QA, at least one production API key (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY`) must be configured before external users access the platform.
3. **Live Supabase Verification:** Auth flow has been verified with synthetic tokens in tests; end-to-end user sign-up with live confirmation email must be tested against a real Supabase project instance.

---

## 10. Prioritized Development Roadmap

### Priorities Summary
- **P0 — Critical (Launch Blockers):** Supabase live configuration, cloud LLM key configuration, Caddy HTTPS deployment on cloud VM, nightly backup cron.
- **P1 — High (Pilot Essentials):** Table-aware extraction/chunking, RBAC (Admin/Editor/Viewer), expanded African-language evaluation sets (Oromo, Somali, Hausa, Tigrinya), chat pagination.
- **P2 — Medium (Scaling & Monetization):** PostgreSQL + `pgvector` migration, Redis job queue for multi-worker indexing, pan-African payment integration (Chapa, M-Pesa, Paystack).
- **P3 — Low (Future Innovations):** Voice query and TTS (Whisper/SeamlessM4T), WhatsApp/Telegram bot connectors, offline desktop bundle (Tauri).
