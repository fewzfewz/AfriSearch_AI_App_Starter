# AfriSearch AI — Web App Starter

A local app for asking questions about your own documents. Upload PDF or TXT files, and AfriSearch finds the most relevant passages and writes an answer that cites them. It turns the Notebook 5 pipeline into a web app.

**Features**
- Upload PDF and TXT documents; exact duplicates are rejected
- Extract text with page numbers, split it into sentence-aware chunks that can span pages, and embed them
- Index only new files (a full rebuild is optional), and delete documents from the UI
- Semantic search with a relevance cutoff, so unrelated passages are never passed to the model
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
data/             uploads/, index.json, embeddings.npy, manifest.json (created at runtime)
```

- **Search model:** Sentence Transformers `all-MiniLM-L6-v2`
- **Answer models:** see [Answer models](#answer-models)
- **Storage:** local files under `data/` (a starter implementation, not production storage)

## Requirements

- Python 3.10+
- Internet access on the first run, to install packages and download model weights
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
3. **Ask:** type a question and press **Ask AfriSearch** or **Ctrl+Enter**. **Passages to retrieve** sets how many passages the model sees.
4. **Check the answer:** citations such as **S1** are highlighted. Under **Sources**, each passage shows its file, pages and relevance. Always check important claims against them.
5. **Earlier answers:** your last 10 answers stay available in the session. Click **Show** to bring one back.

**Advanced → Rebuild full index** processes every document again. This is only needed after changing the search model or chunk settings, and those changes are also detected automatically.

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

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `AFRISEARCH_API_URL` | `http://127.0.0.1:8000` | Where the UI finds the API |
| `AFRISEARCH_DEFAULT_PROVIDER` | first available | Pre-selected answer model |
| `AFRISEARCH_EMBEDDER` | `sentence-transformers/all-MiniLM-L6-v2` | Search model (changing it re-indexes automatically) |
| `AFRISEARCH_MIN_SCORE` | `0.2` | Passages less similar than this are ignored |
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
| `GET` | `/documents` | Indexed documents and chunk count |
| `DELETE` | `/documents/{source_id}` | Delete a document and its chunks |
| `GET` | `/providers` | Answer models, whether each is available, and why not |
| `POST` | `/ask` | `{"question", "top_k", "provider"}` → answer, sources, removed citations |
| `GET` | `/health` | Status and chunk count |

## Testing

The tests use a fake search model, a fake answer model and a temporary data folder. They need no downloads, API keys or GPU, and never touch your `data/` folder.

```bash
pip install -r requirements-dev.txt   # adds pytest and httpx
pytest -q
```

| File | Covers |
|---|---|
| `tests/test_text_processing.py` | Chunking, citation cleanup, page formatting |
| `tests/test_documents.py` | Upload, duplicate rejection, incremental and full indexing, failed files, delete, reload from disk |
| `tests/test_ask.py` | `/ask`: cited answers, relevance cutoff, provider selection and errors |
| `tests/test_providers.py` | Claude, ChatGPT and Gemini requests (real SDKs against a local mock server), availability checks, gpt-oss output parsing |

The Claude, ChatGPT and Gemini tests are skipped when their SDK isn't installed.

## Troubleshooting

- **"Cannot reach the API":** start the backend (step 4) before the UI, and check `AFRISEARCH_API_URL`.
- **A model is missing from the picker:** open **Other models** for the reason. Usually a key isn't set in the terminal running the API, or there's no GPU.
- **"No passages were similar enough":** rephrase the question, or lower `AFRISEARCH_MIN_SCORE`.
- **A PDF is "Not indexed: no extractable text":** it is probably scanned. OCR isn't supported yet.
- **Out of GPU memory:** set `AFRISEARCH_LOCAL_QUANTIZE=4bit`, or use gpt-oss-20b.
- **Only "Qwen 2.5 0.5B" is offered:** that's expected on a machine with no API keys and no NVIDIA GPU. Add keys (setup step 3) to enable Claude, ChatGPT or Gemini; for those, also install `anthropic`, `openai` and `google-genai` into the environment.
- **The first local answer is slow:** the model loads on the first question. Later questions are much faster.

## Notes and limitations

- Only PDF and TXT are supported. Scanned PDFs need OCR, which isn't supported yet.
- Documents are stored locally in `data/uploads/`. Don't upload private or sensitive documents unless you control the machine and understand the risks.
- Generated answers and citations can be wrong, especially from the small local model. Always check the source passages.
- The app is for local development, not public deployment. Before exposing it to the internet, add authentication, upload quotas, file-content validation, rate limits, secure configuration and stronger storage controls.
- The simple NumPy vector index is fine for small collections. Replace it with a vector database for large ones.
- Local models load the first time you ask a question with them, so uploading, indexing and searching never download them.
