"""Defensive normalization for extraction responses."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, Final, Literal, cast

from ..models import (
    Commitment,
    CommitmentDeadline,
    Decision,
    DecisionLog,
    ExtractionMetadata,
    OpenQuestion,
    Rejection,
)
from .deadline_resolver import resolve_deadline_full

logger = logging.getLogger(__name__)

Confidence = Literal["high", "medium"]

_LANGUAGE_ALIASES: Final[dict[str, str]] = {
    "arabic": "ar",
    "de": "de",
    "english": "en",
    "en": "en",
    "es": "es",
    "french": "fr",
    "fr": "fr",
    "german": "de",
    "it": "it",
    "italian": "it",
    "ja": "ja",
    "japanese": "ja",
    "ko": "ko",
    "korean": "ko",
    "nl": "nl",
    "polish": "pl",
    "pl": "pl",
    "portuguese": "pt",
    "pt": "pt",
    "spanish": "es",
    "zh": "zh",
    "chinese": "zh",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _empty_log(
    *,
    meeting_date: date | None,
    model: str,
    prompt_version: str,
    extracted_at: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    pass_count: int = 1,
    parse_warnings: tuple[str, ...] = (),
) -> DecisionLog:
    return DecisionLog(
        decisions=(),
        commitments=(),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model=model,
            prompt_version=prompt_version,
            meeting_date=meeting_date,
            extracted_at=extracted_at or _timestamp(),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pass_count=pass_count,
            parse_warnings=parse_warnings,
        ),
    )


def _coerce_payload(response: object) -> dict[str, Any]:
    if response is None:
        return {}
    if isinstance(response, dict):
        return cast(dict[str, Any], response)
    if isinstance(response, str):
        try:
            decoded = json.loads(response)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, dict):
            return cast(dict[str, Any], decoded)
        return {}
    return {}


def _coerce_items(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    items: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            items.append(cast(dict[str, Any], item))
    return items


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_confidence(value: object) -> Confidence | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "high":
            return "high"
        if normalized == "low":
            return None
        if normalized == "medium":
            return "medium"
    return "medium"


def _normalize_language(value: object, default: str = "en") -> str:
    normalized = _clean_text(value).lower()
    if not normalized:
        return default
    if normalized in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[normalized]
    if len(normalized) == 2 and normalized.isalpha():
        return normalized
    return default


def _normalize_quote(value: object, *, warnings: list[str], item_label: str) -> str:
    quote = _clean_text(value)
    if not quote:
        warning = f"empty quote retained for {item_label}"
        logger.warning(warning)
        warnings.append(warning)
        return ""
    if len(quote) > 500:
        return f"{quote[:500]}..."
    return quote


def _normalize_timestamp(value: object) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(cast(Any, value))
    except (TypeError, ValueError):
        return None
    if normalized < 0:
        return None
    return normalized


def _normalize_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names: list[str] = []
    for item in value:
        candidate = _clean_text(item)
        if candidate and candidate not in names:
            names.append(candidate)
    return tuple(names)


def _normalize_deadline(
    value: object,
    *,
    meeting_date: date | None,
    language: str,
) -> CommitmentDeadline | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        return None
    raw_value = _clean_text(value.get("raw"))
    if not raw_value:
        return None
    if meeting_date is None:
        resolved_date = None
        is_explicit = bool(value.get("is_explicit"))
        return CommitmentDeadline(
            raw=raw_value, resolved_date=resolved_date, is_explicit=is_explicit
        )
    resolved = resolve_deadline_full(raw_value, meeting_date, language)
    explicit_override = value.get("is_explicit")
    if isinstance(explicit_override, bool):
        return CommitmentDeadline(
            raw=raw_value,
            resolved_date=resolved.resolved_date,
            is_explicit=explicit_override
            if resolved.resolved_date is None
            else resolved.is_explicit,
        )
    return resolved


def _parse_decision(
    item: dict[str, Any],
    *,
    warnings: list[str],
) -> Decision | None:
    summary = _clean_text(item.get("summary"))
    if not summary:
        return None
    confidence = _normalize_confidence(item.get("confidence"))
    if confidence is None:
        return None
    language = _normalize_language(item.get("language"), default="en")
    return Decision(
        id="D0",
        summary=summary,
        timestamp_s=_normalize_timestamp(item.get("timestamp_s")),
        speaker=_clean_text(item.get("speaker")) or None,
        confirmed_by=_normalize_names(item.get("confirmed_by")),
        quote=_normalize_quote(item.get("quote"), warnings=warnings, item_label="decision"),
        confidence=confidence,
        language=language,
    )


def _parse_commitment(
    item: dict[str, Any],
    *,
    warnings: list[str],
    meeting_date: date | None,
) -> Commitment | None:
    action = _clean_text(item.get("action"))
    if not action:
        return None
    confidence = _normalize_confidence(item.get("confidence"))
    if confidence is None:
        return None
    language = _normalize_language(item.get("language"), default="en")
    owner = _clean_text(item.get("owner")) or "Unknown"
    return Commitment(
        id="C0",
        owner=owner,
        action=action,
        deadline=_normalize_deadline(
            item.get("deadline"), meeting_date=meeting_date, language=language
        ),
        timestamp_s=_normalize_timestamp(item.get("timestamp_s")),
        quote=_normalize_quote(item.get("quote"), warnings=warnings, item_label="commitment"),
        confidence=confidence,
        language=language,
    )


def _parse_rejection(
    item: dict[str, Any],
    *,
    warnings: list[str],
) -> Rejection | None:
    summary = _clean_text(item.get("summary") or item.get("proposal"))
    if not summary:
        return None
    confidence = _normalize_confidence(item.get("confidence"))
    if confidence is None:
        return None
    language = _normalize_language(item.get("language"), default="en")
    return Rejection(
        id="R0",
        summary=summary,
        timestamp_s=_normalize_timestamp(item.get("timestamp_s")),
        quote=_normalize_quote(item.get("quote"), warnings=warnings, item_label="rejection"),
        confidence=confidence,
        language=language,
        reason=_clean_text(item.get("reason")) or None,
    )


def _parse_open_question(
    item: dict[str, Any],
    *,
    warnings: list[str],
) -> OpenQuestion | None:
    question = _clean_text(item.get("question"))
    if not question:
        return None
    confidence = _normalize_confidence(item.get("confidence"))
    if confidence is None:
        return None
    language = _normalize_language(item.get("language"), default="en")
    return OpenQuestion(
        id="Q0",
        question=question,
        asked_by=_clean_text(item.get("asked_by")) or None,
        timestamp_s=_normalize_timestamp(item.get("timestamp_s")),
        quote=_normalize_quote(item.get("quote"), warnings=warnings, item_label="open question"),
        language=language,
        stakes=_clean_text(item.get("stakes")) or None,
        confidence=confidence,
    )


def validate_decision_log(log: DecisionLog) -> DecisionLog:
    decisions = tuple(
        replace(item, id=f"D{index}") for index, item in enumerate(log.decisions, start=1)
    )
    commitments = tuple(
        replace(item, id=f"C{index}") for index, item in enumerate(log.commitments, start=1)
    )
    rejected = tuple(
        replace(item, id=f"R{index}") for index, item in enumerate(log.rejected, start=1)
    )
    open_questions = tuple(
        replace(item, id=f"Q{index}") for index, item in enumerate(log.open_questions, start=1)
    )
    return replace(
        log,
        decisions=decisions,
        commitments=commitments,
        rejected=rejected,
        open_questions=open_questions,
    )


def parse_extraction_response(
    response: object,
    *,
    meeting_date: date | None,
    model: str = "mistral-large-latest",
    prompt_version: str = "v1.0",
    extracted_at: str | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    pass_count: int = 1,
) -> DecisionLog:
    try:
        payload = _coerce_payload(response)
        warnings: list[str] = []

        decision_items: list[Decision] = []
        for raw_item in _coerce_items(payload.get("decisions")):
            parsed_decision = _parse_decision(raw_item, warnings=warnings)
            if parsed_decision is not None:
                decision_items.append(parsed_decision)

        commitment_items: list[Commitment] = []
        for raw_item in _coerce_items(payload.get("commitments")):
            parsed_commitment = _parse_commitment(
                raw_item,
                warnings=warnings,
                meeting_date=meeting_date,
            )
            if parsed_commitment is not None:
                commitment_items.append(parsed_commitment)

        rejection_items: list[Rejection] = []
        for raw_item in _coerce_items(payload.get("rejected")):
            parsed_rejection = _parse_rejection(raw_item, warnings=warnings)
            if parsed_rejection is not None:
                rejection_items.append(parsed_rejection)

        question_items: list[OpenQuestion] = []
        for raw_item in _coerce_items(payload.get("open_questions")):
            parsed_question = _parse_open_question(raw_item, warnings=warnings)
            if parsed_question is not None:
                question_items.append(parsed_question)

        return validate_decision_log(
            DecisionLog(
                decisions=tuple(decision_items),
                commitments=tuple(commitment_items),
                rejected=tuple(rejection_items),
                open_questions=tuple(question_items),
                metadata=ExtractionMetadata(
                    model=model,
                    prompt_version=prompt_version,
                    meeting_date=meeting_date,
                    extracted_at=extracted_at or _timestamp(),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    pass_count=pass_count,
                    parse_warnings=tuple(warnings),
                ),
            )
        )
    except Exception:
        return _empty_log(
            meeting_date=meeting_date,
            model=model,
            prompt_version=prompt_version,
            extracted_at=extracted_at,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            pass_count=pass_count,
        )


__all__ = ["parse_extraction_response", "validate_decision_log"]
