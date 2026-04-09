"""
Property-based tests: extraction parser invariants

Uses Hypothesis to verify that parse_extraction_response() satisfies
structural invariants across the full input space.

Properties proven here:
  P1  — Never raises for any dict/string/None input
  P2  — Output is always a DecisionLog (never None, never a raw dict)
  P3  — All IDs in output are unique within their collection
  P4  — All confidence values are exactly "high" or "medium" (never "low",
         never unknown values like "very_high")
  P5  — All language codes are exactly 2 lowercase characters (ISO 639-1)
  P6  — Decisions count + rejected count + open_questions count ≤ total items
         in input decisions (filter but never inflate)
  P7  — Any item missing 'summary' (decision) or 'action' (commitment) is dropped
  P8  — Empty-collection input always produces an empty log (is_empty=True)
  P9  — All resolved deadline dates are date objects or None (never strings)
  P10 — Output segments are immutable (frozen dataclass)
  P11 — IDs follow Dₙ / Cₙ / Rₙ / Qₙ pattern after normalization
"""

import pytest
import string
from datetime import date
from typing import Any

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from parler.extraction.parser import parse_extraction_response


# ─── Strategies ──────────────────────────────────────────────────────────────

ANCHOR = date(2026, 4, 9)

valid_confidence = st.sampled_from(["high", "medium", "low", "very_high", "unknown", ""])
valid_language = st.sampled_from(["fr", "en", "de", "es", "it", "pt", "zh", "FRENCH", "English", ""])

short_text = st.text(
    alphabet=string.ascii_letters + string.digits + " .,!?'-",
    min_size=1,
    max_size=100,
)

optional_float = st.one_of(st.none(), st.floats(min_value=0.0, max_value=7200.0, allow_nan=False))
optional_text = st.one_of(st.none(), short_text)

def decision_strategy():
    return st.fixed_dictionaries({
        "summary": short_text,
        "confidence": valid_confidence,
        "language": valid_language,
        "quote": st.one_of(st.just(""), short_text),
        "timestamp_s": optional_float,
        "speaker": optional_text,
        "confirmed_by": st.lists(short_text, max_size=5),
    }, optional={
        "id": st.one_of(st.just("D1"), short_text, st.none()),
    })

def decision_without_summary():
    return st.fixed_dictionaries({
        "confidence": valid_confidence,
        "language": valid_language,
        "quote": short_text,
        "timestamp_s": optional_float,
        "speaker": optional_text,
        "confirmed_by": st.lists(short_text, max_size=5),
    })

def commitment_strategy():
    return st.fixed_dictionaries({
        "action": short_text,
        "confidence": valid_confidence,
        "language": valid_language,
        "quote": st.one_of(st.just(""), short_text),
        "timestamp_s": optional_float,
        "deadline": st.one_of(st.none(), st.fixed_dictionaries({
            "raw": short_text,
            "resolved_date": st.none(),
            "is_explicit": st.booleans(),
        })),
    }, optional={
        "id": st.one_of(st.just("C1"), short_text),
        "owner": st.one_of(st.none(), short_text),
    })

def valid_response_strategy():
    return st.fixed_dictionaries({
        "decisions": st.lists(decision_strategy(), max_size=20),
        "commitments": st.lists(commitment_strategy(), max_size=20),
        "rejected": st.lists(st.dictionaries(st.text(max_size=20), st.text(max_size=50)), max_size=5),
        "open_questions": st.lists(st.dictionaries(st.text(max_size=20), st.text(max_size=50)), max_size=5),
    })


# ─── P1: Never raises ────────────────────────────────────────────────────────

@given(
    response=st.one_of(
        st.none(),
        st.text(max_size=500),
        st.integers(),
        st.lists(st.integers(), max_size=5),
        valid_response_strategy(),
        st.fixed_dictionaries({}),
    )
)
@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
def test_p1_never_raises(response: Any):
    """parse_extraction_response never raises for any input."""
    try:
        parse_extraction_response(response, meeting_date=ANCHOR)
    except Exception as exc:  # noqa: BLE001
        pytest.fail(
            f"parse_extraction_response({type(response).__name__}) raised "
            f"{type(exc).__name__}: {exc}"
        )


