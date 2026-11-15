"""Turning retrieved passages into a cited answer."""
from __future__ import annotations

import re
from typing import Any

from backend import llm, models
from backend.text import format_pages, is_ethiopic

NO_SOURCES_ANSWER = (
    "The indexed documents do not contain passages relevant enough to answer this question."
)
NOT_COVERED_ANSWER = (
    "The documents don't seem to cover this question. The closest passages are listed below in case they help."
)
# The same two messages in the languages we can recognise reliably.
# TODO(review): have native speakers check the Amharic and Swahili wording.
CANNED = {
    "no_sources": {
        "en": NO_SOURCES_ANSWER,
        "am": "በተጫኑት ሰነዶች ውስጥ ይህን ጥያቄ ለመመለስ በቂ ተዛማጅ ክፍሎች አልተገኙም።",
        "sw": "Nyaraka zilizopo hazina vifungu vinavyohusiana vya kutosha kujibu swali hili.",
    },
    "not_covered": {
        "en": NOT_COVERED_ANSWER,
        "am": "ሰነዶችዎ ይህን ጥያቄ የሚመልሱ አይመስሉም። በጣም ቅርብ የሆኑት ክፍሎች ከታች ተዘርዝረዋል።",
        "sw": "Inaonekana nyaraka zako hazijibu swali hili. Vifungu vinavyokaribiana zaidi viko hapa chini, huenda vikasaidia.",
    },
}
# Frequent Swahili question and function words; two or more mark a Swahili question.
SWAHILI_WORDS = {"je", "ni", "nini", "gani", "ngapi", "vipi", "nani", "wapi", "lini", "kwa", "wa", "ya", "za",
                 "kuna", "hii", "hiyo", "katika", "kama", "na", "kwenye", "mimi", "yangu", "nifanye"}


def question_language(question: str) -> str:
    """'am', 'sw' or 'en' (everything else), for the canned messages."""
    if is_ethiopic(question):
        return "am"
    words = re.findall(r"[a-z]+", question.lower())
    return "sw" if sum(word in SWAHILI_WORDS for word in words) >= 2 else "en"


def canned(kind: str, question: str) -> str:
    return CANNED[kind][question_language(question)]


SYSTEM_PROMPT = "Be accurate, concise, and grounded in provided evidence."
# How much of the conversation a follow-up question sees.
HISTORY_TURNS = 2
HISTORY_CHARS = 600
# Questions this short in a chat are treated as follow-ups ("and the SB-500?") and
# searched together with the previous question.
FOLLOW_UP_WORDS = 8


def is_covered(sources: list[dict[str, Any]]) -> bool:
    """Whether the passages plausibly answer the question (see models.MIN_RERANK_SCORE)."""
    if not sources:
        return False
    best = sources[0].get("rerank_score")
    return best is None or best >= models.MIN_RERANK_SCORE


