"""Resolve natural-language deadlines against a meeting-date anchor."""

from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from typing import Final

from ..models import CommitmentDeadline

_WEEKDAYS: Final[dict[str, int]] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}
_MONTHS: Final[dict[str, int]] = {
    "january": 1,
    "janvier": 1,
    "february": 2,
    "fevrier": 2,
    "march": 3,
    "mars": 3,
    "april": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "june": 6,
    "juin": 6,
    "july": 7,
    "juillet": 7,
    "august": 8,
    "aout": 8,
    "september": 9,
    "septembre": 9,
    "october": 10,
    "octobre": 10,
    "november": 11,
    "novembre": 11,
    "december": 12,
    "decembre": 12,
}
_EXPLICIT_PREFIXES: Final[tuple[str, ...]] = ("avant le ", "before ", "by ")
_UNRESOLVABLE_TERMS: Final[set[str]] = {
    "asap",
    "bientot",
    "des que possible",
    "sometime soon",
    "soon",
    "tbd",
}
_ISO_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_NUMERIC_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_MONTH_FIRST_PATTERN: Final[re.Pattern[str]] = re.compile(r"^([a-z]+)\s+(\d{1,2})(?:\s+(\d{4}))?$")
_DAY_FIRST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(\d{1,2})\s+(?:of\s+)?([a-z]+)(?:\s+(\d{4}))?$"
)
_DAY_ONLY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?:le\s+)?(\d{1,2})$")


def _normalize_text(raw: str) -> str:
    normalized = unicodedata.normalize("NFKD", raw)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    lowered = without_accents.lower().strip()
    lowered = re.sub(r"\b(\d{1,2})(st|nd|rd|th)\b", r"\1", lowered)
    lowered = re.sub(r"[.,;]+", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _next_month(anchor: date) -> tuple[int, int]:
    if anchor.month == 12:
        return anchor.year + 1, 1
    return anchor.year, anchor.month + 1


def _next_named_weekday(anchor: date, weekday: int) -> date:
    start_next_week = anchor + timedelta(days=(7 - anchor.weekday()))
    return start_next_week + timedelta(days=weekday)


def _this_named_weekday(anchor: date, weekday: int) -> date:
    start_of_week = anchor - timedelta(days=anchor.weekday())
    return start_of_week + timedelta(days=weekday)


def _by_named_weekday(anchor: date, weekday: int) -> date:
    if anchor.weekday() == weekday:
        return anchor
    return _next_named_weekday(anchor, weekday)


def _end_of_week(anchor: date) -> date:
    saturday = 5
    delta = (saturday - anchor.weekday()) % 7
    return anchor + timedelta(days=delta)


def _end_of_month(anchor: date) -> date:
    last_day = calendar.monthrange(anchor.year, anchor.month)[1]
    return date(anchor.year, anchor.month, last_day)


def _future_month_day(anchor: date, month: int, day: int, year: int | None = None) -> date | None:
    if year is not None:
        return _safe_date(year, month, day)
    candidate = _safe_date(anchor.year, month, day)
    if candidate is None:
        return None
    if candidate < anchor:
        return _safe_date(anchor.year + 1, month, day)
    return candidate


def _parse_numeric_date(raw: str, anchor: date, language: str) -> date | None:
    match = _NUMERIC_DATE_PATTERN.match(raw)
    if not match:
        return None
    first, second, year_text = (int(group) for group in match.groups())
    if first > 12:
        day, month = first, second
    elif second > 12:
        month, day = first, second
    elif language == "fr":
        day, month = first, second
    else:
        month, day = first, second
    candidate = _safe_date(int(year_text), month, day)
    if candidate is None:
        return None
    if candidate < anchor and candidate.year == anchor.year:
        return _safe_date(candidate.year + 1, candidate.month, candidate.day)
    return candidate


def _parse_month_name_date(raw: str, anchor: date) -> date | None:
    month_first = _MONTH_FIRST_PATTERN.match(raw)
    if month_first:
        month_text, day_text, year_text = month_first.groups()
        month = _MONTHS.get(month_text)
        if month is None:
            return None
        return _future_month_day(
            anchor,
            month,
            int(day_text),
            int(year_text) if year_text is not None else None,
        )

    day_first = _DAY_FIRST_PATTERN.match(raw)
    if day_first:
        day_text, month_text, year_text = day_first.groups()
        month = _MONTHS.get(month_text)
        if month is None:
            return None
        return _future_month_day(
            anchor,
            month,
            int(day_text),
            int(year_text) if year_text is not None else None,
        )

    return None


def _parse_day_only(raw: str, anchor: date) -> date | None:
    match = _DAY_ONLY_PATTERN.match(raw)
    if not match:
        return None
    day = int(match.group(1))
    current = _safe_date(anchor.year, anchor.month, day)
    if current is not None and current >= anchor:
        return current
    next_year, next_month = _next_month(anchor)
    return _safe_date(next_year, next_month, day)


def _parse_explicit_date(raw: str, anchor: date, language: str) -> date | None:
    candidate = raw
    for prefix in _EXPLICIT_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :].strip()
            break

    iso_match = _ISO_DATE_PATTERN.match(candidate)
    if iso_match:
        year_text, month_text, day_text = iso_match.groups()
        return _safe_date(int(year_text), int(month_text), int(day_text))

    numeric = _parse_numeric_date(candidate, anchor, language)
    if numeric is not None:
        return numeric

    month_name = _parse_month_name_date(candidate, anchor)
    if month_name is not None:
        return month_name

    if language == "fr":
        return _parse_day_only(candidate, anchor)
    return None