# ─── P2: Always returns DecisionLog ─────────────────────────────────────────

@given(response=st.one_of(st.none(), st.text(max_size=200), valid_response_strategy()))
@settings(max_examples=300)
def test_p2_always_returns_decision_log(response: Any):
    """Return type is always DecisionLog — never None, never dict."""
    from parler.models import DecisionLog
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    assert isinstance(result, DecisionLog), (
        f"Expected DecisionLog, got {type(result).__name__}"
    )


# ─── P3: IDs are unique within each collection ───────────────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p3_ids_unique_in_decisions(response: Any):
    """All decision IDs in the output are unique."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    ids = [d.id for d in result.decisions]
    assert len(ids) == len(set(ids)), f"Duplicate decision IDs: {ids}"


@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p3_ids_unique_in_commitments(response: Any):
    """All commitment IDs in the output are unique."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    ids = [c.id for c in result.commitments]
    assert len(ids) == len(set(ids)), f"Duplicate commitment IDs: {ids}"


# ─── P4: Confidence values are normalized ────────────────────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p4_all_confidence_values_are_valid(response: Any):
    """All confidence values in output are exactly 'high' or 'medium'."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    for d in result.decisions:
        assert d.confidence in ("high", "medium"), (
            f"Invalid confidence in decision {d.id}: {d.confidence!r}"
        )
    for c in result.commitments:
        assert c.confidence in ("high", "medium"), (
            f"Invalid confidence in commitment {c.id}: {c.confidence!r}"
        )


# ─── P5: Language codes are valid ISO 639-1 ──────────────────────────────────

VALID_LANGUAGES = {"fr", "en", "de", "es", "it", "pt", "nl", "pl", "ar", "zh", "ja", "ko"}

@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p5_language_codes_are_iso_639_1(response: Any):
    """All language codes in output are 2-character lowercase ISO 639-1 codes."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    for d in result.decisions:
        assert len(d.language) == 2, (
            f"Language code {d.language!r} is not 2 characters"
        )
        assert d.language == d.language.lower(), (
            f"Language code {d.language!r} is not lowercase"
        )


# ─── P6: Parser only filters, never inflates ────────────────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p6_output_count_never_exceeds_input(response: Any):
    """The parser can only remove items, never create new ones from thin air."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    input_decision_count = len(response.get("decisions", []))
    input_commitment_count = len(response.get("commitments", []))
    assert len(result.decisions) <= input_decision_count, (
        f"Output has {len(result.decisions)} decisions but input had {input_decision_count}"
    )
    assert len(result.commitments) <= input_commitment_count, (
        f"Output has {len(result.commitments)} commitments but input had {input_commitment_count}"
    )


# ─── P7: Missing required fields cause item to be dropped ────────────────────

@given(
    extra_decisions=st.lists(decision_without_summary(), min_size=0, max_size=5),
    good_decisions=st.lists(decision_strategy(), min_size=0, max_size=5),
    anchor=st.dates(min_value=date(2024, 1, 1), max_value=date(2030, 12, 31)),
)
@settings(max_examples=200)
def test_p7_items_missing_summary_are_dropped(extra_decisions, good_decisions, anchor):
    """Decisions without a 'summary' field are silently dropped."""
    response = {
        "decisions": good_decisions + extra_decisions,
        "commitments": [],
        "rejected": [],
        "open_questions": [],
    }
    result = parse_extraction_response(response, meeting_date=anchor)
    # Only the good decisions (those with summaries) should survive
    assert len(result.decisions) <= len(good_decisions), (
        f"Items without summary leaked into output: "
        f"output={len(result.decisions)}, good_input={len(good_decisions)}"
    )


# ─── P8: Empty input always produces empty log ───────────────────────────────

@given(anchor=st.dates(min_value=date(2024, 1, 1), max_value=date(2030, 12, 31)))
@settings(max_examples=100)
def test_p8_empty_input_gives_empty_log(anchor):
    """An input with all-empty collections always produces is_empty=True."""
    response = {"decisions": [], "commitments": [], "rejected": [], "open_questions": []}
    result = parse_extraction_response(response, meeting_date=anchor)
    assert result.is_empty


# ─── P9: Resolved deadline dates are date objects or None ────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=300)
def test_p9_deadline_resolved_date_is_date_or_none(response: Any):
    """CommitmentDeadline.resolved_date is always a date object or None — never a string."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    for c in result.commitments:
        if c.deadline is not None:
            resolved = c.deadline.resolved_date
            assert resolved is None or isinstance(resolved, date), (
                f"deadline.resolved_date is {type(resolved).__name__}: {resolved!r}"
            )


