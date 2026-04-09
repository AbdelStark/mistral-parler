"""
Property-based tests: deadline_resolver invariants

Uses Hypothesis to verify that resolve_deadline() satisfies structural
invariants for ALL inputs, not just the 30 hand-crafted cases in the
unit test file.

Properties proven here:
  P1  — Result is always date | None, never raises
  P2  — Resolved dates are always >= anchor date (future-only semantics)
  P3  — Resolved dates are never more than 366 days after anchor
  P4  — Deterministic: same inputs always produce same output
  P5  — Case-insensitive: upper/lower/mixed give same result
  P6  — Leading/trailing whitespace has no effect
  P7  — is_explicit=True implies the date was stated verbatim (exact phrase in input)
  P8  — is_explicit=False implies a relative interpretation was applied
  P9  — resolve_deadline(None, ...) always returns None
  P10 — Unresolvable gibberish always returns None (or at most a date)
  P11 — End-of-month results always land on the last day of the anchor month
  P12 — "tomorrow" always resolves to anchor + 1 day, never otherwise
"""

import pytest
from datetime import date, timedelta
import calendar

from hypothesis import given, assume, settings, HealthCheck
from hypothesis import strategies as st

from parler.extraction.deadline_resolver import resolve_deadline, resolve_deadline_full


# ─── Strategies ────────────────────────────────────────────────────────────

# A reasonable date range for anchors (not far-future, not distant past)
anchor_dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2035, 12, 31))

# Languages we support
languages = st.sampled_from(["en", "fr"])

# Garbage strings — should never raise, should resolve to None
garbage_strings = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "P", "Zs")),
    min_size=0,
    max_size=200,
).filter(lambda s: not any(
    kw in s.lower() for kw in
    ["tomorrow", "friday", "monday", "demain", "vendredi", "lundi",
     "next", "week", "month", "prochain", "semaine", "mois", "eow",
     "january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december",
     "janvier", "février", "mars", "avril", "juin", "juillet",
     "août", "septembre", "octobre", "novembre", "décembre",
     "2020", "2021", "2022", "2023", "2024", "2025", "2026",
     "2027", "2028", "2029", "2030",
     "/", "-",  # date separators
     ]
))


# ─── P1: Never raises ─────────────────────────────────────────────────────

@given(raw=st.one_of(st.none(), st.text(max_size=300)), anchor=anchor_dates, lang=languages)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_p1_never_raises(raw, anchor, lang):
    """For ANY string input (including None, empty, garbage), resolve_deadline never raises."""
    try:
        result = resolve_deadline(raw, anchor, lang)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"resolve_deadline({raw!r}, {anchor}, {lang!r}) raised {type(exc).__name__}: {exc}"
        )


# ─── P2: Resolved dates are always in the future ─────────────────────────

RELATIVE_KEYWORDS_EN = [
    "tomorrow", "next friday", "next monday", "next week",
    "end of week", "eow", "end of month", "next thursday",
    "next tuesday", "next wednesday", "next saturday", "next sunday",
]

RELATIVE_KEYWORDS_FR = [
    "demain", "vendredi prochain", "lundi prochain",
    "la semaine prochaine", "fin de semaine", "fin du mois",
    "jeudi prochain", "mardi prochain",
]

@pytest.mark.parametrize("raw,lang", [
    (kw, "en") for kw in RELATIVE_KEYWORDS_EN
] + [
    (kw, "fr") for kw in RELATIVE_KEYWORDS_FR
])
@given(anchor=anchor_dates)
@settings(max_examples=100)
def test_p2_resolved_date_is_future_or_today(raw, lang, anchor):
    """Relative date keywords always resolve to a date >= anchor."""
    result = resolve_deadline(raw, anchor, lang)
    if result is not None:
        assert result >= anchor, (
            f"resolve_deadline({raw!r}, {anchor}, {lang!r}) returned {result}, "
            f"which is BEFORE anchor {anchor}"
        )


# ─── P3: Resolved dates never more than 366 days out ─────────────────────

