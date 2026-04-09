"""Transcript speaker attribution heuristics."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Final, Literal

from ..models import Transcript
from .resolver import SpeakerResolver, format_human_name, normalize_speaker_token

SpeakerConfidence = Literal["high", "medium", "low", "unknown"]
_NAME_TRAILING_FILLERS: Final[frozenset[str]] = frozenset({"and", "et"})

_SELF_INTRO_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(
        r"\b(?:i am|i'm|this is|and i'm|and i am)\s+"
        r"([A-Za-z][A-Za-z'-]*(?:[- ][A-Za-z][A-Za-z'-]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bje m'appelle\s+([A-Za-z][A-Za-z'-]*(?:[- ][A-Za-z][A-Za-z'-]*)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bc'est\s+([A-Za-z][A-Za-z'-]*(?:[- ][A-Za-z][A-Za-z'-]*)?)\s+qui parle\b",
        re.IGNORECASE,
    ),
)
_EXPLICIT_SPEAKER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^\s*([A-Z][\w'-]*(?:[- ][A-Z][\w'-]*){0,2}|[A-Z]{2,4})\s*:\s*",
)


def _clean_extracted_name(candidate: str) -> str:
    tokens = [token for token in candidate.strip().split() if token]
    while len(tokens) > 1 and normalize_speaker_token(tokens[-1]) in _NAME_TRAILING_FILLERS:
        tokens.pop()
    return " ".join(tokens)


def _extract_self_intro_name(text: str) -> str | None:
    for pattern in _SELF_INTRO_PATTERNS:
        match = pattern.search(text)
        if match:
            cleaned = _clean_extracted_name(match.group(1))
            if cleaned:
                return cleaned
    return None


def _extract_explicit_speaker(text: str) -> str | None:
    match = _EXPLICIT_SPEAKER_PATTERN.match(text)
    if match:
        return match.group(1).strip()
    return None


def _find_subsequence(tokens: list[str], needle: list[str]) -> int | None:
    if not needle or len(needle) > len(tokens):
        return None
    for index in range(len(tokens) - len(needle) + 1):
        if tokens[index : index + len(needle)] == needle:
            return index
    return None


def _speaker_alias_label(index: int) -> str:
    label = ""
    current = index
    while True:
        label = chr(ord("A") + (current % 26)) + label
        current = current // 26 - 1
        if current < 0:
            return f"Speaker {label}"


class SpeakerAttributor:
    """Assign stable, human-readable speaker labels to transcript segments."""

    def __init__(self, *, confidence_threshold: float = 0.7, model: str = "mistral-large-latest"):
        self.confidence_threshold = confidence_threshold
        self.model = model

    def _register_name(
        self,
        candidate: str,
        *,
        resolver: SpeakerResolver,
        discovered_names: dict[str, str],
    ) -> str:
        canonical = resolver.resolve_name(candidate)
        if canonical is not None:
            return canonical
        normalized = normalize_speaker_token(candidate)
        if normalized in discovered_names:
            return discovered_names[normalized]
        formatted = format_human_name(candidate)
        discovered_names[normalized] = formatted
        return formatted

    def _extract_addressed_participant(
        self,
        text: str,
        *,
        resolver: SpeakerResolver,
        discovered_names: dict[str, str],
    ) -> str | None:
        if not text.strip():
            return None
        normalized_text = normalize_speaker_token(text)
        if not normalized_text or ("?" not in text and "," not in text):
            return None
        tokens = normalized_text.split()
        alias_pairs = list(resolver.iter_aliases())
        alias_pairs.extend((alias, name) for alias, name in discovered_names.items())

        seen_aliases: set[str] = set()
        for alias, canonical in alias_pairs:
            if alias in seen_aliases:
                continue
            seen_aliases.add(alias)
            alias_tokens = alias.split()
            position = _find_subsequence(tokens, alias_tokens)
            if position is not None and position <= 3:
                return canonical
        return None

    def _apply_anonymization(self, labels: list[str]) -> list[str]:
        mapping: dict[str, str] = {}
        next_index = 0
        anonymized: list[str] = []
        for label in labels:
            if label == "Unknown":
                anonymized.append(label)
                continue
            if label not in mapping:
                mapping[label] = _speaker_alias_label(next_index)
                next_index += 1
            anonymized.append(mapping[label])
        return anonymized

    def _fallback_unknown(self, transcript: Transcript) -> Transcript:
        segments = tuple(
            replace(segment, speaker_id="Unknown", speaker_confidence="unknown")
            for segment in transcript.segments
        )
        return replace(transcript, segments=segments)

    def attribute(
        self,
        transcript: Transcript,
        *,
        participants: list[str] | None = None,
        anonymize: bool = False,
    ) -> Transcript:
        try:
            resolver = SpeakerResolver(participants)
            if not transcript.segments:
                return replace(transcript, segments=())

            discovered_names: dict[str, str] = {}
            labels: list[str | None] = [None] * len(transcript.segments)
            confidences: list[SpeakerConfidence | None] = [None] * len(transcript.segments)
            opaque_mapping: dict[str, str] = {}
            opaque_confidence: dict[str, SpeakerConfidence] = {}

            for index, segment in enumerate(transcript.segments):
                raw_label = (segment.speaker_id or "").strip()

                if raw_label and not resolver.is_opaque_label(raw_label):
                    labels[index] = resolver.canonicalize_or_preserve(raw_label)
                    confidences[index] = segment.speaker_confidence or "high"

                explicit_name = _extract_explicit_speaker(segment.text)
                if explicit_name is not None:
                    explicit_label = self._register_name(
                        explicit_name,
                        resolver=resolver,
                        discovered_names=discovered_names,
                    )
                    labels[index] = explicit_label
                    confidences[index] = "high"
                    if raw_label and resolver.is_opaque_label(raw_label):
                        opaque_mapping[raw_label] = explicit_label
                        opaque_confidence[raw_label] = "high"

                if segment.start_s <= 300:
                    intro_name = _extract_self_intro_name(segment.text)
                    if intro_name is not None:
                        intro_label = self._register_name(
                            intro_name,
                            resolver=resolver,
                            discovered_names=discovered_names,
                        )
                        if labels[index] is None or resolver.is_opaque_label(raw_label):
                            labels[index] = intro_label
                            confidences[index] = "high"
                        if raw_label and resolver.is_opaque_label(raw_label):
                            opaque_mapping[raw_label] = intro_label
                            opaque_confidence[raw_label] = "high"

            assigned_participants = set(opaque_mapping.values())
            opaque_ids_in_order: list[str] = []
            for segment in transcript.segments:
                raw_label = (segment.speaker_id or "").strip()
                if (
                    raw_label
                    and resolver.is_opaque_label(raw_label)
                    and raw_label not in opaque_ids_in_order
                ):
                    opaque_ids_in_order.append(raw_label)
            for opaque_id in opaque_ids_in_order:
                if opaque_id in opaque_mapping:
                    continue
                next_participant = resolver.next_unassigned_participant(assigned_participants)
                if next_participant is None:
                    continue
                opaque_mapping[opaque_id] = next_participant
                opaque_confidence[opaque_id] = "medium"
                assigned_participants.add(next_participant)

            for index, segment in enumerate(transcript.segments):
                raw_label = (segment.speaker_id or "").strip()
                if labels[index] is None and raw_label and raw_label in opaque_mapping:
                    labels[index] = opaque_mapping[raw_label]
                    confidences[index] = opaque_confidence.get(raw_label, "medium")

            for index, segment in enumerate(transcript.segments[:-1]):
                addressed = self._extract_addressed_participant(
                    segment.text,
                    resolver=resolver,
                    discovered_names=discovered_names,
                )
                if addressed is None:
                    continue
                next_index = index + 1
                next_segment = transcript.segments[next_index]
                if labels[next_index] is None:
                    labels[next_index] = addressed
                    confidences[next_index] = "medium"
                next_raw_label = (next_segment.speaker_id or "").strip()
                if (
                    next_raw_label
                    and resolver.is_opaque_label(next_raw_label)
                    and next_raw_label not in opaque_mapping
                ):
                    opaque_mapping[next_raw_label] = addressed
                    opaque_confidence[next_raw_label] = "medium"

            discovered_label_set = {label for label in labels if label not in {None, "Unknown"}}
            if len(discovered_label_set) == 1 and all(
                segment.speaker_id is None for segment in transcript.segments
            ):
                sole_label = next(iter(discovered_label_set))
                for index, current_label in enumerate(labels):
                    if current_label is None:
                        labels[index] = sole_label
                        confidences[index] = "low"

            if len(resolver.ordered_participants) == 1:
                sole_participant = resolver.ordered_participants[0]
                for index, current_label in enumerate(labels):
                    if current_label is None:
                        labels[index] = sole_participant
                        confidences[index] = "medium"

            finalized_labels = [label or "Unknown" for label in labels]
            finalized_confidences: list[SpeakerConfidence] = [
                confidence or "unknown" for confidence in confidences
            ]

            if anonymize:
                finalized_labels = self._apply_anonymization(finalized_labels)

            segments = tuple(
                replace(
                    segment,
                    speaker_id=finalized_labels[index],
                    speaker_confidence=finalized_confidences[index],
                )
                for index, segment in enumerate(transcript.segments)
            )
            return replace(transcript, segments=segments)
        except Exception:
            return self._fallback_unknown(transcript)
