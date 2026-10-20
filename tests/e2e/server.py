"""The real app with fake models, for the browser tests in web/e2e (no downloads, keys or GPU).

    python tests/e2e/server.py [port]
"""
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ["AFRISEARCH_DATA_DIR"] = tempfile.mkdtemp(prefix="afrisearch-e2e-")
os.environ["AFRISEARCH_PRELOAD_MODELS"] = "0"
os.environ["AFRISEARCH_RERANKER"] = "off"
os.environ["AFRISEARCH_AUTH"] = "none"
sys.path[:0] = [str(HERE.parents[1]), str(HERE.parent)]

import uvicorn  # noqa: E402

from backend import extract, llm, main, models  # noqa: E402
from conftest import FakeEmbedder, FakeModel  # noqa: E402

models.embedder = FakeEmbedder()
models.MIN_SCORE = 0.2  # the fake embedder's scale
extract.ocr_status = lambda: ([], "OCR is off in the browser tests.")
fake = FakeModel()
llm.PROVIDERS = {"fake": llm.Provider("fake", "Test model (local, runs on CPU)", "local", "fake-1", fake.check, fake.generate)}
llm.DEFAULT_PROVIDER = "fake"

if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8799, log_level="warning")
