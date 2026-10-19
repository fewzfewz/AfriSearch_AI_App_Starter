# AfriSearch AI — Web App Starter

A local app for asking questions about your own documents. Upload PDF or TXT files, and AfriSearch finds the most relevant passages and writes an answer that cites them. It turns the Notebook 5 pipeline into a web app.

**Features**
- Upload PDF and TXT documents; exact duplicates are rejected
- Extract text with page numbers, split it into sentence-aware chunks that can span pages, and embed them
- Index only new files (a full rebuild is optional), and delete documents from the UI
- Multilingual semantic search (94 languages, including Amharic, Swahili, Somali, Hausa and Afaan Oromo), so a question in one language can find a document in another
- A reranker that rereads the best matches and puts the most relevant passage first (can be switched off per question)
- A relevance cutoff, so clearly unrelated passages are never passed to the model
- Answers from **Claude, ChatGPT, Gemini** or a **local open-weight model**, picked per question
- Citations like `[S1]` link to the source passages; citations that don't match a source are removed
- Files that can't be indexed (for example scanned PDFs) are reported in the UI
- The index stays on disk between restarts

## Architecture

```
frontend/app.py   Streamlit UI: upload, index status, model picker, answers, sources
backend/main.py   FastAPI: ingestion, chunking, embeddings, retrieval, /ask
backend/llm.py    Answer-model providers (Claude, ChatGPT, Gemini, local Transformers models)
tests/            pytest suite (no downloads, keys or GPU needed)
evaluation/       question set with known answers + scoring script
data/             uploads/, index.json, embeddings.npy, manifest.json (created at runtime)
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

### 3. (Optional) Add API keys

Set the keys for the hosted models you want to use in the terminal that will run the API:

```bash
export ANTHROPIC_API_KEY=...   # Claude
export OPENAI_API_KEY=...      # ChatGPT
export GEMINI_API_KEY=...      # Gemini
```

Windows PowerShell: `$env:ANTHROPIC_API_KEY="..."`. Without keys you can still use the local models.

### 4. Start the API

```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### 5. Start the UI in another terminal

Activate the same virtual environment, then:
```bash
streamlit run frontend/app.py
```

The UI opens at http://localhost:8501.

## Using the app

1. **Add documents:** in the sidebar, choose `.pdf` or `.txt` files and click **Upload and index**. Only new files are processed. The sidebar shows the document and chunk counts, the indexed files (🗑 deletes one), and any file that couldn't be indexed.
2. **Pick a model:** **Answer model** lists the models that are ready to use. A badge shows where the selected one runs (Cloud API, Local · GPU or Local · CPU). **Other models** explains why the rest are unavailable, for example a missing API key or no GPU.
3. **Ask:** type a question and press **Ask AfriSearch** or **Ctrl+Enter**. **Passages to retrieve** sets how many passages the model sees. **Rerank passages** (on by default) puts the most relevant passages first; turn it off for slightly faster searches.
4. **Check the answer:** citations such as **S1** are highlighted. Under **Sources**, each passage shows its file, pages and relevance (and its reranker score when reranking was used). Always check important claims against them.
5. **Earlier answers:** your last 10 answers stay available in the session. Click **Show** to bring one back.

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
| `AFRISEARCH_LOCAL_QUANTIZE` | off | `4bit` loads Qwen 3.8 and Gemma 4 in 4-bit |
| `AFRISEARCH_LOCAL_MAX_NEW_TOKENS` | `512` | Answer length cap for local GPU models |
| `AFRISEARCH_ALLOW_CPU` | off | `1` lets GPU models run on CPU |
| `HF_HOME` | `~/.cache/hf_models` | Where model weights are stored |

The model-name variables are listed in [Answer models](#answer-models).

## API

| Method | Path | Description |
|---|---|---|
| `POST` | `/documents/upload` | Upload files (multipart field `files`) |
| `POST` | `/documents/index` | Index new uploads; `?full=true` rebuilds everything. Returns failed files |
| `GET` | `/documents` | Indexed documents, chunk count, documents needing re-indexing, search model and reranker |
| `DELETE` | `/documents/{source_id}` | Delete a document and its chunks |
| `GET` | `/providers` | Answer models, whether each is available, and why not |
| `POST` | `/ask` | `{"question", "top_k", "provider", "rerank", "generate_answer"}` → answer, sources (with `score` and `rerank_score`), whether they were reranked, removed citations |
| `GET` | `/health` | Status, chunk count, search model and reranker |

## Testing

The tests use a fake search model, a fake reranker, a fake answer model and a temporary data folder. They need no downloads, API keys or GPU, and never touch your `data/` folder.

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
| `tests/test_providers.py` | Claude, ChatGPT and Gemini requests (real SDKs against a local mock server), availability checks, gpt-oss output parsing |
| `tests/test_evaluation_scoring.py` | The evaluation script's grading rules |

The Claude, ChatGPT and Gemini tests are skipped when their SDK isn't installed.

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

- **"Cannot reach the API":** start the backend (step 4) before the UI, and check `AFRISEARCH_API_URL`.
- **A model is missing from the picker:** open **Other models** for the reason. Usually a key isn't set in the terminal running the API, or there's no GPU.
- **"No passages were similar enough":** rephrase the question, or lower `AFRISEARCH_MIN_SCORE`.
- **"documents were indexed with a different search model" / HTTP 409 from `/ask`:** the search model or chunk settings changed. Click **Re-index now** in the sidebar.
- **A PDF is "Not indexed: no extractable text":** it is probably scanned. OCR isn't supported yet.
- **Out of GPU memory:** set `AFRISEARCH_LOCAL_QUANTIZE=4bit`, or use gpt-oss-20b.
- **Only "Qwen 2.5 0.5B" is offered:** that's expected on a machine with no API keys and no NVIDIA GPU. Add keys (setup step 3) to enable Claude, ChatGPT or Gemini; for those, also install `anthropic`, `openai` and `google-genai` into the environment.
- **The first local answer is slow:** the model loads on the first question. Later questions are much faster.
- **The first search is slow:** the search model and reranker load on first use (about 10 s on a laptop CPU, plus the download the very first time). Set `AFRISEARCH_RERANKER=off` if you don't want the reranker.

## Notes and limitations

- Only PDF and TXT are supported. Scanned PDFs need OCR, which isn't supported yet.
- Documents are stored locally in `data/uploads/`. Don't upload private or sensitive documents unless you control the machine and understand the risks.
- Generated answers and citations can be wrong, especially from the small local model. Always check the source passages.
- The app is for local development, not public deployment. Before exposing it to the internet, add authentication, upload quotas, file-content validation, rate limits, secure configuration and stronger storage controls.
- The simple NumPy vector index is fine for small collections. Replace it with a vector database for large ones.
- Local models load the first time you ask a question with them, so uploading, indexing and searching never download them.