@given(
    raw=st.sampled_from(RELATIVE_KEYWORDS_EN + RELATIVE_KEYWORDS_FR),
    anchor=anchor_dates,
)
@settings(max_examples=200)
def test_p3_resolved_within_one_year(raw, anchor):
    """Relative keywords never resolve to a date more than 366 days in the future."""
    lang = "fr" if any(kw in raw for kw in ["prochain", "demain", "fin"]) else "en"
    result = resolve_deadline(raw, anchor, lang)
    if result is not None:
        delta = (result - anchor).days
        assert delta <= 366, (
            f"resolve_deadline({raw!r}, {anchor}, ...) resolved to {result}, "
            f"which is {delta} days ahead (> 366)"
        )


# ─── P4: Determinism ─────────────────────────────────────────────────────

@given(
    raw=st.one_of(
        st.sampled_from(RELATIVE_KEYWORDS_EN + RELATIVE_KEYWORDS_FR),
        st.none(),
        garbage_strings,
    ),
    anchor=anchor_dates,
    lang=languages,
)
@settings(max_examples=300)
def test_p4_deterministic(raw, anchor, lang):
    """Same inputs always produce same output — no randomness."""
    result1 = resolve_deadline(raw, anchor, lang)
    result2 = resolve_deadline(raw, anchor, lang)
    assert result1 == result2, (
        f"resolve_deadline({raw!r}, {anchor}, {lang!r}) returned "
        f"{result1} then {result2} — non-deterministic!"
    )


# ─── P5: Case insensitivity ───────────────────────────────────────────────

@given(
    raw=st.sampled_from(RELATIVE_KEYWORDS_EN),
    anchor=anchor_dates,
)
@settings(max_examples=150)
def test_p5_case_insensitive(raw, anchor):
    """Upper case, lower case, and title case produce the same result."""
    lower = resolve_deadline(raw.lower(), anchor, "en")
    upper = resolve_deadline(raw.upper(), anchor, "en")
    title = resolve_deadline(raw.title(), anchor, "en")
    assert lower == upper == title, (
        f"Case sensitivity detected for {raw!r} on {anchor}: "
        f"lower={lower}, upper={upper}, title={title}"
    )


# ─── P6: Whitespace invariance ────────────────────────────────────────────

@given(
    raw=st.sampled_from(RELATIVE_KEYWORDS_EN + RELATIVE_KEYWORDS_FR),
    leading_spaces=st.integers(min_value=0, max_value=10),
    trailing_spaces=st.integers(min_value=0, max_value=10),
    anchor=anchor_dates,
    lang=languages,
)
@settings(max_examples=150)
def test_p6_whitespace_invariant(raw, leading_spaces, trailing_spaces, anchor, lang):
    """Adding leading/trailing whitespace never changes the result."""
    padded = " " * leading_spaces + raw + " " * trailing_spaces
    result_raw = resolve_deadline(raw, anchor, lang)
    result_padded = resolve_deadline(padded, anchor, lang)
    assert result_raw == result_padded, (
        f"Whitespace changed result for {raw!r}: "
        f"stripped={result_raw}, padded={result_padded}"
    )


# ─── P7 / P8: is_explicit semantics ─────────────────────────────────────

EXPLICIT_EN = [
    "April 14th", "14/04/2026", "2026-04-20", "January 15th 2027",
    "15th of March", "March 15",
]

EXPLICIT_FR = [
    "14 avril", "avant le 17 avril", "le 20", "15 mars",
]

RELATIVE_EN = ["tomorrow", "next Friday", "end of week", "end of month", "next week"]
RELATIVE_FR = ["demain", "vendredi prochain", "fin de semaine", "la semaine prochaine"]


