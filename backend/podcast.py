"""Two-Host Conversational Audio Overview / Podcast Generator for AfriSearch.

Generates dynamic, engaging NotebookLM-style podcast discussions between two AI hosts
("Alex" and "Sam") synthesizing uploaded documents, with page citations and structured
dialogue turns for audio playback.
"""
from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from backend import compare, llm

logger = logging.getLogger("afrisearch.podcast")

TONE_INSTRUCTIONS = {
    "conversational": (
        "Upbeat, engaging, and accessible (NotebookLM style). The hosts speak naturally with conversational filler, "
        "relatable analogies, genuine reactions, and mutual enthusiasm for uncovering insights."
    ),
    "deep_dive": (
        "Technical, analytical, and rigorous. The hosts scrutinize specific data points, methodologies, architecture, "
        "and empirical metrics with scholarly depth."
    ),
    "critique": (
        "Critical, probing, and inquisitive. The hosts play devil's advocate, question underlying assumptions, "
        "highlight unaddressed risks, and debate trade-offs."
    ),
}

LENGTH_TURNS = {
    "quick": 6,     # ~2-3 minutes
    "medium": 10,   # ~4-5 minutes
    "deep": 16,     # ~7-8 minutes
}


def build_podcast_prompt(
    doc_contexts: list[dict[str, Any]],
    tone: str = "conversational",
    length: str = "medium",
) -> tuple[str, str]:
    """Build the system and user prompt for generating a realistic two-host podcast discussion."""
    target_turns = LENGTH_TURNS.get(length, 10)
    tone_desc = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["conversational"])

    doc_blocks: list[str] = []
    doc_titles: list[str] = []

    for i, ctx in enumerate(doc_contexts, start=1):
        name = ctx["source_name"]
        doc_titles.append(name)
        outline_str = "\n".join(f"  - {item['title']} (p. {item.get('page', 1)})" for item in ctx.get("outline", []))
        passages_str = "\n\n".join(
            f"  [p. {p.get('page', 1)}]: {p['text']}" for p in ctx.get("passages", [])
        )

        block = (
            f"DOCUMENT {i}: \"{name}\" (Total Pages: {ctx.get('pages', 1)})\n"
            f"Outline:\n{outline_str or '  No outline.'}\n"
            f"Key Excerpts:\n{passages_str or '  No excerpts.'}\n"
        )
        doc_blocks.append(block)

    docs_joined = "\n---\n".join(doc_blocks)
    names_joined = " and ".join(f'"{t}"' for t in doc_titles)

    system_prompt = (
        "You are the executive producer and scriptwriter for 'AfriSearch Deep Dive', an award-winning "
        "conversational tech and research podcast. You write ultra-realistic, captivating two-host audio discussions "
        "between two co-hosts: Alex and Sam."
    )

    user_prompt = (
        f"Write an engaging two-host podcast episode deep-diving into {names_joined}.\n\n"
        f"SHOW HOSTS:\n"
        "- **Alex**: Energetic, inquisitive co-host who frames the big picture, asks insightful questions, and connects ideas with real-world analogies.\n"
        "- **Sam**: Perceptive analytical co-host who brings up specific data points, page citations, nuances, and methodology details.\n\n"
        f"EPISODE TONE: {tone_desc}\n\n"
        f"TARGET LENGTH: Exactly {target_turns} dialogue turns alternating between Alex and Sam.\n\n"
        f"DOCUMENT EVIDENCE:\n{docs_joined}\n\n"
        "DIALOGUE RULES:\n"
        "1. Write ONLY the script lines starting with `Alex:` or `Sam:` on separate lines.\n"
        "2. Make the dialogue flow like real human speech: use natural banter, interruptions, 'Right', 'Exactly', 'Wait, really?', and smooth transitions.\n"
        "3. Reference specific facts, numbers, and pages from the documents (e.g., 'as shown on page 4...').\n"
        "4. Start with a catchy hook welcoming listeners, unpack the core breakthroughs and findings in the middle, and conclude with memorable final takeaways.\n"
        "5. Do NOT output parenthetical stage directions like (laughing) or (music fades). Output clean spoken text only."
    )

    return system_prompt, user_prompt


def parse_podcast_script(script_text: str) -> list[dict[str, Any]]:
    """Parse raw podcast text into structured dialogue turns."""
    turns: list[dict[str, Any]] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    for line in script_text.splitlines():
        trimmed = line.strip()
        if not trimmed:
            continue

        # Match speaker prefix like "Alex:" or "**Sam**:"
        match = re.match(r"^(\*\*|\*)?(Alex|Sam)(\*\*|\*)?\s*:\s*(.+)$", trimmed, re.IGNORECASE)
        if match:
            if current_speaker and current_lines:
                turns.append(
                    {
                        "speaker": current_speaker,
                        "text": " ".join(current_lines).strip(),
                        "index": len(turns),
                    }
                )
                current_lines = []

            speaker_raw = match.group(2).capitalize()
            current_speaker = "Alex" if "Alex" in speaker_raw else "Sam"
            current_lines.append(match.group(4).strip())
        elif current_speaker:
            current_lines.append(trimmed)

    if current_speaker and current_lines:
        turns.append(
            {
                "speaker": current_speaker,
                "text": " ".join(current_lines).strip(),
                "index": len(turns),
            }
        )

    # Fallback if no speaker tags were found
    if not turns and script_text.strip():
        paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
        for i, p in enumerate(paragraphs):
            speaker = "Alex" if i % 2 == 0 else "Sam"
            turns.append(
                {
                    "speaker": speaker,
                    "text": p,
                    "index": i,
                }
            )

    return turns


def generate_podcast(
    store: Any,
    source_ids: list[str],
    tone: str = "conversational",
    length: str = "medium",
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Generate a full two-host audio overview podcast script for the selected documents."""
    doc_contexts = compare.collect_comparison_context(store, source_ids)
    if not doc_contexts:
        raise ValueError("No indexed passages found for the requested documents.")

    system_prompt, user_prompt = build_podcast_prompt(doc_contexts, tone=tone, length=length)

    prov = provider or llm.default_provider() or "qwen-small"
    raw_script = llm.generate(prov, system_prompt, user_prompt, model=model, api_key=api_key)

    turns = parse_podcast_script(raw_script)

    first_doc_name = doc_contexts[0]["source_name"]
    title = (
        f"Deep Dive: {first_doc_name}"
        if len(doc_contexts) == 1
        else f"Comparative Deep Dive: {len(doc_contexts)} Documents"
    )

    # Estimate audio duration (avg speaking rate ~145 words per minute)
    total_words = sum(len(t["text"].split()) for t in turns)
    estimated_seconds = max(30, int((total_words / 145) * 60))

    return {
        "title": title,
        "script": turns,
        "full_text": raw_script,
        "source_ids": source_ids,
        "documents": [
            {"source_id": c["source_id"], "source_name": c["source_name"], "pages": c["pages"]}
            for c in doc_contexts
        ],
        "tone": tone,
        "length": length,
        "total_turns": len(turns),
        "total_words": total_words,
        "estimated_seconds": estimated_seconds,
        "provider": prov,
        "model": model,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
