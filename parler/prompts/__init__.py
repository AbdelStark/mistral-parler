"""Prompt templates used by LLM-backed stages."""

from .attribution import ATTRIBUTION_PROMPT_TEMPLATE, ATTRIBUTION_PROMPT_VERSION
from .extraction import (
    DEFAULT_EXTRACTION_PROMPT_VERSION,
    EXTRACTION_PROMPTS,
    get_extraction_prompt,
)

__all__ = [
    "ATTRIBUTION_PROMPT_TEMPLATE",
    "ATTRIBUTION_PROMPT_VERSION",
    "DEFAULT_EXTRACTION_PROMPT_VERSION",
    "EXTRACTION_PROMPTS",
    "get_extraction_prompt",
]