def _resolve_relative_date(raw: str, anchor: date) -> date | None:
    if raw == "tomorrow" or raw == "demain":
        return anchor + timedelta(days=1)
    if raw in {"next week", "la semaine prochaine"}:
        return _next_named_weekday(anchor, 0)
    if raw in {"end of month", "fin du mois"}:
        return _end_of_month(anchor)
    if raw in {"end of week", "by end of week", "eow", "fin de semaine"}:
        return _end_of_week(anchor)

    if raw.startswith("next "):
        weekday = _WEEKDAYS.get(raw.removeprefix("next ").strip())
        if weekday is not None:
            return _next_named_weekday(anchor, weekday)

    if raw.endswith(" prochain"):
        weekday = _WEEKDAYS.get(raw.removesuffix(" prochain").strip())
        if weekday is not None:
            return _next_named_weekday(anchor, weekday)

    if raw.startswith("this "):
        weekday = _WEEKDAYS.get(raw.removeprefix("this ").strip())
        if weekday is not None:
            return _this_named_weekday(anchor, weekday)

    if raw.startswith("ce "):
        weekday = _WEEKDAYS.get(raw.removeprefix("ce ").strip())
        if weekday is not None:
            return _this_named_weekday(anchor, weekday)

    if raw.startswith("by "):
        weekday = _WEEKDAYS.get(raw.removeprefix("by ").strip())
        if weekday is not None:
            return _by_named_weekday(anchor, weekday)

    if raw.startswith("d'ici "):
        remainder = raw.removeprefix("d'ici ").strip()
        if remainder.endswith(" prochain"):
            weekday = _WEEKDAYS.get(remainder.removesuffix(" prochain").strip())
            if weekday is not None:
                return _next_named_weekday(anchor, weekday)
        weekday = _WEEKDAYS.get(remainder)
        if weekday is not None:
            return _by_named_weekday(anchor, weekday)

    return None


def resolve_deadline_full(
    raw: str | None,
    meeting_date: date,
    language: str,
) -> CommitmentDeadline:
    original = (raw or "").strip()
    if not original:
        return CommitmentDeadline(raw=original, resolved_date=None, is_explicit=False)

    try:
        normalized = _normalize_text(original)
        if not normalized or normalized in _UNRESOLVABLE_TERMS:
            return CommitmentDeadline(raw=original, resolved_date=None, is_explicit=False)

        explicit = _parse_explicit_date(normalized, meeting_date, language)
        if explicit is not None:
            return CommitmentDeadline(raw=original, resolved_date=explicit, is_explicit=True)

        relative = _resolve_relative_date(normalized, meeting_date)
        if relative is not None:
            return CommitmentDeadline(raw=original, resolved_date=relative, is_explicit=False)
    except Exception:
        return CommitmentDeadline(raw=original, resolved_date=None, is_explicit=False)

    return CommitmentDeadline(raw=original, resolved_date=None, is_explicit=False)


def resolve_deadline(raw: str | None, meeting_date: date, language: str) -> date | None:
    return resolve_deadline_full(raw, meeting_date, language).resolved_date


def resolve_deadline_today(raw: str | None, language: str) -> date | None:
    return resolve_deadline(raw, datetime.now(UTC).date(), language)


__all__ = ["resolve_deadline", "resolve_deadline_full", "resolve_deadline_today"]
