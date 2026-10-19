# AfriSearch AI

[![tests](https://github.com/fewzfewz/AfriSearch_AI_App_Starter/actions/workflows/tests.yml/badge.svg)](https://github.com/fewzfewz/AfriSearch_AI_App_Starter/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![version 0.1.0](https://img.shields.io/badge/version-0.1.0-orange.svg)

Ask questions about your own documents, in English, Amharic, Swahili and 90+ other languages. Upload PDFs, text files or photos of documents, and AfriSearch finds the most relevant passages and writes an answer that cites them.

**Quick start with Docker**

```bash
docker compose up --build        # or: docker-compose up --build
```

Then open http://127.0.0.1:8501. The first start downloads about 1 GB of models. To use Claude, ChatGPT or Gemini, set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` in your shell or a `.env` file first. See [Running with Docker](#running-with-docker), or [Setup](#setup) to run without Docker.

> **Status:** v0.1, for local use by one person or a trusted team. It has no logins yet, so don't expose it to the internet ([SECURITY.md](SECURITY.md)). The plan to a hosted release is in [ROADMAP.md](ROADMAP.md).

**Features**
- Upload PDF and TXT documents, and photos or scans of pages (PNG, JPG, TIFF, WebP, BMP); exact duplicates are rejected
- OCR for scanned PDFs and photos with Tesseract, in English, Amharic and Swahili by default; PDFs that mix typed and scanned pages work too
- Extract text with page numbers, split it into sentence-aware chunks that can span pages, and embed them
- Index only new files (a full rebuild is optional), and delete documents from the UI
- Multilingual semantic search (94 languages, including Amharic, Swahili, Somali, Hausa and Afaan Oromo), so a question in one language can find a document in another
- A reranker that rereads the best matches and puts the most relevant passage first (can be switched off per question)
- A relevance cutoff, so clearly unrelated passages are never passed to the model
- Answers from **Claude, ChatGPT, Gemini** or a **local open-weight model**, picked per question; local models show the answer as it is written
- Citations like `[S1]` link to the source passages; citations that don't match a source are removed
- Files that can't be indexed (for example a scan when OCR isn't installed) are reported in the UI, with the reason
- **Ask** tab: choose which documents to search, write an answer or just find passages, citations that jump to their source, 👍/👎 ratings with comments, and Markdown export of an answer or the whole session
- **Library** tab: every document with its type, pages, passages, OCR status, size and date; read its passages or delete it
- **Insights** tab: library and session statistics, and the ratings everyone has given
- Light and dark mode, and a layout that works on phones
- The index stays on disk between restarts

## Architecture

```
frontend/app.py   Streamlit UI: upload, index status, model picker, streamed answers, sources
.streamlit/       UI theme (light and dark) and upload size limit
backend/main.py   FastAPI: ingestion, OCR, chunking, embeddings, retrieval, reranking, /ask
backend/llm.py    Answer-model providers (Claude, ChatGPT, Gemini, local Transformers models)
tests/            pytest suite (no downloads, keys or GPU needed)
evaluation/       question set with known answers + scoring script
data/             uploads/, index.json, embeddings.npy, manifest.json, feedback.jsonl (created at runtime)
Dockerfile, docker-compose.yml   container image (with Tesseract) and the two services
.github/workflows/               tests and Docker build on every push
```

- **Search model:** `intfloat/multilingual-e5-small`, with the `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` reranker (see [Search](#search))
- **Answer models:** see [Answer models](#answer-models)
- **Storage:** local files under `data/` (a starter implementation, not production storage)

## Requirements

- Python 3.10+
- Internet access on the first run, to install packages and download model weights
- About 1 GB of free disk space for the search model and reranker (about 470 MB each), plus more for any local answer model
- For **Claude / ChatGPT / Gemini**: an API key from the provider
- For **Qwen 3.8, Gemma 4 and gpt-oss**: an NVIDIA GPU (see [GPU memory](#local-models))
- **Qwen 2.5 0.5B** runs on an ordinary laptop CPU, with no key or GPU
- For **scanned PDFs and photos**: the Tesseract OCR program (see [setup step 3](#3-optional-install-tesseract-for-scanned-pdfs-and-photos))

## Setup

Open a terminal in the project folder.

### 1. Create and activate a virtual environment

Linux/macOS:
```bash
python -m venv .venv
source .venv/bin/activate
```

Windows:
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Or use an existing conda environment that already has PyTorch, for example:
```bash
conda activate pytorch_env
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

On a machine without an NVIDIA GPU, the CPU build of PyTorch is a much smaller download:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### 3. (Optional) Install Tesseract for scanned PDFs and photos

Typed PDFs and text files work without it. To read scans and photos, install Tesseract and the languages you need:

```bash
# Debian, Ubuntu, Kali
sudo apt install tesseract-ocr tesseract-ocr-amh tesseract-ocr-swa
# macOS (Homebrew); tesseract-lang contains all languages
brew install tesseract tesseract-lang
```

On Windows, use the installer from [UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki), tick the extra languages you need, and add the install folder to `PATH`. Restart the API afterwards. The sidebar shows whether OCR is on and which languages it uses.

### 4. (Optional) Add API keys

Set the keys for the hosted models you want to use in the terminal that will run the API:

```bash
export ANTHROPIC_API_KEY=...   # Claude
export OPENAI_API_KEY=...      # ChatGPT
export GEMINI_API_KEY=...      # Gemini
```

Windows PowerShell: `$env:ANTHROPIC_API_KEY="..."`. Without keys you can still use the local models.

### 5. Start the API

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 6. Start the UI in another terminal

Activate the same virtual environment, then:
```bash
streamlit run frontend/app.py
```

The UI opens at http://localhost:8501.

## Running with Docker

```bash
docker compose up --build        # older installs: docker-compose up --build
```

- **UI:** http://127.0.0.1:8501 · **API docs:** http://127.0.0.1:8000/docs
- The image includes Tesseract with English, Amharic and Swahili, and the CPU build of PyTorch.
- Documents, the index and feedback are kept in the `afrisearch-data` volume, and downloaded models in `afrisearch-models`, so they survive restarts and upgrades. `docker compose down -v` deletes them.
- API keys and settings (`AFRISEARCH_DEFAULT_PROVIDER`, `AFRISEARCH_RERANKER`, `AFRISEARCH_OCR_LANGS`) are read from your shell or a `.env` file next to `docker-compose.yml`.
- Both services listen on `127.0.0.1` only. Don't change that until logins exist ([SECURITY.md](SECURITY.md)).
- The image runs on CPU. The GPU answer models (Qwen 3.8, Gemma 4, gpt-oss) need an NVIDIA GPU and the NVIDIA container toolkit, which this compose file doesn't set up.

## Using the app

The sidebar is for adding documents; the main area has three tabs.

1. **Add documents:** in the sidebar, choose PDF, TXT or image files and click **Upload and index**. Only new files are processed; scanned pages are read with OCR, which takes a few seconds per page. Files that couldn't be indexed are listed with the reason.
2. **Ask tab:**
   - The line above the question shows which model will answer and where it runs (Cloud API, Local · GPU or Local · CPU).
   - **Settings** changes the mode (**Write an answer**, or **Find passages only**: instant, and nothing is sent to a cloud API), the answer model, the number of passages and reranking. **Other models** there explains why the rest are unavailable.
   - **Search in** limits the search to the documents you pick; leave it empty to search everything.
   - Type a question in any language and press **Ask AfriSearch** or **Ctrl+Enter**. With a local model, the answer appears as it is written.
3. **Check the answer:** click a citation such as **S1** to jump to its source card, which shows the file, pages, relevance, reranker score and whether the text came from OCR. Always check important claims against the sources.
4. **Rate and save:** **Rate this answer** records 👍 or 👎 with an optional comment. **Download** saves the question, answer and sources as Markdown, and **Download session** saves every question from this session.
5. **Library tab:** all documents in a table. Filter by name, select a row to read its passages, or delete it (with confirmation).
6. **Insights tab:** document and passage counts, this session's questions and average answer time, and the ratings from everyone using this server.

**Advanced → Rebuild full index** processes every document again. You rarely need it: when the search model or chunk settings change, the sidebar shows which documents are out of date, and **Re-index now** (or **Upload and index**) updates just those.

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
- **Switching models:** set `AFRISEARCH_EMBEDDER`, for example `sentence-transformers/all-MiniLM-L6-v2` for a smaller, faster English-only setup. Documents indexed with another model are left out of search, because their vectors can't be compared, and the sidebar shows **Re-index now** to update them.

### Reranker

The default reranker is [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1) (Apache 2.0, about 470 MB, multilingual). It downloads the first time a question is reranked.

- **Speed:** on a 4-core laptop CPU the first reranked question takes about 10 s while the model loads; after that reranking adds about 0.5 s per question.
- **What it changes:** only the order of the passages. The relevance cutoff still uses the search model's score, and **relevance** in the UI still shows that score. Reranker scores didn't separate answerable from off-topic questions reliably enough to use as a cutoff.
- **Turning it off:** use the **Rerank passages** toggle per question, send `"rerank": false` to `/ask`, or set `AFRISEARCH_RERANKER=off` to never load it. `AFRISEARCH_RERANKER` also takes another cross-encoder model id.

### Tried and not adopted: keyword (hybrid) search

Merging a keyword ranking (BM25) with the semantic ranking is a common way to catch exact names, numbers and product codes. It was tested here and left out:

- Keyword matching only works within one language, so it pushed same-language documents above the right answer for cross-language questions. With rank fusion, "right document in the top 4" dropped from 38/39 to 36/39, even with the keyword ranking at a quarter of the weight.
- It brought no gain on questions built to need exact matches (`kw-*` in the evaluation set: three spec sheets that differ only in model code and numbers). The multilingual search model already ranked the right sheet first for all of them, and with MiniLM it made no difference.

If your documents are full of codes the search model confuses, measure it on your own questions before adding it.

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `AFRISEARCH_API_URL` | `http://127.0.0.1:8000` | Where the UI finds the API |
| `AFRISEARCH_DEFAULT_PROVIDER` | first available | Pre-selected answer model |
| `AFRISEARCH_EMBEDDER` | `intfloat/multilingual-e5-small` | Search model; documents must be re-indexed after changing it |
| `AFRISEARCH_MIN_SCORE` | `0.75` for E5 models, `0.2` otherwise | Passages less similar than this are ignored |
| `AFRISEARCH_QUERY_PREFIX` / `AFRISEARCH_PASSAGE_PREFIX` | `query: ` / `passage: ` for E5 models | Text added before questions / passages when embedding |
| `AFRISEARCH_RERANKER` | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | Reranking model; `off` disables reranking |
| `AFRISEARCH_OCR_LANGS` | `eng+amh+swa` | Tesseract languages for OCR, joined with `+` (e.g. `eng+amh+swa+som`); ones not installed are skipped |
| `AFRISEARCH_LOCAL_QUANTIZE` | off | `4bit` loads Qwen 3.8 and Gemma 4 in 4-bit |
| `AFRISEARCH_LOCAL_MAX_NEW_TOKENS` | `512` | Answer length cap for local GPU models |
| `AFRISEARCH_ALLOW_CPU` | off | `1` lets GPU models run on CPU |
| `HF_HOME` | `~/.cache/hf_models` | Where model weights are stored |

The model-name variables are listed in [Answer models](#answer-models).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload PDF, TXT or image files (multipart field `files`) |
| `POST` | `/documents/index` | Index new uploads; `?full=true` rebuilds everything. Returns failed files |
| `GET` | `/documents` | Indexed documents (type, pages, passages, OCR, size, upload time), chunk count, documents needing re-indexing, search model, reranker and OCR status |
| `GET` | `/documents/{source_id}/passages` | The indexed passages of one document, with pages and OCR flags |
| `DELETE` | `/documents/{source_id}` | Delete a document and its chunks |
| `GET` | `/providers` | Answer models, whether each is available, and why not |
| `POST` | `/ask` | `{"question", "top_k", "provider", "rerank", "generate_answer", "source_ids"}` → answer, sources (with `score` and `rerank_score`), whether they were reranked, removed citations. `source_ids` limits the search to those documents |
| `POST` | `/ask/stream` | Same request as `/ask`; streams newline-delimited JSON events: `sources`, then `token` pieces of the answer, then `done` (cleaned answer) or `error` |
| `POST` | `/feedback` | `{"rating": "up" or "down", "question", "answer", "provider", "comment", "sources"}`; appended to `data/feedback.jsonl` |
| `GET` | `/feedback` | Rating totals and the most recent ratings (`?limit=20`) |
| `GET` | `/` | Name and version |
| `GET` | `/health` | Status, chunk count, search model, reranker and OCR status |

## Testing

The tests use a fake search model, a fake reranker, fake OCR, a fake answer model and a temporary data folder. They need no downloads, API keys or GPU, and never touch your `data/` folder.

```bash
pip install -r requirements-dev.txt   # adds pytest and httpx
pytest -q
```

| File | Covers |
|---|---|
| `tests/test_text_processing.py` | Chunking, citation cleanup, page formatting |
| `tests/test_documents.py` | Upload, duplicate rejection, incremental and full indexing, failed files, delete, reload from disk |
| `tests/test_ask.py` | `/ask`: cited answers, relevance cutoff, provider selection and errors |
| `tests/test_search_model.py` | Per-model prefixes and cutoffs, environment overrides, re-indexing after a model change |
| `tests/test_reranker.py` | Reranking order, candidate count, cutoff before reranking, turning reranking off |
| `tests/test_ocr.py` | Scanned and mixed PDFs, images, OCR languages, missing Tesseract, blank scans |
| `tests/test_stream.py` | `/ask/stream` events, cleaned citations, errors during generation, search-only requests |
| `tests/test_library.py` | Document details, passages, search scope, feedback storage and summary, version |
| `tests/test_providers.py` | Claude, ChatGPT and Gemini requests (real SDKs against a local mock server), availability checks, gpt-oss output parsing |
| `tests/test_evaluation_scoring.py` | The evaluation script's grading rules |

The Claude, ChatGPT and Gemini tests are skipped when their SDK isn't installed. GitHub Actions runs the tests, and builds and checks the Docker image, on every push and pull request.

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

- **"Cannot reach the API":** start the backend (step 5) before the UI, and check `AFRISEARCH_API_URL`.
- **A model is missing from the picker:** open **Other models** for the reason. Usually a key isn't set in the terminal running the API, or there's no GPU.
- **"No passages were similar enough":** rephrase the question, or lower `AFRISEARCH_MIN_SCORE`.
- **"documents were indexed with a different search model" / HTTP 409 from `/ask`:** the search model or chunk settings changed. Click **Re-index now** in the sidebar.
- **"needs OCR, which is not available":** the file is a scan or photo and Tesseract isn't installed, or the API can't find it. Install it ([setup step 3](#3-optional-install-tesseract-for-scanned-pdfs-and-photos)) and restart the API. Then click **Upload and index** (no new files needed): files that failed before are retried.
- **OCR text is poor:** OCR needs clear, straight, well-lit pages of at least about 300 dpi. Handwriting isn't supported. Check that the document's language is installed (`tesseract --list-langs`) and listed in `AFRISEARCH_OCR_LANGS`.
- **Out of GPU memory:** set `AFRISEARCH_LOCAL_QUANTIZE=4bit`, or use gpt-oss-20b.
- **Only "Qwen 2.5 0.5B" is offered:** that's expected on a machine with no API keys and no NVIDIA GPU. Add keys (setup step 4) to enable Claude, ChatGPT or Gemini; for those, also install `anthropic`, `openai` and `google-genai` into the environment.
- **The first local answer is slow:** the model loads on the first question. Later questions are much faster.
- **The first search is slow:** the search model and reranker load on first use (about 10 s on a laptop CPU, plus the download the very first time). Set `AFRISEARCH_RERANKER=off` if you don't want the reranker.

## Notes and limitations

- PDF, TXT and common image formats are supported; Word, Excel and other formats aren't. OCR doesn't read handwriting, and Tesseract has no language data for Afaan Oromo or Hausa (their Latin script is usually read acceptably with English).
- Documents are stored locally in `data/uploads/`. Don't upload private or sensitive documents unless you control the machine and understand the risks.
- Generated answers and citations can be wrong, especially from the small local model. Always check the source passages.
- The app is for local use, not public deployment: there are no logins, and every user sees every document and all feedback. [SECURITY.md](SECURITY.md) explains the risks, and [ROADMAP.md](ROADMAP.md) the plan for logins, separate document spaces, HTTPS and backups.
- Indexing runs inside the request, so very long scans can take minutes (background indexing is next on the roadmap).
- The simple NumPy vector index is fine for small collections. Replace it with a vector database for large ones.
- Local models load the first time you ask a question with them, so uploading, indexing and searching never download them.

## Project

- [ROADMAP.md](ROADMAP.md): the plan from this open-source release to a hosted pilot
- [CHANGELOG.md](CHANGELOG.md): what changed in each version
- [CONTRIBUTING.md](CONTRIBUTING.md): how to report problems and contribute; evaluation questions in African languages are especially welcome
- [SECURITY.md](SECURITY.md): current security limits and how to report a vulnerability

## License

AfriSearch is released under the [MIT license](LICENSE). The models it downloads have their own licenses: `multilingual-e5-small` (MIT), the reranker and Qwen 2.5 (Apache 2.0), Tesseract (Apache 2.0); Gemma 4 and the hosted APIs have their own terms of use.
