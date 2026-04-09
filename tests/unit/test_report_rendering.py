"""
TDD specification: ReportRenderer.render()

The renderer converts a DecisionLog into formatted output artefacts:
  - Markdown: GitHub-flavoured, structured, human-readable
  - HTML:     self-contained (no external CSS/JS), with timeline visualisation
  - JSON:     schema-valid, machine-readable
  - Terminal: Rich-formatted for stdout

Design contract:
  - Input: DecisionLog + RenderConfig
  - Output: rendered string (Markdown/HTML/JSON) or prints to stdout (Terminal)
  - Never raises for any valid DecisionLog
  - Empty log → renders "No decisions recorded" placeholder (not empty document)
  - HTML is self-contained: no <link href="...">, no <script src="...">
  - JSON output validates against the schema in RFC-0005
  - Markdown decisions table has columns: ID | Summary | Owner | Timestamp | Confidence
  - Commitment table has columns: ID | Owner | Action | Deadline | Confidence
"""

import pytest
import json
from datetime import date, timedelta
from parler.rendering.renderer import ReportRenderer, RenderConfig, OutputFormat
from parler.models import (
    DecisionLog, Decision, Commitment, Rejection, OpenQuestion,
    CommitmentDeadline, ExtractionMetadata
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_deadline(raw="vendredi prochain", resolved=date(2026, 4, 17), explicit=False):
    return CommitmentDeadline(raw=raw, resolved_date=resolved, is_explicit=explicit)


def make_log(
    decisions=None,
    commitments=None,
    rejected=None,
    open_questions=None,
):
    return DecisionLog(
        decisions=tuple(decisions or []),
        commitments=tuple(commitments or []),
        rejected=tuple(rejected or []),
        open_questions=tuple(open_questions or []),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:00:00Z",
            input_tokens=1234,
            output_tokens=456,
        ),
    )


SAMPLE_DECISION = Decision(
    id="D1",
    summary="Launch date set to May 15",
    timestamp_s=842.0,
    speaker="Pierre",
    confirmed_by=("Sophie",),
    quote="On part sur le 15 mai, c'est décidé.",
    confidence="high",
    language="fr",
)

SAMPLE_COMMITMENT = Commitment(
    id="C1",
    owner="Sophie",
    action="Review the deployment checklist",
    deadline=make_deadline(),
    timestamp_s=848.0,
    quote="Je vais revoir le checklist avant vendredi prochain.",
    confidence="high",
    language="fr",
)

SAMPLE_REJECTION = Rejection(
    id="R1",
    summary="Soft launch in March rejected due to team capacity",
    timestamp_s=600.0,
    quote="Non, on ne peut pas faire ça en mars.",
    confidence="high",
    language="fr",
)

SAMPLE_OPEN_QUESTION = OpenQuestion(
    id="Q1",
    question="Who owns the migration of the database schema?",
    asked_by="Marc",
    timestamp_s=1200.0,
    quote="Qui s'occupe de la migration?",
    language="fr",
)


# ─── Markdown rendering ───────────────────────────────────────────────────────

