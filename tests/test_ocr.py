"""OCR: scanned PDF pages and images are read with Tesseract (faked here)."""
import io

import pytest
from PIL import Image

from backend import extract, store
from conftest import SOLAR_GUIDE, upload
from test_documents import blank_pdf

OCR_TEXT = "Solar panels should be cleaned every month to remove dust. This text came from a scan."


def text_pdf(*pages: str) -> bytes:
    """A PDF with one page per string; an empty string makes a page with no text layer."""
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{' '.join(f'{4 + 2 * i} 0 R' for i in range(len(pages)))}] "
           f"/Count {len(pages)} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 20 700 Td ({text}) Tj ET" if text else ""
        objects[4 + 2 * i] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                              f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>")
        objects[5 + 2 * i] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offsets = b"%PDF-1.4\n", {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n{objects[number]}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offsets[n]:010d} 00000 n \n".encode() for n in sorted(objects))
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_scanned_pdf_is_read_with_ocr(client, app_env, fake_model, monkeypatch):
    calls = []
    monkeypatch.setattr(extract, "ocr_status", lambda: (["eng"], None))
    monkeypatch.setattr(extract, "ocr_image", lambda image: calls.append(image.size) or OCR_TEXT)
    upload(client, ("scan.pdf", blank_pdf()))
    result = client.post("/documents/index").json()
    assert result["failed"] == []
    assert result["new_documents"] == ["scan.pdf"]
    assert len(calls) == 1
    width, _ = calls[0]
    assert width == pytest.approx(100 * extract.OCR_DPI / 72, abs=2)  # page rendered at OCR_DPI

    documents = client.get("/documents").json()["documents"]
    assert documents[0]["ocr"] is True
    source = client.post("/ask", json={"question": "How often should solar panels be cleaned?"}).json()["sources"][0]
    assert source["ocr"] is True
    assert source["page"] == 1
    assert "came from a scan" in source["text"]


def test_pages_with_a_text_layer_skip_ocr(app_env, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(extract, "ocr_status", lambda: (["eng"], None))
    monkeypatch.setattr(extract, "ocr_image", lambda image: calls.append(image.size) or OCR_TEXT)
    path = tmp_path / "mixed.pdf"
    path.write_bytes(text_pdf("Inverters should be inspected once a year by a technician.", ""))
    pages, ocr_pages = extract.extract_file(path)
    assert ocr_pages == {2}
    assert len(calls) == 1
    assert pages[0] == (1, "Inverters should be inspected once a year by a technician.")
    assert pages[1] == (2, OCR_TEXT)

    chunks = store.create_chunks("id", "mixed.pdf", pages, ocr_pages)
    assert [(c["page"], c["page_end"], c["ocr"]) for c in chunks] == [(1, 2, True)]
    assert store.create_chunks("id", "mixed.pdf", pages[:1], ocr_pages)[0]["ocr"] is False


def test_images_are_read_with_ocr(client, app_env, monkeypatch):
    monkeypatch.setattr(extract, "ocr_status", lambda: (["eng"], None))
    monkeypatch.setattr(extract, "ocr_image", lambda image: OCR_TEXT)
    saved = upload(client, ("photo.png", png_bytes()))["saved"]
    assert [item["filename"] for item in saved] == ["photo.png"]
    result = client.post("/documents/index").json()
    assert result["new_documents"] == ["photo.png"]
    chunk = app_env.store.chunks[0]
    assert (chunk["page"], chunk["ocr"]) == (None, True)


def test_without_ocr_scans_and_images_are_reported(client):
    upload(client, ("guide.txt", SOLAR_GUIDE), ("scan.pdf", blank_pdf()), ("photo.jpg", png_bytes()))
    result = client.post("/documents/index").json()
    failed = {item["filename"]: item["error"] for item in result["failed"]}
    assert "scanned PDF and needs OCR" in failed["scan.pdf"]
    assert "This image needs OCR" in failed["photo.jpg"]
    assert "Tesseract" in failed["photo.jpg"]
    assert result["new_documents"] == ["guide.txt"]


def test_blank_scans_are_reported(client, app_env, monkeypatch):
    monkeypatch.setattr(extract, "ocr_status", lambda: (["eng"], None))
    monkeypatch.setattr(extract, "ocr_image", lambda image: "")
    upload(client, ("blank.pdf", blank_pdf()))
    failed = client.post("/documents/index").json()["failed"]
    assert "No text found, even with OCR" in failed[0]["error"]


def test_unsupported_files_are_rejected(client):
    errors = upload(client, ("notes.docx", b"PK\x03\x04"))["errors"]
    assert "images" in errors[0]["error"]


def test_health_reports_ocr_status(client):
    assert client.get("/health").json()["ocr"] == {
        "available": False, "languages": [], "reason": "Tesseract is not installed (test).",
    }


class FakeTesseract:
    """Stands in for pytesseract.get_languages."""

    def __init__(self, languages=None, error=None):
        self.languages, self.error = languages, error

    def __call__(self, config=""):
        if self.error:
            raise self.error
        return self.languages


@pytest.mark.parametrize("installed, wanted, expected", [
    (["eng", "amh", "osd"], "eng+amh+swa", ["eng", "amh"]),  # missing languages are skipped
    (["eng", "osd"], "amh", ["eng"]),  # falls back to English
])
def test_ocr_uses_installed_languages(monkeypatch, installed, wanted, expected):
    import pytesseract


    monkeypatch.setattr(pytesseract, "get_languages", FakeTesseract(installed))
    monkeypatch.setattr(extract, "OCR_LANGUAGES", wanted)
    assert extract.ocr_status() == (expected, None)


def test_ocr_reports_missing_tesseract(monkeypatch):
    import pytesseract


    monkeypatch.setattr(pytesseract, "get_languages",
                        FakeTesseract(error=pytesseract.TesseractNotFoundError()))
    languages, reason = extract.ocr_status()
    assert languages == []
    assert "Install Tesseract" in reason
