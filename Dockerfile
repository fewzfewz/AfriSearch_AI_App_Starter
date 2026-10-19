# Stage 1: build the web app.
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Stage 2: the API, which also serves the built web app.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models

# Tesseract OCR with English, Amharic and Swahili for scanned PDFs and photos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-amh tesseract-ocr-swa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The CPU build of PyTorch is a fraction of the size of the CUDA build.
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend backend
COPY --from=web /web/dist web/dist

# Run as a normal user; data (accounts, documents, indexes) and model weights live in volumes.
RUN useradd --create-home --uid 1000 afrisearch \
    && mkdir -p /app/data /models \
    && chown -R afrisearch /app/data /models
USER afrisearch

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
