# One image for both the API and the UI (docker-compose.yml picks the command).
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
COPY frontend frontend
COPY .streamlit .streamlit

# Run as a normal user; documents and model weights live in volumes.
RUN useradd --create-home --uid 1000 afrisearch \
    && mkdir -p /app/data/uploads /models \
    && chown -R afrisearch /app/data /models
USER afrisearch

EXPOSE 8000 8501
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
