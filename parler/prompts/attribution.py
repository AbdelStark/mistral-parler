"""Prompt scaffolding for future LLM-backed speaker enrichment."""

ATTRIBUTION_PROMPT_VERSION = "v1"

ATTRIBUTION_PROMPT_TEMPLATE = """
You are resolving speaker names for a meeting transcript.

Rules:
- Prefer upstream diarization labels when they are already human-readable.
- Use participant hints and transcript cues to resolve opaque labels like SPEAKER_00.
- Never invent a name that is absent from the participant list or transcript text.
- If attribution is ambiguous, return "Unknown".
- Preserve segment IDs and timestamps exactly as provided.
""".strip()
