"""
pytest-bdd step definitions for decision_extraction.feature

These steps glue the Gherkin scenarios to the actual parler implementation.
They use the same mocks as the integration test layer — no real API calls.
"""

import pytest
import json
from datetime import date
from unittest.mock import patch, MagicMock
from pytest_bdd import given, when, then, parsers

from parler.extraction.extractor import DecisionExtractor
from parler.models import Transcript, TranscriptSegment


# ─── State container ─────────────────────────────────────────────────────────

@pytest.fixture
def extraction_context():
    """Shared mutable state for a single BDD scenario."""
    return {
        "transcript": None,
        "decision_log": None,
        "meeting_date": date(2026, 4, 9),
        "participants": [],
        "api_call_count": 0,
        "api_error_on_first": False,
    }


# ─── Given steps ──────────────────────────────────────────────────────────────

@given("the Mistral extraction API is mocked")
def mistral_api_mocked():
    pass  # mocking happens in the "When" step


@given(parsers.parse("the meeting date is {date_str}"))
def set_meeting_date(extraction_context, date_str):
    year, month, day = date_str.split("-")
    extraction_context["meeting_date"] = date(int(year), int(month), int(day))


@given(parsers.parse('the extraction model is "{model}"'))
def set_model(extraction_context, model):
    extraction_context["model"] = model


@given(parsers.parse("a French transcript containing:\n{text}"))
def french_transcript_containing(extraction_context, text):
    extraction_context["transcript"] = _make_transcript_from_text(text, language="fr")


@given(parsers.parse("a transcript containing:\n{text}"))
def transcript_containing(extraction_context, text):
    extraction_context["transcript"] = _make_transcript_from_text(text, language="fr")


@given("an empty transcript")
def empty_transcript(extraction_context):
    extraction_context["transcript"] = Transcript(
        text="", language="fr", duration_s=0.0, segments=()
    )


@given(parsers.parse("the participant list is {participants_json}"))
def set_participants(extraction_context, participants_json):
    extraction_context["participants"] = json.loads(participants_json)


@given("the extraction API returns malformed JSON on the first attempt")
def api_returns_malformed_json_first(extraction_context):
    extraction_context["api_error_on_first"] = True


@given("returns valid JSON on the second attempt")
def api_returns_valid_on_second(extraction_context):
    pass  # handled in When step


@given(parsers.parse("a transcript with more than {word_count:d} words"))
def long_transcript(extraction_context, word_count):
    long_text = "The project needs attention. " * (word_count // 5 + 100)
    extraction_context["transcript"] = _make_transcript_from_text(long_text, language="en")


# ─── When steps ───────────────────────────────────────────────────────────────

@when("extraction runs")
def extraction_runs(extraction_context):
    _run_extraction(extraction_context)


@when(parsers.parse("extraction runs with meeting_date={date_str}"))
def extraction_runs_with_date(extraction_context, date_str):
    year, month, day = date_str.split("-")
    extraction_context["meeting_date"] = date(int(year), int(month), int(day))
    _run_extraction(extraction_context)


def _run_extraction(ctx):
    call_count = [0]
    api_error_on_first = ctx.get("api_error_on_first", False)

    def mock_chat_complete(**kwargs):
        call_count[0] += 1
        ctx["api_call_count"] = call_count[0]

        if api_error_on_first and call_count[0] == 1:
            return MagicMock(choices=[MagicMock(message=MagicMock(
                content="not json at all"
            ))])

        # Return a minimal valid response
        return MagicMock(choices=[MagicMock(message=MagicMock(
            content=json.dumps({
                "decisions": [], "commitments": [], "rejected": [], "open_questions": []
            })
        ))])

    with patch("parler.extraction.extractor.MistralClient") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.chat.complete.side_effect = mock_chat_complete
        extractor = DecisionExtractor(
            api_key="test-key",
            model=ctx.get("model", "mistral-large-latest"),
        )
        ctx["decision_log"] = extractor.extract(
            ctx["transcript"],
            meeting_date=ctx["meeting_date"],
            participants=ctx.get("participants", []),
        )


# ─── Then steps ───────────────────────────────────────────────────────────────

@then("the decision log is empty")
def decision_log_is_empty(extraction_context):
    assert extraction_context["decision_log"].is_empty

@then("the command exits with code 0")
def exits_with_code_0(extraction_context):
    pass  # No exception raised = exit code 0

@then(parsers.parse("the decision log contains {count:d} decision"))
@then(parsers.parse("the decision log contains {count:d} decisions"))
def decision_log_contains_n_decisions(extraction_context, count):
    actual = len(extraction_context["decision_log"].decisions)
    assert actual == count, f"Expected {count} decisions, got {actual}"

@then(parsers.parse("the decision log contains {count:d} commitment"))
@then(parsers.parse("the decision log contains {count:d} commitments"))
def decision_log_contains_n_commitments(extraction_context, count):
    actual = len(extraction_context["decision_log"].commitments)
    assert actual == count, f"Expected {count} commitments, got {actual}"

@then(parsers.parse("the decision log contains {count:d} rejected item"))
@then(parsers.parse("the decision log contains {count:d} rejected items"))
def decision_log_contains_n_rejected(extraction_context, count):
    actual = len(extraction_context["decision_log"].rejected)
    assert actual == count, f"Expected {count} rejected items, got {actual}"

@then(parsers.parse("the decision log contains {count:d} open question"))
@then(parsers.parse("the decision log contains {count:d} open questions"))
def decision_log_contains_n_questions(extraction_context, count):
    actual = len(extraction_context["decision_log"].open_questions)
    assert actual == count, f"Expected {count} open questions, got {actual}"

@then(parsers.parse("at least {count:d} extraction API calls are made"))
def at_least_n_api_calls(extraction_context, count):
    assert extraction_context["api_call_count"] >= count

@then(parsers.parse("exactly {count:d} API calls were made"))
def exactly_n_api_calls(extraction_context, count):
    assert extraction_context["api_call_count"] == count

@then("extraction completes successfully")
def extraction_completes_successfully(extraction_context):
    assert extraction_context["decision_log"] is not None


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_transcript_from_text(text: str, language: str = "fr") -> Transcript:
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    segments = tuple(
        TranscriptSegment(
            id=i,
            start_s=float(i * 10),
            end_s=float((i + 1) * 10),
            text=line,
            language=language,
            speaker_id=line.split(":")[0].strip() if ":" in line else None,
            speaker_confidence=None,
            confidence=0.9,
            no_speech_prob=0.01,
            code_switch=False,
            words=None,
        )
        for i, line in enumerate(lines)
    )
    return Transcript(
        text=" ".join(s.text for s in segments),
        language=language,
        duration_s=float(len(segments) * 10),
        segments=segments,
    )