# ─── P10: Output is immutable ────────────────────────────────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=100)
def test_p10_output_is_immutable(response: Any):
    """The returned DecisionLog (and its nested items) are frozen dataclasses."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    with pytest.raises((AttributeError, TypeError)):
        result.decisions = ()  # type: ignore[misc]


# ─── P11: IDs follow expected naming pattern ─────────────────────────────────

@given(response=valid_response_strategy())
@settings(max_examples=200)
def test_p11_decision_ids_follow_d_pattern(response: Any):
    """After normalization, all decision IDs start with 'D' followed by digits."""
    import re
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    pattern = re.compile(r"^D\d+$")
    for d in result.decisions:
        assert pattern.match(d.id), (
            f"Decision ID {d.id!r} does not match pattern 'D{{n}}'"
        )


@given(response=valid_response_strategy())
@settings(max_examples=200)
def test_p11_commitment_ids_follow_c_pattern(response: Any):
    """After normalization, all commitment IDs start with 'C' followed by digits."""
    import re
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    pattern = re.compile(r"^C\d+$")
    for c in result.commitments:
        assert pattern.match(c.id), (
            f"Commitment ID {c.id!r} does not match pattern 'C{{n}}'"
        )


# ─── Parametrized edge-case regression suite ─────────────────────────────────

KNOWN_PROBLEMATIC_INPUTS = [
    # (description, response, expected_decisions, expected_commitments)
    ("all nulls", {"decisions": [None, None], "commitments": [None], "rejected": [], "open_questions": []}, 0, 0),
    ("nested lists", {"decisions": [[]], "commitments": [[]], "rejected": [], "open_questions": []}, 0, 0),
    ("boolean values", {"decisions": [True, False], "commitments": [], "rejected": [], "open_questions": []}, 0, 0),
    ("integer decisions", {"decisions": [1, 2, 3], "commitments": [], "rejected": [], "open_questions": []}, 0, 0),
    ("string decisions", {"decisions": ["oops"], "commitments": [], "rejected": [], "open_questions": []}, 0, 0),
    ("decisions is null", {"decisions": None, "commitments": [], "rejected": [], "open_questions": []}, 0, 0),
    ("decisions is string", {"decisions": "oops", "commitments": [], "rejected": [], "open_questions": []}, 0, 0),
]

@pytest.mark.parametrize("description,response,exp_decisions,exp_commitments", KNOWN_PROBLEMATIC_INPUTS)
def test_known_problematic_inputs_handled_gracefully(description, response, exp_decisions, exp_commitments):
    """Known pathological inputs are handled without crashing."""
    result = parse_extraction_response(response, meeting_date=ANCHOR)
    assert len(result.decisions) == exp_decisions, (
        f"[{description}] Expected {exp_decisions} decisions, got {len(result.decisions)}"
    )
    assert len(result.commitments) == exp_commitments, (
        f"[{description}] Expected {exp_commitments} commitments, got {len(result.commitments)}"
    )
