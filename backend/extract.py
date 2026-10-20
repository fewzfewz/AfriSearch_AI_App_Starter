"""Reading text from PDF, Office (Word, Excel, PowerPoint), text, HTML and image files, with OCR for scans."""
from __future__ import annotations

import os
from html.parser import HTMLParser
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


class _VisibleText(HTMLParser):
    """Collects the text a reader would see in an HTML page (no scripts or styles)."""

    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "td", "th"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self.hidden += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self.hidden:
            self.hidden -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def html_text(markup: str) -> str:
    parser = _VisibleText()
    parser.feed(markup)
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    return "\n".join(line for line in lines if line)


def _office(module: str, package: str):
    try:
        return __import__(module)
    except ImportError as exc:
        raise RuntimeError(f"Install the '{package}' package to read this file type.") from exc


def extract_office(path: Path) -> list[tuple[int | None, str]]:
    """(page, text) pairs from Word, Excel and PowerPoint files; slides count as pages."""
    suffix = path.suffix.lower()
    if suffix == ".docx":
        docx = _office("docx", "python-docx")
        document = docx.Document(str(path))
        blocks = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
        text = "\n".join(block.strip() for block in blocks if block.strip())
        return [(None, text)] if text else []
    if suffix == ".xlsx":
        openpyxl = _office("openpyxl", "openpyxl")
        workbook = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        sheets = []
        try:
            for sheet in workbook.worksheets:
                rows = [" | ".join("" if v is None else str(v) for v in row).strip(" |")
                        for row in sheet.iter_rows(values_only=True)]
                rows = [row for row in rows if row]
                if rows:
                    # Each row ends like a sentence, so chunks break between rows.
                    sheets.append(f"Sheet: {sheet.title}.\n" + "\n".join(f"{row}." for row in rows))
        finally:
            workbook.close()
        text = "\n\n".join(sheets)
        return [(None, text)] if text else []
    if suffix == ".pptx":
        pptx = _office("pptx", "python-pptx")
        presentation = pptx.Presentation(str(path))
        pages = []
        for number, slide in enumerate(presentation.slides, start=1):
            texts = [shape.text_frame.text for shape in slide.shapes if shape.has_text_frame and shape.text_frame.text.strip()]
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                texts.append(slide.notes_slide.notes_text_frame.text)
            text = "\n".join(t.strip() for t in texts)
            if text:
                pages.append((number, text))
        return pages
    raise ValueError(f"Unsupported file type {suffix}.")


def extract_file(
    path: Path, on_page: PageCallback | None = None,
) -> tuple[list[tuple[int | None, str]], set[int | None]]:
    """Return (page, text) pairs and the pages whose text came from OCR.

    Page is None for TXT files and images. PDF pages without a usable text layer
    (scans) and image files are read with OCR; raises OcrUnavailable if they need
    it and it isn't installed.
    """
    suffix = path.suffix.lower()
    if suffix in config.TEXT_EXTENSIONS:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if suffix in (".html", ".htm"):
            text = html_text(text)
        return ([(None, text)] if text else []), set()
    if suffix in config.OFFICE_EXTENSIONS:
        return extract_office(path), set()
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
    raise ValueError("Unsupported file type.")
