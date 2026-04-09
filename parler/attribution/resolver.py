"""Speaker-name resolution helpers."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

_NON_ALNUM_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+")
_OPAQUE_SPEAKER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:speaker|spk)[\s_-]*\d+$",
    re.IGNORECASE,
)
_PARENTHETICAL_PATTERN: Final[re.Pattern[str]] = re.compile(r"\(([^)]*)\)")


def normalize_speaker_token(value: str) -> str:
    """Normalize a name or role label for conservative matching."""

    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    collapsed = _NON_ALNUM_PATTERN.sub(" ", without_accents.lower())
    return " ".join(collapsed.split())


def _format_name_piece(piece: str) -> str:
    if piece.isupper() and len(piece) <= 4:
        return piece
    return piece[:1].upper() + piece[1:].lower()


def format_human_name(value: str) -> str:
    """Format a raw speaker label into a readable human name."""

    tokens = []
    for token in value.strip().split():
        subtokens = [_format_name_piece(part) for part in token.split("-") if part]
        if subtokens:
            tokens.append("-".join(subtokens))
    return " ".join(tokens)


def _parse_participant(raw_participant: str) -> tuple[str, set[str]]:
    canonical = _PARENTHETICAL_PATTERN.sub("", raw_participant).strip(" ,")
    canonical = format_human_name(canonical or raw_participant.strip())
    aliases = {canonical}

    name_tokens = [token for token in re.split(r"[\s-]+", canonical) if token]
    if name_tokens:
        aliases.add(name_tokens[0])
        if len(name_tokens) > 1:
            aliases.add("".join(token[0] for token in name_tokens).upper())

    for parenthetical in _PARENTHETICAL_PATTERN.findall(raw_participant):
        for part in re.split(r"[,/;|]", parenthetical):
            alias = part.strip()
            if alias:
                aliases.add(alias)

    return canonical, aliases


class SpeakerResolver:
    """Resolve speaker aliases against the participant list."""

    def __init__(self, participants: list[str] | None = None):
        ordered_participants: list[str] = []
        alias_candidates: dict[str, set[str]] = {}

        for raw_participant in participants or []:
            if not raw_participant.strip():
                continue
            canonical, aliases = _parse_participant(raw_participant)
            if canonical not in ordered_participants:
                ordered_participants.append(canonical)
            for alias in aliases:
                normalized_alias = normalize_speaker_token(alias)
                if normalized_alias:
                    alias_candidates.setdefault(normalized_alias, set()).add(canonical)

        self._ordered_participants = tuple(ordered_participants)
        self._alias_to_canonical = {
            alias: next(iter(candidates))
            for alias, candidates in alias_candidates.items()
            if len(candidates) == 1
        }
        self._sorted_aliases = tuple(
            sorted(
                self._alias_to_canonical.items(),
                key=lambda item: (-len(item[0].split()), -len(item[0])),
            )
        )

    @property
    def ordered_participants(self) -> tuple[str, ...]:
        return self._ordered_participants

    def is_opaque_label(self, label: str | None) -> bool:
        if label is None:
            return False
        return bool(_OPAQUE_SPEAKER_PATTERN.fullmatch(label.strip()))

    def resolve_name(self, raw_name: str | None) -> str | None:
        if raw_name is None:
            return None
        normalized = normalize_speaker_token(raw_name)
        if not normalized:
            return None
        return self._alias_to_canonical.get(normalized)

    def canonicalize_or_preserve(self, raw_name: str) -> str:
        return self.resolve_name(raw_name) or format_human_name(raw_name)

    def next_unassigned_participant(self, assigned_names: set[str]) -> str | None:
        for participant in self._ordered_participants:
            if participant not in assigned_names:
                return participant
        return None

    def iter_aliases(self) -> tuple[tuple[str, str], ...]:
        return self._sorted_aliases