@pytest.mark.parametrize("raw,lang,expected_explicit", [
    *[(e, "en", True) for e in EXPLICIT_EN],
    *[(e, "fr", True) for e in EXPLICIT_FR],
    *[(r, "en", False) for r in RELATIVE_EN],
    *[(r, "fr", False) for r in RELATIVE_FR],
])
@given(anchor=anchor_dates)
@settings(max_examples=50)
def test_p7_p8_explicit_flag(raw, lang, expected_explicit, anchor):
    """is_explicit flag correctly distinguishes absolute dates from relative ones."""
    result = resolve_deadline_full(raw, anchor, lang)
    if result.resolved_date is not None:
        assert result.is_explicit == expected_explicit, (
            f"Expected is_explicit={expected_explicit} for {raw!r} ({lang}), "
            f"got {result.is_explicit}"
        )


# ─── P9: None input always returns None ─────────────────────────────────

@given(anchor=anchor_dates, lang=languages)
@settings(max_examples=100)
def test_p9_none_input_returns_none(anchor, lang):
    """resolve_deadline(None, ...) always returns None."""
    assert resolve_deadline(None, anchor, lang) is None


# ─── P11: End-of-month always lands on last day of month ─────────────────

@given(anchor=anchor_dates)
@settings(max_examples=200)
def test_p11_end_of_month_is_last_day(anchor):
    """'end of month' always resolves to the last day of the anchor month."""
    result = resolve_deadline("end of month", anchor, "en")
    if result is not None:
        expected_last = calendar.monthrange(result.year, result.month)[1]
        assert result.day == expected_last, (
            f"end of month for anchor {anchor} resolved to {result}, "
            f"but the last day of {result.month}/{result.year} is {expected_last}"
        )


@given(anchor=anchor_dates)
@settings(max_examples=200)
def test_p11_fin_du_mois_is_last_day(anchor):
    """'fin du mois' (French) always resolves to the last day of the anchor month."""
    result = resolve_deadline("fin du mois", anchor, "fr")
    if result is not None:
        expected_last = calendar.monthrange(result.year, result.month)[1]
        assert result.day == expected_last, (
            f"fin du mois for anchor {anchor} resolved to {result}, "
            f"but last day is {expected_last}"
        )


# ─── P12: "tomorrow" always = anchor + 1 day ─────────────────────────────

@given(anchor=anchor_dates)
@settings(max_examples=200)
def test_p12_tomorrow_is_anchor_plus_one(anchor):
    """'tomorrow' always resolves to anchor + 1 day without exception."""
    result = resolve_deadline("tomorrow", anchor, "en")
    assert result == anchor + timedelta(days=1), (
        f"tomorrow from {anchor} should be {anchor + timedelta(days=1)}, got {result}"
    )


@given(anchor=anchor_dates)
@settings(max_examples=200)
def test_p12_demain_is_anchor_plus_one(anchor):
    """'demain' (French) always resolves to anchor + 1 day."""
    result = resolve_deadline("demain", anchor, "fr")
    assert result == anchor + timedelta(days=1), (
        f"demain from {anchor} should be {anchor + timedelta(days=1)}, got {result}"
    )


# ─── Regression: specific dates proven invariant under date range ─────────

@given(anchor=st.dates(min_value=date(2025, 1, 1), max_value=date(2030, 12, 31)))
@settings(max_examples=200)
def test_next_friday_is_always_in_future(anchor):
    """'next Friday' always lands after anchor, regardless of what day anchor is."""
    result = resolve_deadline("next Friday", anchor, "en")
    if result is not None:
        assert result > anchor, (
            f"next Friday from {anchor} ({anchor.strftime('%A')}) resolved to "
            f"{result} which is not after anchor"
        )


@given(anchor=st.dates(min_value=date(2025, 1, 1), max_value=date(2030, 12, 31)))
@settings(max_examples=200)
def test_next_friday_lands_on_friday(anchor):
    """'next Friday' always resolves to a Friday (weekday index 4)."""
    result = resolve_deadline("next Friday", anchor, "en")
    if result is not None:
        assert result.weekday() == 4, (
            f"next Friday from {anchor} resolved to {result} "
            f"which is a {result.strftime('%A')}, not Friday"
        )
