"""Reading text from PDF, TXT and image files, with OCR for scans and photos."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from pypdf import PdfReader

from backend import config

# OCR (Tesseract) reads scanned PDF pages and photos of documents. Languages are
# Tesseract codes joined with "+"; those not installed are skipped.
OCR_LANGUAGES = os.getenv("AFRISEARCH_OCR_LANGS", "eng+amh+swa")
OCR_DPI = 300
# PDF pages with less extractable text than this are treated as scanned images.
MIN_PAGE_CHARS = 25

# Called as on_page(page_number, page_count, used_ocr) while a PDF is read.
PageCallback = Callable[[int, int, bool], None]


class OcrUnavailable(RuntimeError):
    """A file needs OCR but Tesseract (or its Python packages) is not installed."""


def ocr_status() -> tuple[list[str], str | None]:
    """(languages OCR will use, why OCR is unavailable or None)."""
    try:
        import pytesseract

        installed = set(pytesseract.get_languages(config=""))
    except ImportError:
        return [], "Install the 'pytesseract' and 'pypdfium2' packages."
    except Exception:  # TesseractNotFoundError and friends
        return [], "Install Tesseract OCR (for example: sudo apt install tesseract-ocr tesseract-ocr-amh)."
    wanted = [lang for lang in OCR_LANGUAGES.split("+") if lang]
    languages = [lang for lang in wanted if lang in installed] or (["eng"] if "eng" in installed else [])
    if not languages:
        return [], f"No Tesseract language data for {OCR_LANGUAGES} is installed."
    return languages, None


def ocr_image(image: Any) -> str:
    """Read the text in a PIL image with Tesseract."""
    languages, reason = ocr_status()
    if reason:
        raise OcrUnavailable(reason)
    import pytesseract

    return pytesseract.image_to_string(image.convert("L"), lang="+".join(languages)).strip()


def ocr_pdf_page(path: Path, page_number: int) -> str:
    try:
        import pypdfium2
    except ImportError as exc:
        raise OcrUnavailable("Install the 'pypdfium2' package.") from exc
    pdf = pypdfium2.PdfDocument(str(path))
    try:
        image = pdf[page_number - 1].render(scale=OCR_DPI / 72).to_pil()
    finally:
        pdf.close()
    return ocr_image(image)


def extract_file(
    path: Path, on_page: PageCallback | None = None,
) -> tuple[list[tuple[int | None, str]], set[int | None]]:
    """Return (page, text) pairs and the pages whose text came from OCR.

    Page is None for TXT files and images. PDF pages without a usable text layer
    (scans) and image files are read with OCR; raises OcrUnavailable if they need
    it and it isn't installed.
    """
    suffix = path.suffix.lower()
    if suffix == ".txt":
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return ([(None, text)] if text else []), set()
    if suffix in config.IMAGE_EXTENSIONS:
        from PIL import Image

        with Image.open(path) as image:
            text = ocr_image(image)
        return ([(None, text)] if text else []), {None}
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages, ocr_pages = [], set()
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            used_ocr = False
            if len(text) < MIN_PAGE_CHARS:
                scanned = ocr_pdf_page(path, page_number)
                if len(scanned) > len(text):
                    text, used_ocr = scanned, True
                    ocr_pages.add(page_number)
            if text:
                pages.append((page_number, text))
            if on_page:
                on_page(page_number, len(reader.pages), used_ocr)
        return pages, ocr_pages
    raise ValueError("Only PDF, TXT and image files are supported.")
