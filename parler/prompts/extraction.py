"""Prompt registry for decision extraction."""

from __future__ import annotations

DEFAULT_EXTRACTION_PROMPT_VERSION = "v1.0"

_BASE_EXTRACTION_PROMPT = """
You are a meeting intelligence system that extracts a canonical decision log from business meeting transcripts.

Rules:
- Return JSON only. Do not emit markdown or commentary.
- Extract only explicit or strongly implied outcomes.
- Include decisions, commitments, rejections, and unresolved open questions.
- Drop low-confidence items. Only keep high or medium confidence.
- Preserve the original quote language from the transcript.
- Use null for unknown fields.
- Never invent speakers, owners, dates, or facts not grounded in the transcript or provided participants.
- A commitment needs a concrete action; owner may be "Unknown" only when the transcript does not identify one.
""".strip()

EXTRACTION_PROMPTS: dict[str, str] = {
    "v1": _BASE_EXTRACTION_PROMPT,
    "v1.0": _BASE_EXTRACTION_PROMPT,
    "v1.0.0": _BASE_EXTRACTION_PROMPT,
    "v1.2.0": _BASE_EXTRACTION_PROMPT,
}


def get_extraction_prompt(version: str) -> str:
    return EXTRACTION_PROMPTS.get(version, EXTRACTION_PROMPTS[DEFAULT_EXTRACTION_PROMPT_VERSION])


__all__ = [
    "DEFAULT_EXTRACTION_PROMPT_VERSION",
    "EXTRACTION_PROMPTS",
    "get_extraction_prompt",
]
