"""Chunking, citation cleanup and page formatting (pure functions)."""
from backend.text import chunk_document, clean_citations, format_pages, split_sentences


def words(text: str) -> int:
    return len(text.split())


def test_short_pages_are_merged_and_keep_their_page_range():
    chunks = chunk_document([(1, "Short page one."), (2, "Short page two.")], chunk_size=50, overlap=10)
    assert chunks == [(1, 2, "Short page one. Short page two.")]


def test_chunks_end_on_sentence_boundaries_and_respect_size():
    text = " ".join(f"Sentence number {i} is here." for i in range(60))
    chunks = chunk_document([(1, text)], chunk_size=40, overlap=10)
    assert len(chunks) > 1
    for _, _, chunk in chunks:
        assert words(chunk) <= 40
        assert chunk.endswith(".")


def test_overlap_repeats_trailing_whole_sentences():
    # 4-word sentences: 5 fit in a 20-word chunk, and an 8-word overlap carries 2 of them.
    text = " ".join(f"Fact {i} is true." for i in range(30))
    chunks = chunk_document([(None, text)], chunk_size=20, overlap=8)
    first, second = chunks[0][2], chunks[1][2]
    assert first == " ".join(f"Fact {i} is true." for i in range(5))
    assert second.startswith("Fact 3 is true. Fact 4 is true. Fact 5 is true.")


def test_sentence_longer_than_chunk_size_is_split_by_words():
    chunks = chunk_document([(None, " ".join(["word"] * 130))], chunk_size=50, overlap=10)
    assert [words(text) for _, _, text in chunks] == [50, 50, 30]


def test_amharic_sentences_are_split_on_the_ethiopic_full_stop():
    text = " ".join(["የቡና ተክሎች በከፊል ጥላ ውስጥ በደንብ ያድጋሉ።"] * 6)  # 7 words per sentence
    chunks = chunk_document([(1, text)], chunk_size=15, overlap=0)
    assert [words(chunk) for _, _, chunk in chunks] == [14, 14, 14]  # 2 whole sentences each
    assert all(chunk.endswith("።") for _, _, chunk in chunks)


def test_double_wordspace_also_ends_amharic_sentences():
    # OCR and many keyboards write the full stop as two wordspaces (፡፡).
    assert split_sentences("ጥላ ያስፈልጋል፡፡ ፍሬ ይልቀሙ። ያድርቁ") == ["ጥላ ያስፈልጋል፡፡", "ፍሬ ይልቀሙ።", "ያድርቁ"]


def test_blank_input_produces_no_chunks():
    assert chunk_document([(1, "   "), (2, "")]) == []


def test_clean_citations_keeps_valid_labels_and_drops_invalid_ones():
    answer, removed = clean_citations("Clean monthly [S1]. Also [S9] and [S1, S5].", source_count=2)
    assert answer == "Clean monthly [S1]. Also and [S1]."
    assert removed == ["S9", "S5"]


def test_clean_citations_tidies_space_before_punctuation():
    answer, removed = clean_citations("Done [S3].", source_count=1)
    assert answer == "Done."
    assert removed == ["S3"]


def test_clean_citations_leaves_valid_answer_untouched():
    assert clean_citations("Yes [S1], and [S2].", source_count=2) == ("Yes [S1], and [S2].", [])


def test_format_pages():
    assert format_pages(None, None) == ""
    assert format_pages(3, 3) == "page 3"
    assert format_pages(3, 5, prefix=", ") == ", pages 3-5"


def test_generate_suggestions_handles_empty_and_not_covered():
    from backend.answers import generate_suggestions

    empty_en = generate_suggestions("What should I do?", [])
    assert len(empty_en) == 3
    assert any("documents" in s for s in empty_en)

    not_cov = generate_suggestions("Quantum physics?", [{"source_name": "solar_guide.txt", "text": "Panels."}], covered=False)
    assert len(not_cov) == 3
    assert any("solar guide" in s for s in not_cov)


def test_generate_suggestions_extracts_headings_in_multiple_languages():
    from backend.answers import generate_suggestions

    en_src = [{"source_name": "solar.txt", "text": "Panels. Clean dust.\n\nBatteries. Keep charged.\n\nInverter. Inspect yearly."}]
    sugs_en = generate_suggestions("How to clean solar panels?", en_src)
    assert len(sugs_en) >= 2
    assert any("batteries" in s.lower() or "inverter" in s.lower() for s in sugs_en)

    am_src = [{"source_name": "coffee.txt", "text": "ጥላ። በደንብ ያድጋሉ።\n\nለቀማ። ቀይ ፍሬ ይልቀሙ።"}]
    sugs_am = generate_suggestions("የቡና ፍሬ ማድረቅ?", am_src)
    assert len(sugs_am) >= 2
    assert any("ለቀማ" in s or "ጥላ" in s for s in sugs_am)


def test_generate_chat_title():
    from backend.answers import generate_chat_title

    t1 = generate_chat_title("What is the battery capacity of the SB-500 kit?", "The battery capacity is 307 watt-hours [S1].")
    assert "battery capacity" in t1.lower()
    assert len(t1) <= 48

    t2 = generate_chat_title("How often should solar panels be cleaned?", "Clean them every month [S1].")
    assert t2 == "Clean them every month"

    t3 = generate_chat_title("የቡና ፍሬ ለምን ያህል ጊዜ መድረቅ አለበት?", "የተለቀመውን ፍሬ ከሁለት እስከ ሶስት ሳምንት ያድርቁ።")
    assert "የተለቀመውን ፍሬ" in t3 or "የቡና ፍሬ" in t3


