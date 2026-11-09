"""Word, Excel, PowerPoint, HTML, Markdown and CSV documents."""
import io

import pytest

from backend import extract
from conftest import upload

docx = pytest.importorskip("docx")
openpyxl = pytest.importorskip("openpyxl")
pptx = pytest.importorskip("pptx")


def word_file() -> bytes:
    document = docx.Document()
    document.add_heading("Cooperative savings policy", level=1)
    document.add_paragraph("Members may borrow up to three times their savings.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Loan term", "Interest"
    table.cell(1, 0).text, table.cell(1, 1).text = "12 months", "1.5 percent per month"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def excel_file() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Prices"
    sheet.append(["Crop", "Price per kg (ETB)"])
    sheet.append(["Teff", 95])
    sheet.append(["Maize", 32])
    workbook.create_sheet("Empty")
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def slides_file() -> bytes:
    presentation = pptx.Presentation()
    for title, body, notes in [("Welcome", "Training for extension workers.", ""),
                               ("Storage", "Dry maize to 13 percent moisture.", "Show the salt test.")]:
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def test_office_documents_are_read(tmp_path):
    (tmp_path / "policy.docx").write_bytes(word_file())
    pages, ocr = extract.extract_file(tmp_path / "policy.docx")
    assert ocr == set()
    assert "borrow up to three times" in pages[0][1] and "12 months | 1.5 percent per month" in pages[0][1]

    (tmp_path / "prices.xlsx").write_bytes(excel_file())
    text = extract.extract_file(tmp_path / "prices.xlsx")[0][0][1]
    assert "Sheet: Prices." in text and "| Teff | 95 |" in text and "Empty" not in text
    assert "| --- | --- |" in text

    (tmp_path / "training.pptx").write_bytes(slides_file())
    pages = extract.extract_file(tmp_path / "training.pptx")[0]
    assert [page for page, _ in pages] == [1, 2]  # slides are cited like pages
    assert "13 percent moisture" in pages[1][1] and "salt test" in pages[1][1]  # speaker notes too


def test_html_markdown_and_csv(tmp_path):
    (tmp_path / "page.html").write_text(
        "<html><head><style>p{color:red}</style><script>alert('x')</script></head>"
        "<body><h1>Clinic hours</h1><p>Open <b>8 to 5</b>, Monday to Friday.</p></body></html>")
    text = extract.extract_file(tmp_path / "page.html")[0][0][1]
    assert text == "Clinic hours\nOpen 8 to 5, Monday to Friday."
    (tmp_path / "notes.md").write_text("# Notes\n\n- Boil water for one minute.")
    assert "Boil water" in extract.extract_file(tmp_path / "notes.md")[0][0][1]
    (tmp_path / "data.csv").write_text("crop,price\nteff,95\n")
    csv_text = extract.extract_file(tmp_path / "data.csv")[0][0][1]
    assert "| teff | 95 |" in csv_text
    assert "| --- | --- |" in csv_text


def test_markdown_table_chunking_preserves_headers():
    from backend.text import chunk_document, split_sentences

    # Create a 40-row financial table
    header = "| Region | Target (M) | Actual (M) | Performance Notes |"
    sep = "| --- | --- | --- | --- |"
    rows = [
        f"| Region {i} | ${10.0 + i}M | ${11.5 + i}M | Met quarterly target with Dr. Smith. |"
        for i in range(1, 41)
    ]
    table_text = "\n".join([header, sep] + rows)

    # 1. Test split_sentences preserves rows containing periods mid-cell
    sentences = split_sentences(table_text)
    assert len(sentences) == 42
    assert sentences[0] == header
    assert sentences[1] == sep
    assert sentences[2] == rows[0]  # Not split by "Dr. Smith." or "10.0"

    # 2. Test chunk_document preserves table header across chunks
    chunks = chunk_document([(1, table_text)], chunk_size=40, overlap=10)
    assert len(chunks) > 1

    # Every chunk should have the header row and separator at the top
    for first_p, last_p, chunk_text in chunks:
        assert header in chunk_text, f"Chunk missing table header:\n{chunk_text}"
        assert sep in chunk_text, f"Chunk missing table separator:\n{chunk_text}"


def test_upload_index_and_search_office_files(client, fake_model):
    result = upload(client, ("policy.docx", word_file()), ("prices.xlsx", excel_file()), ("training.pptx", slides_file()))
    assert len(result["saved"]) == 3
    indexed = client.post("/documents/index").json()
    assert sorted(indexed["new_documents"]) == ["policy.docx", "prices.xlsx", "training.pptx"]
    source = client.post("/ask", json={"question": "How dry should maize be before storing it moisture?",
                                       "generate_answer": False}).json()["sources"][0]
    assert source["source_name"] == "training.pptx"
    assert source["page"] <= 2 <= source["page_end"]  # short slides share a passage covering slide 2


def test_old_office_formats_are_rejected_with_advice(client):
    errors = upload(client, ("old.docx", b"\xd0\xcf\x11\xe0 old binary format"), ("old.doc", b"whatever"))["errors"]
    messages = {e["filename"]: e["error"] for e in errors}
    assert "Save it as .docx" in messages["old.docx"]
    assert "Save older .doc" in messages["old.doc"]