class TestMarkdownRendering:

    def test_markdown_contains_decisions_section(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "## Decisions" in result or "# Decisions" in result

    def test_markdown_decisions_table_has_required_columns(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "ID" in result
        assert "Summary" in result
        assert "Confidence" in result

    def test_markdown_decision_id_present(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "D1" in result

    def test_markdown_decision_summary_present(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "May 15" in result or "15 mai" in result or "Launch date" in result

    def test_markdown_contains_commitments_section(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Commitment" in result

    def test_markdown_commitment_deadline_resolved_date_shown(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        # Resolved date April 17 should appear in ISO or human format
        assert "2026-04-17" in result or "April 17" in result or "17 avril" in result

    def test_markdown_commitment_owner_shown(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Sophie" in result

    def test_markdown_empty_log_has_placeholder(self):
        log = make_log()
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "no decisions" in result.lower() or "nothing" in result.lower() or "empty" in result.lower()

    def test_markdown_open_questions_section_present_when_non_empty(self):
        log = make_log(open_questions=[SAMPLE_OPEN_QUESTION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Question" in result or "Open" in result

    def test_markdown_rejection_section_present_when_non_empty(self):
        log = make_log(rejected=[SAMPLE_REJECTION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Rejected" in result or "Rejection" in result

    def test_markdown_quote_included_in_decision(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "décidé" in result or "15 mai" in result

    def test_markdown_speaker_included(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Pierre" in result


# ─── HTML rendering ───────────────────────────────────────────────────────────

class TestHTMLRendering:

    def test_html_output_is_valid_html_document(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        assert "<!DOCTYPE html>" in result or "<html" in result

    def test_html_has_no_external_css_links(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        import re
        external_links = re.findall(r'<link[^>]+href=["\'][^"\']+["\']', result, re.IGNORECASE)
        # No external CDN links allowed
        external_hrefs = [l for l in external_links if "http" in l or "//" in l]
        assert len(external_hrefs) == 0, f"External CSS links found: {external_hrefs}"

    def test_html_has_no_external_js_scripts(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        import re
        external_scripts = re.findall(r'<script[^>]+src=["\'][^"\']+["\']', result, re.IGNORECASE)
        external_srcs = [s for s in external_scripts if "http" in s or "//" in s]
        assert len(external_srcs) == 0, f"External JS found: {external_srcs}"

    def test_html_contains_decision_data(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        assert "D1" in result
        assert "Pierre" in result

    def test_html_empty_log_still_produces_valid_document(self):
        log = make_log()
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        assert "<html" in result or "<!DOCTYPE" in result
        assert len(result) > 100

    def test_html_timeline_section_present(self):
        log = make_log(decisions=[SAMPLE_DECISION], commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        assert "timeline" in result.lower() or "Timeline" in result


# ─── JSON rendering ───────────────────────────────────────────────────────────

class TestJSONRendering:

    def test_json_output_is_valid_json(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)  # must not raise
        assert parsed is not None

    def test_json_has_top_level_decisions_key(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        assert "decisions" in parsed

    def test_json_has_commitments_key(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        assert "commitments" in parsed

    def test_json_decision_has_required_fields(self):
        log = make_log(decisions=[SAMPLE_DECISION])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        d = parsed["decisions"][0]
        for field in ("id", "summary", "confidence", "language"):
            assert field in d, f"Missing field: {field}"

    def test_json_commitment_deadline_is_nested_object(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        c = parsed["commitments"][0]
        assert isinstance(c.get("deadline"), dict)
        assert "resolved_date" in c["deadline"]

    def test_json_resolved_date_is_iso_format(self):
        log = make_log(commitments=[SAMPLE_COMMITMENT])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        resolved = parsed["commitments"][0]["deadline"]["resolved_date"]
        if resolved:
            assert resolved == "2026-04-17"

    def test_json_metadata_block_present(self):
        log = make_log()
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        assert "metadata" in parsed

    def test_json_empty_log_has_empty_arrays(self):
        log = make_log()
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.JSON))
        parsed = json.loads(result)
        assert parsed["decisions"] == []
        assert parsed["commitments"] == []


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestRenderingEdgeCases:

    def test_decision_with_no_timestamp_renders_without_error(self):
        decision = Decision(
            id="D1",
            summary="A timeless decision",
            timestamp_s=None,
            speaker=None,
            confirmed_by=(),
            quote="",
            confidence="medium",
            language="en",
        )
        log = make_log(decisions=[decision])
        for fmt in (OutputFormat.MARKDOWN, OutputFormat.JSON, OutputFormat.HTML):
            result = ReportRenderer().render(log, RenderConfig(format=fmt))
            assert result  # non-empty

    def test_commitment_with_null_deadline_renders_without_error(self):
        commitment = Commitment(
            id="C1",
            owner="Alice",
            action="Send the report",
            deadline=None,
            timestamp_s=None,
            quote="",
            confidence="medium",
            language="en",
        )
        log = make_log(commitments=[commitment])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        assert "Alice" in result

    def test_many_decisions_all_rendered(self):
        decisions = [
            Decision(
                id=f"D{i}", summary=f"Decision {i}", timestamp_s=float(i * 60),
                speaker="Pierre", confirmed_by=(), quote=".", confidence="high", language="fr"
            )
            for i in range(20)
        ]
        log = make_log(decisions=decisions)
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.MARKDOWN))
        for i in range(20):
            assert f"D{i}" in result

    def test_special_characters_in_summary_escaped_in_html(self):
        decision = Decision(
            id="D1",
            summary='Decision with <script>alert("xss")</script> content',
            timestamp_s=None,
            speaker=None,
            confirmed_by=(),
            quote="",
            confidence="high",
            language="en",
        )
        log = make_log(decisions=[decision])
        result = ReportRenderer().render(log, RenderConfig(format=OutputFormat.HTML))
        # Raw script tag must not appear unescaped
        assert '<script>alert(' not in result
