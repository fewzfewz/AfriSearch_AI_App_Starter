# AfriSearch AI

[![tests](https://github.com/fewzfewz/AfriSearch_AI_App_Starter/actions/workflows/tests.yml/badge.svg)](https://github.com/fewzfewz/AfriSearch_AI_App_Starter/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![version 0.2.0](https://img.shields.io/badge/version-0.2.0-orange.svg)

Ask questions about your own documents in English, Amharic, Swahili and 90+ other languages. Upload PDFs, text files or photos of pages; AfriSearch finds the relevant passages and writes an answer that cites them, with the original page one click away.

**Quick start with Docker**

```bash
docker compose up --build        # or: docker-compose up --build
```

Then open http://127.0.0.1:8000. The first start downloads about 1 GB of models. Without further setup it runs in **local mode**: no sign-in, one user, only reachable from this computer. To offer it to other people, turn on sign-in first ([Accounts and workspaces](#accounts-and-workspaces)).

> **Status:** v0.2. Accounts, workspaces and the web app are in place for a hosted pilot; HTTPS, backups and billing are still to do. See [ROADMAP.md](ROADMAP.md) and [SECURITY.md](SECURITY.md).

## Features

**Documents**
- Upload PDF, TXT and photos or scans of pages (PNG, JPG, TIFF, WebP, BMP) by drag and drop; exact duplicates are rejected
- OCR for scanned PDFs and photos with Tesseract (English, Amharic and Swahili by default), page by page, so mixed PDFs work
- Indexing runs in the background with live progress (file, page, stage); you can keep working meanwhile
- Library with type, pages, passages, OCR status, size and date; read a document's passages, open the original, delete

**Asking**
- Chat-style questions with saved conversation history; short follow-up questions use the earlier context
- Multilingual search (94 languages, across languages) with a multilingual reranker
- Answers stream as they're written (local models), in the question's language, with `[S1]` citations that open the source passage; the original PDF opens at the cited page
- Questions the documents don't cover are answered with "not covered" and the closest passages, instead of a guess
- Answers from **Claude, ChatGPT, Gemini** or a **local model**; or **find passages only**, with nothing sent to an AI model
- Limit a question to chosen documents; copy, rate (👍/👎 with a comment) or download any answer as Markdown

**Teams and product**
- Sign-in with Supabase (email and password, Google, password reset, email confirmation)
- Workspaces: separate documents, chats and feedback per team or project; owners add members by email
- Insights: questions per day, most-cited documents, answers not covered, ratings and comments
- Landing page, light and dark mode, phone-friendly layout

## Architecture

```
web/                React + TypeScript + Tailwind app (Vite): landing page, sign-in, chat, library, insights, settings
backend/main.py     FastAPI routes under /api; also serves the built web app
backend/auth.py     Sign-in: verifies Supabase tokens, or a single local user when sign-in is off
backend/db.py       SQLite: users, workspaces, members, chats, messages, feedback, indexing jobs
backend/store.py    Per-workspace uploads and search index (chunks + embeddings)
backend/jobs.py     Background indexing with progress
backend/extract.py  PDF/TXT/image text extraction and OCR
backend/models.py   Search model and reranker
backend/answers.py  Prompts, "not covered" rule, follow-up handling
backend/llm.py      Answer-model providers (Claude, ChatGPT, Gemini, local Transformers models)
backend/text.py     Sentence splitting, chunking, citation cleanup
tests/              pytest suite (no downloads, keys or GPU needed)
evaluation/         Question set with known answers + scoring script
data/               afrisearch.db and workspaces/<id>/ (created at runtime)
```

## Requirements

- Python 3.10+ and Node.js 20+ (Node only to build or develop the web app; Docker does both for you)
- About 1 GB of disk for the search model and reranker, plus more for any local answer model
- Optional: **Tesseract** for scans and photos ([install](#2-optional-install-tesseract-for-scans-and-photos)); API keys for Claude / ChatGPT / Gemini; an NVIDIA GPU for the larger local models; a free **Supabase** project for sign-in

## Development setup

Open a terminal in the project folder.

### 1. Python environment and packages

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu   # skip if you have an NVIDIA GPU
pip install -r requirements-dev.txt
```

An existing conda environment with PyTorch works too (`conda activate pytorch_env`).

### 2. (Optional) Install Tesseract for scans and photos

```bash
sudo apt install tesseract-ocr tesseract-ocr-amh tesseract-ocr-swa   # Debian, Ubuntu, Kali
brew install tesseract tesseract-lang                                 # macOS
```

On Windows use the [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki) and add it to `PATH`. On Kali, if `http.kali.org` times out, switch `/etc/apt/sources.list` to `http://kali.download/kali`.

### 3. (Optional) API keys

```bash
export ANTHROPIC_API_KEY=...   # Claude
export OPENAI_API_KEY=...      # ChatGPT
export GEMINI_API_KEY=...      # Gemini
```

Without keys, the small local model (Qwen 2.5 0.5B) answers on your CPU.

### 4. Start the API

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/api/docs

### 5. Start the web app (in another terminal)

```bash
cd web
npm install
npm run dev
```

Open http://localhost:5173. Vite forwards `/api` to the API on port 8000 and reloads the page as you edit. To serve the app from the API instead (as in production), run `npm run build`; the API then serves `web/dist` at http://127.0.0.1:8000.

**Upgrading from 0.1:** on first start, documents in the old `data/uploads` folder and ratings in `data/feedback.jsonl` move into the local user's first workspace automatically.

## Running in production

**[docs/deploy.md](docs/deploy.md) is the step-by-step guide** for one cloud server: HTTPS with Caddy, Supabase, backups, Sentry and uptime monitoring. In short:

1. **Turn on sign-in** ([below](#accounts-and-workspaces)).
2. **Build and run** with Docker: copy `.env.example` to `.env`, fill it in, and run `docker compose up -d --build`. The image includes Tesseract (English, Amharic, Swahili), CPU PyTorch and the built web app; data and models live in the `afrisearch-data` and `afrisearch-models` volumes.
3. **Put HTTPS in front.** Keep the container on `127.0.0.1` and use a reverse proxy, for example [Caddy](https://caddyserver.com) with `reverse_proxy 127.0.0.1:8000`, which gets a certificate automatically. Only then set `AFRISEARCH_BIND=0.0.0.0` if the proxy runs elsewhere.
4. **Back up** nightly with `python -m backend.backup create` (a consistent snapshot, safe while the app runs) and copy the archives off the server; restore with `python -m backend.backup restore <archive>`.

The image runs on CPU. The GPU answer models need an NVIDIA GPU and the NVIDIA container toolkit, which this compose file doesn't set up.

## Accounts and workspaces

| Mode | `AFRISEARCH_AUTH` | Who can use it |
|---|---|---|
| Local | `none` (default) | One local user, no sign-in. For your own computer only. |
| Accounts | `supabase` | Anyone who signs up; each user has their own workspaces. |

**Setting up Supabase sign-in** (free tier is enough to start):
1. Create a project at [supabase.com](https://supabase.com).
2. In **Project Settings → API**, copy the **Project URL** and the **anon public** key into `SUPABASE_URL` and `SUPABASE_ANON_KEY`, and set `AFRISEARCH_AUTH=supabase`.
3. In **Authentication → URL Configuration**, set the **Site URL** to your app's address (for example `https://search.example.org`) and add `https://search.example.org/app` and `/signin` as redirect URLs.
4. Optional: enable **Google** under **Authentication → Providers** and set `AFRISEARCH_AUTH_PROVIDERS=google` to show the button.
5. Restart the API. The sign-in page now offers sign-up, sign-in and password reset; email confirmation follows your Supabase settings.

AfriSearch verifies each request's access token with the project's published signing keys. Projects still on the legacy shared JWT secret set `SUPABASE_JWT_SECRET` instead. Only the token check depends on Supabase, so another provider that issues standard JWTs (Clerk, Auth0) could be added in `backend/auth.py`.

**Workspaces.** Every user starts with a workspace called *My documents* and can create more (one per team, project or client) from the workspace switcher. Each workspace has its own documents, search index, chats, feedback and insights. Its owner can add people who have signed up (**Settings → Members**), rename it, or delete it; members can search, ask, upload and leave. Chats are private to the person who asked.

## Using the app

- **Library:** drag files into the upload area. Upload progress, then indexing progress ("Reading scan.pdf · page 3 of 12"), show live. Files that couldn't be read are listed with the reason. Click a document to read its passages; the ⋯ menu opens the original or deletes it.
- **Ask:** type a question in any language and press Enter (Shift+Enter for a new line). Below the box:
  - **Model**: which model answers and where it runs (Cloud, On this computer, Local GPU), or **Find passages only**. Unavailable models are listed with the reason.
  - **All documents**: tick documents to search only those.
  - **Options**: passages to use (1–8) and reranking.
- **Answers:** click a citation such as **S1** to show its passage, **Open document at page N** to see the original, and the icons below the answer to copy it, download it as Markdown or rate it. The stop button cancels an answer that is being written.
- **Chats** are saved in the sidebar (rename or delete with ⋯). **New chat** starts fresh.
- **Insights** and **Settings** cover usage, ratings, members, appearance and system details.

## Answer models

| Provider id | Default model | Runs on | Needs | Change model with |
|---|---|---|---|---|
| `claude` | `claude-opus-5-5` | Anthropic API | `ANTHROPIC_API_KEY` | `AFRISEARCH_CLAUDE_MODEL`, `AFRISEARCH_CLAUDE_EFFORT` (`low`/`medium`/`high`) |
| `chatgpt` | `gpt-6.1-sol` | OpenAI API | `OPENAI_API_KEY` | `AFRISEARCH_OPENAI_MODEL` |
| `gemini` | `gemini-4-argon` | Google API | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `AFRISEARCH_GEMINI_MODEL` |
| `qwen` | `Qwen/Qwen3.8-27B` | Local GPU | CUDA GPU | `AFRISEARCH_QWEN_MODEL` |
| `gemma` | `google/gemma-4-26B-A4B-it` | Local GPU | CUDA GPU | `AFRISEARCH_GEMMA_MODEL` |
| `gpt-oss` | `openai/gpt-oss-20b` | Local GPU | CUDA GPU | `AFRISEARCH_GPT_OSS_MODEL` |
| `qwen-small` | `Qwen/Qwen2.5-0.5B-Instruct` | Local CPU or GPU | nothing extra | `AFRISEARCH_SMALL_MODEL` |

- **Measured quality:** on the evaluation set (`evaluation/run_eval.py --providers qwen-small`, October 2026) Qwen 2.5 0.5B answered **14 of 39** questions correctly: 14 of 25 in English and **none of the 14** in Amharic, Swahili, Somali, Afaan Oromo or Hausa, even though search found the right document for 38 of them. It's fine for trying AfriSearch offline, not for real users; use a cloud model or a GPU model for them, and measure it the same way.
- **Which model is pre-selected:** `AFRISEARCH_DEFAULT_PROVIDER` (for example `qwen-small`). Otherwise the first available model in the table order is used.
- **Claude refusals:** requests to Claude include Anthropic's server-side refusal fallback. If a safety filter declines a question, the API answers with Anthropic's recommended fallback model instead of returning an error.
- **Privacy:** when you use Claude, ChatGPT or Gemini, the retrieved passages from your documents are sent to that company.
- **Streaming:** local models (except gpt-oss, whose raw output needs cleaning first) show the answer as it is written; the first words of a Qwen 2.5 0.5B answer appear in about a second once the model is loaded. Claude, ChatGPT and Gemini answers appear all at once.
- **Cost:** about $0.01 per question with `claude-opus-5-5` and about half that with `gpt-6.1-sol` (at October 2026 prices). Local models are free.

### Local models

Local models download from Hugging Face the first time you use them (to `~/.cache/hf_models`) and then stay loaded. Picking another local model unloads the previous one to free memory.

| Model | Full precision (bf16) | With `AFRISEARCH_LOCAL_QUANTIZE=4bit` |
|---|---|---|
| Qwen 3.8 27B | ~56 GB GPU | ~17 GB GPU |
| Gemma 4 26B-A4B (fast: 4B active) | ~52 GB GPU | ~16 GB GPU |
| gpt-oss-20b | ~16 GB GPU (ships quantized; ~40 GB if your GPU lacks MXFP4 support) | not applicable |
| Qwen 2.5 0.5B | ~1 GB RAM on CPU | not needed |

- **4-bit loading** needs `pip install bitsandbytes` and an NVIDIA GPU.
- **Answer length:** `AFRISEARCH_LOCAL_MAX_NEW_TOKENS` (default 512) caps it for the GPU models. Qwen 2.5 0.5B is capped at 220 tokens to keep CPU answers fast.
- **GPU models on CPU:** `AFRISEARCH_ALLOW_CPU=1` allows it, but they're very slow and need more RAM than most laptops have.
- **Qwen 2.5 0.5B on a laptop:** on CPU it loads in float32, which most laptop CPUs run much faster than bfloat16. On a 4-core laptop CPU, the first question takes about 30–90 s while the model loads, and later answers take about 5–10 s. Answers to direct questions are usually right, but the model often leaves out citation labels, so check the sources. The 0.5B model only needs transformers 5.x; the 5.8 minimum in `requirements.txt` is for Qwen 3.8.
- **Offline use:** once a model is downloaded, set `HF_HUB_OFFLINE=1` to start without contacting Hugging Face.

## Search

Search runs in two steps:

1. **Find candidates.** The search model turns the question and every passage into vectors and keeps the passages most similar in meaning. Passages below the relevance cutoff are dropped.
2. **Rerank.** The reranker reads the question together with each of the best 12 candidates and reorders them, so the passage that actually answers the question comes first.

Measured with `python evaluation/run_eval.py --retrieval-only --embedders sentence-transformers/all-MiniLM-L6-v2 intfloat/multilingual-e5-small --modes semantic rerank` on the 39 answerable evaluation questions:

| | `all-MiniLM-L6-v2` | `multilingual-e5-small` | `multilingual-e5-small` + reranker |
|---|---|---|---|
| Right document **ranked first** | 28/39 | 32/39 | **36/39** |
| Right document in the top 4 | 29/39 | **38/39** | **38/39** |
| … English questions (25) | 23 | 25 | 25 |
| … Amharic (6) | 3 | 6 | 6 |
| … Swahili (5) | 3 | 5 | 5 |
| … Somali, Afaan Oromo, Hausa (1 each) | 0 | 2 | 2 |

### Search model

The default search model is [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small) (MIT licence, about 470 MB, downloads on first use). It understands 94 languages and matches questions to documents across languages, for example an English question to a Swahili guide.

- **Relevance cutoff:** E5 models score even unrelated text fairly high (about 0.7–0.83 here), so the cutoff is 0.75 for them instead of 0.2. Cross-language questions often score 0.75–0.80, and a higher cutoff started dropping correct passages. The trade-off is that only some off-topic questions are filtered out; the answer model is told to say when the documents don't cover a question. To tune the cutoff for your own documents, run the evaluation with your own questions and look at the *suggested cutoff* lines.
- **Switching models:** set `AFRISEARCH_EMBEDDER`, for example `sentence-transformers/all-MiniLM-L6-v2` for a smaller, faster English-only setup. Documents indexed with another model are left out of search, because their vectors can't be compared, and the Library shows **Re-index now** to update them.

### Reranker

The default reranker is [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1) (Apache 2.0, about 470 MB, multilingual). It downloads the first time a question is reranked.

- **Speed:** on a 4-core laptop CPU the first reranked question takes about 10 s while the model loads; after that reranking adds about 0.5 s per question.
- **What it changes:** the order of the passages, and whether the answer model is asked at all (see *Questions your documents don't answer* below). The relevance cutoff still uses the search model's score, and the **% match** on source cards still shows that score.
- **Turning it off:** switch off **Rerank passages** under **Options** below the question box, send `"rerank": false` to `/api/ask`, or set `AFRISEARCH_RERANKER=off` to never load it. `AFRISEARCH_RERANKER` also takes another cross-encoder model id.

### Questions your documents don't answer

When reranking is on and even the best passage scores below `AFRISEARCH_MIN_RERANK_SCORE` (default −5), AfriSearch doesn't ask the answer model. It says the documents don't seem to cover the question and shows the closest passages instead. Small models in particular tend to invent answers when given unrelated passages.

On the evaluation set this stopped 3 of the 6 off-topic questions (2 were already stopped by the relevance cutoff), and no answerable question: the lowest-scoring answerable one scored −3.2. A threshold of −4 stopped 5 of 6 but sits closer to real answers, so measure on your own documents before raising it.

### Only close passages reach the model

Small models mix up facts when unrelated passages sit next to the right one: in testing, Qwen 2.5 0.5B answered "once a month" (the rainy-season figure) instead of "every two weeks" when a Swahili poultry guide and an Amharic coffee guide were among its passages. So when reranking is on, passages scoring more than `AFRISEARCH_RERANK_GAP` (default 5) below the best one are dropped, from the prompt and from the sources shown. On the evaluation set any gap from 3 to 8 kept the right document for all 39 questions; 5 removed 45% of the passages.

### Answer language and follow-up questions

- Answers are written in the language of the question. Amharic questions (Ge'ez script) get an explicit instruction to answer in Amharic, because small models otherwise drift into English.
- In a chat, short follow-up questions ("and the batteries?") are searched together with the previous question, and the model sees the last two answers as context.

### Tried and not adopted: keyword (hybrid) search

Merging a keyword ranking (BM25) with the semantic ranking is a common way to catch exact names, numbers and product codes. It was tested here and left out:

- Keyword matching only works within one language, so it pushed same-language documents above the right answer for cross-language questions. With rank fusion, "right document in the top 4" dropped from 38/39 to 36/39, even with the keyword ranking at a quarter of the weight.
- It brought no gain on questions built to need exact matches (`kw-*` in the evaluation set: three spec sheets that differ only in model code and numbers). The multilingual search model already ranked the right sheet first for all of them, and with MiniLM it made no difference.

If your documents are full of codes the search model confuses, measure it on your own questions before adding it.


## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `AFRISEARCH_AUTH` | `none` | `none` (local, one user) or `supabase` (accounts) |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | – | Supabase project URL and public anon key |
| `SUPABASE_JWT_SECRET` | – | Only for projects on the legacy shared secret |
| `AFRISEARCH_AUTH_PROVIDERS` | – | Extra sign-in buttons, e.g. `google` |
| `AFRISEARCH_DATA_DIR` | `./data` | Database, uploads and indexes |
| `AFRISEARCH_WEB_DIST` | `./web/dist` | Built web app served at `/` |
| `AFRISEARCH_DEFAULT_PROVIDER` | first available | Pre-selected answer model |
| `AFRISEARCH_EMBEDDER` | `intfloat/multilingual-e5-small` | Search model; documents must be re-indexed after changing it |
| `AFRISEARCH_MIN_SCORE` | `0.75` for E5 models, `0.2` otherwise | Passages less similar than this are ignored |
| `AFRISEARCH_QUERY_PREFIX` / `AFRISEARCH_PASSAGE_PREFIX` | `query: ` / `passage: ` for E5 models | Text added before questions / passages when embedding |
| `AFRISEARCH_RERANKER` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Reranking model; `off` disables reranking |
| `AFRISEARCH_MIN_RERANK_SCORE` | `-5` | Below this best reranker score, a question counts as not covered |
| `AFRISEARCH_RERANK_GAP` | `5` | Passages scoring this far below the best reranked one aren't given to the model |
| `AFRISEARCH_OCR_LANGS` | `eng+amh+swa` | Tesseract languages, joined with `+`; ones not installed are skipped |
| `AFRISEARCH_LOCAL_QUANTIZE` | off | `4bit` loads Qwen 3.8 and Gemma 4 in 4-bit |
| `AFRISEARCH_LOCAL_MAX_NEW_TOKENS` | `512` | Answer length cap for local GPU models |
| `AFRISEARCH_ALLOW_CPU` | off | `1` lets GPU models run on CPU |
| `AFRISEARCH_WORKSPACE_QUOTA_MB` | `500` | Storage per workspace (0 = no limit) |
| `AFRISEARCH_ASK_PER_MINUTE`, `AFRISEARCH_ASK_PER_DAY` | `20`, `500` | Questions per user (0 = no limit) |
| `AFRISEARCH_UPLOADS_PER_HOUR` | `200` | Uploaded files per user (0 = no limit) |
| `AFRISEARCH_ORG_NAME`, `AFRISEARCH_CONTACT_EMAIL` | – | Shown on the privacy notice and terms pages |
| `SUPABASE_SERVICE_ROLE_KEY` | – | Secret; lets "Delete my account" remove the Supabase account too |
| `SENTRY_DSN`, `SENTRY_DSN_WEB` | – | Error reports to Sentry from the API and the web app |
| `AFRISEARCH_ENV` | `development` | Environment name in error reports |
| `AFRISEARCH_BIND` | `127.0.0.1` | Docker only: address the container's port is published on |
| `HF_HOME` | `~/.cache/hf_models` | Where model weights are stored |

The model-name variables are listed in [Answer models](#answer-models).

## API

All endpoints are under `/api`; interactive docs at `/api/docs`. With sign-in on, send `Authorization: Bearer <Supabase access token>`. Workspace endpoints act on the workspace in the `X-Workspace-Id` header, or the user's first workspace.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/config` | Public: sign-in mode and Supabase settings for the web app, upload limits |
| `GET` | `/api/me` | The signed-in user and their workspaces |
| `GET` | `/api/me/export` | A zip of the user's data and the documents of workspaces they own |
| `DELETE` | `/api/me` | Delete the account: `{"confirm": "<email>"}` (or `DELETE` in local mode) |
| `GET`, `POST` | `/api/workspaces` | List or create workspaces |
| `PATCH`, `DELETE` | `/api/workspaces/{id}` | Rename or delete (owner) |
| `GET`, `POST` | `/api/workspaces/{id}/members` | List members, or add one by `{"email"}` (owner) |
| `DELETE` | `/api/workspaces/{id}/members/{user_id}` | Remove a member (owner), or leave |
| `POST` | `/api/documents/upload` | Upload files (multipart field `files`) |
| `POST` | `/api/documents/index` | Index new uploads; `?wait=false` runs it as a background job, `?full=true` re-reads everything |
| `GET` | `/api/jobs`, `/api/jobs/{id}` | Indexing jobs and their progress (`?active=true` for running ones) |
| `GET` | `/api/documents` | Documents with details, counts, search model, reranker, OCR status |
| `GET` | `/api/documents/{id}/passages` | A document's indexed passages |
| `GET` | `/api/documents/{id}/file` | The original uploaded file |
| `DELETE` | `/api/documents/{id}` | Delete a document |
| `GET` | `/api/providers` | Answer models, whether each is available, and why not |
| `POST` | `/api/ask` | `{"question", "top_k", "provider", "rerank", "generate_answer", "source_ids", "chat_id", "save"}` → answer, sources, `covered`, chat and message ids |
| `POST` | `/api/ask/stream` | Same request; newline-delimited JSON events: `sources`, `token` pieces, then `done` or `error` |
| `GET`, `POST` | `/api/chats` | The user's chats in the workspace, or create one |
| `GET`, `PATCH`, `DELETE` | `/api/chats/{id}` | A chat with its messages; rename; delete |
| `POST`, `GET` | `/api/feedback` | Rate an answer (`message_id` links it to a chat message); totals and recent ratings |
| `GET` | `/api/insights` | Usage, questions per day, most-cited documents, ratings |
| `GET` | `/api/health` | 200 when the database and data folder work, 503 otherwise; version, models, OCR |

## Testing

```bash
pytest -q                      # backend: fake models, fake OCR, temporary data; no downloads or keys
cd web && npm test             # web app unit tests
cd web && npm run typecheck
```

| File | Covers |
|---|---|
| `tests/test_security.py` | Upload content checks and size limits, rate limits, storage quota, security headers, health check |
| `tests/test_backup.py` | Backup and restore round trip, retention, refusing to overwrite, archive path tricks |
| `tests/test_accounts.py` | Supabase tokens (shared secret and published keys; expired, forged, wrong audience), users kept apart, workspaces, members and roles |
| `tests/test_chats.py` | Saved chats, follow-ups, ratings on messages, background jobs and progress, "not covered" rule, answer language, file download, insights |
| `tests/test_documents.py` | Upload, duplicates, incremental and full indexing, failed files, delete, restart |
| `tests/test_ask.py`, `tests/test_stream.py` | `/api/ask` and `/api/ask/stream`: citations, cutoff, providers, errors |
| `tests/test_library.py` | Document details, passages, search scope, feedback, moving 0.1 data |
| `tests/test_search_model.py`, `tests/test_reranker.py` | Search-model settings and re-indexing, reranking |
| `tests/test_ocr.py` | Scanned and mixed PDFs, images, OCR languages, missing Tesseract |
| `tests/test_providers.py` | Claude, ChatGPT and Gemini requests against a local mock server |
| `tests/test_text_processing.py`, `tests/test_evaluation_scoring.py` | Chunking, citations, grading rules |
| `web/src/lib/format.test.ts` | Citation links, stream parsing, formatting |

GitHub Actions runs the backend tests, the web app checks and build, and a Docker build on every push and pull request.

## Evaluating answer quality

`evaluation/` scores search and the answer models on questions with known answers. It shows whether a change actually helps, for example a different search model, the reranker, a different `AFRISEARCH_MIN_SCORE`, or Claude versus a local model.

- **Sample documents:** `evaluation/corpus/`, nine short illustrative documents: four English guides (solar maintenance, grain storage, mobile money safety, drinking water), one Amharic guide (coffee), one Swahili guide (chickens), and three near-identical product sheets for a fictional solar kit that differ only in model code and numbers.
- **Questions:** `evaluation/questions.json`, 39 questions the documents answer and 6 they don't. 16 are in Amharic, Swahili, Somali, Afaan Oromo or Hausa, some ask in one language about a document in another, and five (`kw-*`) can only be answered by telling the product sheets apart.

```bash
python evaluation/run_eval.py --retrieval-only                 # search only, takes seconds
python evaluation/run_eval.py --retrieval-only --embedders sentence-transformers/all-MiniLM-L6-v2 intfloat/multilingual-e5-small
python evaluation/run_eval.py --retrieval-only --modes semantic rerank   # with and without the reranker
python evaluation/run_eval.py --providers qwen-small           # one answer model
python evaluation/run_eval.py --providers claude chatgpt gemini --top-k 6
```

The script indexes the documents into a temporary folder, so your `data/` folder is never touched. It prints a summary and every wrong answer, and saves a full JSON report in `evaluation/results/`.

| Metric | Meaning |
|---|---|
| right document ranked first / in top k | Search found a passage from the document that answers the question |
| off-topic questions with no passages | The relevance cutoff filtered the question out before any model saw it |
| in top k, questions in '…' | The same, broken down by question language |
| suggested cutoff | Lowest score of a correct top passage vs. highest score of an off-topic one; a cutoff is suggested only if they don't overlap |
| correct | The answer contains every required fact (accepted wordings are listed per fact) |
| cites right doc | The answer cites an `[S#]` label from the document that answers the question |
| says not covered | For the 6 off-topic questions: the model said the documents don't cover them instead of inventing an answer |

The grading uses keyword checks, not an AI judge. It is free and gives the same result every time, but it can mark an oddly worded correct answer as wrong, so read the listed failures.

**Using your own documents:** put them in a folder and write a questions file in the same format:
```json
[
  {"id": "q1", "question": "...", "source": "my_file.pdf", "must_include": [["fact wording", "other wording"]]},
  {"id": "q2", "question": "A question the documents don't answer", "source": null}
]
```
```bash
python evaluation/run_eval.py --corpus my_docs/ --questions my_questions.json --providers qwen-small
```


## Troubleshooting

- **"Can't reach the AfriSearch server":** start the API (`uvicorn …`, step 4). In development, open the Vite address (5173), which forwards `/api`.
- **The page at port 8000 shows JSON instead of the app:** the web app isn't built. Run `cd web && npm install && npm run build`.
- **Sign-in page says sign-in isn't configured:** set `SUPABASE_URL` and `SUPABASE_ANON_KEY` and restart the API.
- **"Invalid sign-in token" after signing in:** the API and the web app use different Supabase projects, or a legacy project needs `SUPABASE_JWT_SECRET`.
- **"No account uses that email yet" when adding a member:** they need to sign up once first.
- **A model is missing from the model menu:** the menu lists unavailable models with the reason, usually a missing API key or no GPU.
- **"needs OCR, which is not available":** install Tesseract and restart the API; then use **Index now** in the Library to retry.
- **OCR text is poor:** use clear, straight, well-lit scans (about 300 dpi). Handwriting isn't supported.
- **The first answer is slow:** local models and the reranker load on first use. Later answers are much faster.

## Notes and limitations

- PDF, TXT and common image formats are supported; Word, Excel and other formats aren't yet.
- Answers and citations can be wrong, especially from the small local model. Every answer links to its sources.
- With a cloud model, the passages needed for an answer are sent to that provider; use a local model for sensitive documents.
- Data is stored in SQLite and files on one server. That suits a pilot; many concurrent users need PostgreSQL and object storage (see the roadmap).
- Usage limits (questions, uploads, storage) are counted per server process. There is no billing yet.

## Project

- [ROADMAP.md](ROADMAP.md): from this release to a paid service
- [CHANGELOG.md](CHANGELOG.md): what changed in each version
- [CONTRIBUTING.md](CONTRIBUTING.md): reporting problems and contributing; evaluation questions in African languages are especially welcome
- [SECURITY.md](SECURITY.md): security limits and how to report a vulnerability

## License

AfriSearch is released under the [MIT license](LICENSE). The models it downloads have their own licenses: `multilingual-e5-small` (MIT), the reranker and Qwen 2.5 (Apache 2.0), Tesseract (Apache 2.0); Gemma 4, Supabase and the hosted AI APIs have their own terms.