def focus(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop reranked passages far below the best one (see models.RERANK_GAP)."""
    if not sources or sources[0].get("rerank_score") is None:
        return sources
    floor = sources[0]["rerank_score"] - models.RERANK_GAP
    return [item for item in sources if item["rerank_score"] >= floor]


def search_query(question: str, history: list[dict[str, str]]) -> str:
    """A short question together with the previous one, for follow-ups that need context."""
    previous = [turn["question"] for turn in history if turn.get("question")]
    if previous and len(question.split()) <= FOLLOW_UP_WORDS:
        return f"{previous[-1]} {question}"
    return question


def language_instruction(question: str) -> str:
    if is_ethiopic(question):
        return "The question is written in Amharic (Ge'ez script). Write the answer in Amharic."
    return "Write the answer in the same language as the question."


def build_prompt(question: str, sources: list[dict[str, Any]], history: list[dict[str, str]] | None = None) -> str:
    source_blocks = []
    for i, item in enumerate(sources, start=1):
        location = format_pages(item.get("page"), item.get("page_end"), prefix=", ")
        source_blocks.append(f"[S{i}] (from {item['source_name']}{location}): {item['text']}")
    evidence = "\n\n".join(source_blocks)

    conversation = ""
    if history:
        turns = [f"Q: {turn['question']}\nA: {turn['answer'][:HISTORY_CHARS]}"
                 for turn in history[-HISTORY_TURNS:] if turn.get("answer")]
        if turns:
            conversation = ("EARLIER IN THIS CONVERSATION (context only; cite only the passages):\n"
                            + "\n\n".join(turns) + "\n\n")

    return (
        "You are AfriSearch, a careful document research assistant.\n"
        "Answer using only the source passages. Cite supported claims with labels such as [S1]. "
        "If the evidence does not answer the question, clearly say that the available documents "
        "do not provide enough information. Do not invent facts, numbers, or citations.\n\n"
        f"{conversation}SOURCE PASSAGES:\n{evidence}\n\nQUESTION: {question}\n\n"
        f"{language_instruction(question)} "
        # Small models otherwise tend to echo a source header instead of answering.
        "Write the answer in full sentences, each followed by the label of the passage "
        'that supports it, e.g. "... once a year [S1]."'
    )


def generate_answer(
    question: str, sources: list[dict[str, Any]], provider: str, history: list[dict[str, str]] | None = None,
    usage: llm.Usage | None = None, model: str | None = None, api_key: str | None = None,
) -> str:
    if not sources:
        return canned("no_sources", question)
    if not is_covered(sources):
        return canned("not_covered", question)
    return llm.generate(provider, SYSTEM_PROMPT, build_prompt(question, sources, history), usage, model=model, api_key=api_key)


def source_payload(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "label": f"S{i}",
            "source_id": item["source_id"],
            "source_name": item["source_name"],
            "page": item["page"],
            "page_end": item.get("page_end", item["page"]),
            "score": round(item["score"], 4),
            "rerank_score": round(item["rerank_score"], 4) if "rerank_score" in item else None,
            "ocr": item.get("ocr", False),
            "text": item["text"],
        }
        for i, item in enumerate(sources, start=1)
    ]


GENERIC_HEADINGS = {
    "guide", "overview", "introduction", "sample", "example", "note", "table",
    "page", "sheet", "part", "chapter", "section", "background", "summary",
    "conclusion", "general", "about", "tips", "details", "info",
}


def clean_doc_title(name: str) -> str:
    base = name.split("/")[-1]
    base = re.sub(r"^[0-9a-f]{32}_", "", base)
    base = re.sub(r"\.[^.]+$", "", base)
    return base.replace("_", " ").replace("-", " ").strip()


def generate_suggestions(
    question: str,
    sources: list[dict[str, Any]],
    answer: str | None = None,
    covered: bool = True,
) -> list[str]:
    """Generate 2-3 relevant follow-up questions in the question's language."""
    lang = question_language(question)

    if not sources:
        if lang == "am":
            return [
                "በሰነዶቹ ውስጥ ምን ዋና ርዕሶች አሉ?",
                "የተጫኑትን ሰነዶች ጠቅለል አድርግልኝ።",
                "ሰነዶቼ ምን ምን መመሪያዎችን ይዘዋል?",
            ]
        if lang == "sw":
            return [
                "Je, nyaraka zangu zinahusu mada gani?",
                "Fanya muhtasari wa nyaraka zilizopo.",
                "Ni miongozo gani inayopatikana?",
            ]
        return [
            "What topics are covered in my documents?",
            "Summarize the available documents.",
            "What key guidelines are available?",
        ]

    doc_names = list(dict.fromkeys(s.get("source_name", "") for s in sources if s.get("source_name")))
    clean_docs = [clean_doc_title(d) for d in doc_names if d]

    if not covered:
        top_doc = clean_docs[0] if clean_docs else "the documents"
        if lang == "am":
            return [
                f"{top_doc} ስለ ምን ይናገራል?",
                f"በ{top_doc} ውስጥ ምን ዋና ነጥቦች አሉ?",
                "ስለ ምን ዓይነት ርዕሶች መጠየቅ እችላለሁ?",
            ]
        if lang == "sw":
            return [
                f"{top_doc} inahusu nini?",
                f"Ni mambo gani muhimu katika {top_doc}?",
                "Naweza kuuliza kuhusu mada gani?",
            ]
        return [
            f"What does {top_doc} cover?",
            f"What are the key points in {top_doc}?",
            "What topics can I ask about?",
        ]

    if lang == "am":
        q_tokens = set(re.findall(r"[ሀ-፿]+", question))
    else:
        q_tokens = set(re.findall(r"[a-z0-9]+", question.lower()))

    topics: list[str] = []
    seen: set[str] = set()

    for s in sources:
        text = s.get("text", "")
        if lang == "am":
            found = re.findall(r"(?:^|\n)([ሀ-፿\s]{2,20})(?:።|፡)\s*", text)
        else:
            found = re.findall(r"(?:^|\n)([A-Z][A-Za-z0-9 /&-]{2,30})[.:]\s", text)
            found.extend(re.findall(r"\*\*([A-Za-z0-9 /&-]{2,30})\*\*", text))

        for cand in found:
            cand = cand.strip()
            cand_key = cand.lower()
            if not cand or cand_key in GENERIC_HEADINGS or cand_key in seen:
                continue
            cand_tokens = set(re.findall(r"[ሀ-፿]+" if lang == "am" else r"[a-z0-9]+", cand_key))
            if cand_tokens and cand_tokens.issubset(q_tokens):
                continue
            seen.add(cand_key)
            topics.append(cand)
            if len(topics) >= 4:
                break
        if len(topics) >= 4:
            break

    suggestions: list[str] = []

    if lang == "am":
        for t in topics[:2]:
            suggestions.append(f"ስለ {t} ምን ይመክራል?")
        if len(clean_docs) > 1 and len(suggestions) < 3:
            suggestions.append(f"በ{clean_docs[1]} ውስጥ ስለዚህ ጉዳይ ምን ተብሏል?")
        fallbacks = [
            "ተያያዥ ጥንቃቄዎች ወይም ማስጠንቀቂያዎች ምንድን ናቸው?",
            "ዋና ዋና መመሪያዎች እና ሂደቶች ምንድን ናቸው?",
            "ስለ አፈጻጸሙ ተጨማሪ ማብራሪያ አለ?",
        ]
        for fb in fallbacks:
            if len(suggestions) >= 3:
                break
            if fb not in suggestions:
                suggestions.append(fb)
    elif lang == "sw":
        for t in topics[:2]:
            suggestions.append(f"Kuhusu {t.lower()}, kuna mapendekezo gani?")
        if len(clean_docs) > 1 and len(suggestions) < 3:
            suggestions.append(f"{clean_docs[1]} inasemaje kuhusu jambo hili?")
        fallbacks = [
            "Je, kuna tahadhari au maonyo yoyote muhimu?",
            "Ni hatua gani muhimu zinazopendekezwa?",
            "Ni mambo gani mengine yanayopaswa kuzingatiwa?",
        ]
        for fb in fallbacks:
            if len(suggestions) >= 3:
                break
            if fb not in suggestions:
                suggestions.append(fb)
    else:
        for t in topics[:2]:
            suggestions.append(f"What does it recommend about {t.lower()}?")
        if len(clean_docs) > 1 and len(suggestions) < 3:
            suggestions.append(f"What does {clean_docs[1]} say about this?")
        fallbacks = [
            "What are the main precautions or warnings mentioned?",
            "Are there specific troubleshooting steps?",
            "What are the key requirements or procedures?",
        ]
        for fb in fallbacks:
            if len(suggestions) >= 3:
                break
            if fb not in suggestions:
                suggestions.append(fb)

    return suggestions[:3]


QUESTION_STARTERS = [
    r"^(?:can\s+you\s+tell\s+me\s+(?:about\s+)?|tell\s+me\s+about\s+|please\s+explain\s+|i\s+want\s+to\s+know\s+)",
    r"^(?:how\s+(?:often|many|much|long|far|high|can|do|should|would|to))\s+(?:i\s+|we\s+|a\s+|the\s+)?",
    r"^(?:what\s+(?:is|are|does|do|share|percentage|level|capacity|duration))\s+(?:the\s+|of\s+|a\s+)?",
    r"^(?:which\s+(?:direction|one|type|model|kind))\s+(?:should|is|are|do)?\s*",
    r"^(?:why\s+(?:do|does|is|are))\s+",
    r"^(?:should\s+i|can\s+i|is\s+it\s+(?:safe|better|recommended)\s+to)\s+",
    r"^(?:what\s+should\s+i\s+do\s+(?:if|when)?)\s*",
    r"^(?:to\s+what\s+)",
    r"^(?:does\s+)",
    r"^(?:of\s+|for\s+|to\s+|about\s+|in\s+)",
    r"^(?:je,\s+|kwa nini\s+|wapi\s+|lini\s+|vipi\s+|ninapaswa\s+)",
]


def generate_chat_title(question: str, answer: str | None = None) -> str:
    """Generate a clean, concise 3-6 word chat title from the first answer and question."""
    ans = re.sub(r"\[S\d+(?:,\s*S\d+)*\]", "", answer or "").strip()
    canned_markers = [
        "do not contain passages", "not covered", "don't seem to cover",
        "አልተገኙም", "hazina vifungu", "ይመልሱ አይመስሉም",
    ]
    is_canned = any(m in ans.lower() for m in canned_markers)

    first_sentence = ""
    if ans and not is_canned:
        sentences = re.split(r"(?:(?<=[.!?።፧])|(?<=፡፡))\s+", ans)
        if sentences:
            s0 = sentences[0].strip().rstrip(".!?።")
            s0 = re.sub(r"^(?:according to [^,]+,\s*|based on [^,]+,\s*|the passages? states? (?:that )?)", "", s0, flags=re.I)
            if 8 <= len(s0) <= 60:
                first_sentence = s0

    q = question.strip().rstrip("?.! ፧።")
    q_clean = q
    for pat in QUESTION_STARTERS:
        q_clean = re.sub(pat, "", q_clean, flags=re.I)

    # Amharic question patterns
    q_clean = re.sub(r"^(?:ስለ\s+)?(?:ምን\s+|እንዴት\s+|ለምን\s+)?", "", q_clean)
    q_clean = re.sub(r"(?:ምን ያህል|ለምን ያህል ጊዜ|ስንት)(?:\s+መሆን አለበት|\s+መድረቅ አለበት)?", "", q_clean)

    candidate = first_sentence if first_sentence and len(first_sentence) <= 45 else (q_clean or q)
    candidate = re.sub(r"^(?:of\s+|for\s+|to\s+|about\s+|in\s+)", "", candidate.strip(), flags=re.I)
    candidate = candidate.strip()

    if candidate:
        candidate = candidate[0].upper() + candidate[1:]

    if len(candidate) > 46:
        words = candidate.split()
        res = ""
        for w in words:
            if len(res) + len(w) + 1 <= 46:
                res = f"{res} {w}".strip()
            else:
                break
        candidate = res or candidate[:46]

    return candidate.rstrip(":,.- ") or q[:45]


