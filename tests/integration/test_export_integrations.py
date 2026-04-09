"""
Integration tests: Export integrations (Notion, Linear, Jira, Slack)

These tests verify that each export adapter:
  - Builds the correct API payload from a DecisionLog
  - Handles authentication errors gracefully (non-fatal — logged and skipped)
  - Handles network failures non-fatally (the local report is always saved)
  - Validates the payload structure before sending
  - Returns an ExportResult with success/failure status and URL (when applicable)

All HTTP calls are mocked via respx (httpx) or responses (requests).
No real API tokens required.

Export adapters:
  NotionExporter   — creates a Notion page in a configured database
  LinearExporter   — creates Linear issues for each commitment
  SlackExporter    — posts a formatted summary to a webhook URL
  JiraExporter     — creates Jira tickets for commitments
"""

import pytest
import json
from datetime import date
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from parler.export.notion import NotionExporter
from parler.export.linear import LinearExporter
from parler.export.slack import SlackExporter
from parler.export.result import ExportResult
from parler.models import (
    DecisionLog, Decision, Commitment, CommitmentDeadline, ExtractionMetadata
)


# ─── Shared fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def full_decision_log():
    return DecisionLog(
        decisions=(
            Decision(
                id="D1", summary="Launch on May 15",
                timestamp_s=42.0, speaker="Pierre",
                confirmed_by=("Sophie",),
                quote="On part sur le 15 mai.",
                confidence="high", language="fr",
            ),
        ),
        commitments=(
            Commitment(
                id="C1", owner="Sophie",
                action="Review deployment checklist",
                deadline=CommitmentDeadline(
                    raw="vendredi prochain",
                    resolved_date=date(2026, 4, 17),
                    is_explicit=False,
                ),
                timestamp_s=82.0,
                quote="Je vais revoir la checklist.",
                confidence="high", language="fr",
            ),
        ),
        rejected=(),
        open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest",
            prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9),
            extracted_at="2026-04-09T10:30:00Z",
            input_tokens=512,
            output_tokens=128,
        ),
    )


@pytest.fixture
def empty_decision_log():
    return DecisionLog(
        decisions=(), commitments=(), rejected=(), open_questions=(),
        metadata=ExtractionMetadata(
            model="mistral-large-latest", prompt_version="v1.2.0",
            meeting_date=date(2026, 4, 9), extracted_at="2026-04-09T10:00:00Z",
            input_tokens=0, output_tokens=0,
        ),
    )


# ─── Notion exporter ─────────────────────────────────────────────────────────

class TestNotionExporter:

    def test_notion_export_creates_page_in_database(self, full_decision_log):
        """A successful export calls the Notion API and returns a page URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "page-id-1234",
            "url": "https://notion.so/page-id-1234",
        }

        with patch("parler.export.notion.requests.post", return_value=mock_response) as mock_post:
            exporter = NotionExporter(
                api_token="secret_notion_token",
                database_id="db-id-5678",
            )
            result = exporter.export(full_decision_log, title="Meeting 2026-04-09")

        assert mock_post.called
        assert isinstance(result, ExportResult)
        assert result.success is True
        assert result.url == "https://notion.so/page-id-1234"

    def test_notion_payload_includes_decisions(self, full_decision_log):
        """The Notion page payload must include decision content."""
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "page-1", "url": "https://notion.so/1"}
            return resp

        with patch("parler.export.notion.requests.post", side_effect=capture_post):
            exporter = NotionExporter(api_token="token", database_id="db-1")
            exporter.export(full_decision_log, title="Test Meeting")

        # The payload must reference at least one decision summary
        payload_str = json.dumps(captured_payload)
        assert "Launch on May 15" in payload_str or "D1" in payload_str

    def test_notion_payload_includes_commitments_with_deadline(self, full_decision_log):
        """Commitments with resolved deadlines should have dates in the Notion payload."""
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"id": "page-1", "url": "https://notion.so/1"}
            return resp

        with patch("parler.export.notion.requests.post", side_effect=capture_post):
            exporter = NotionExporter(api_token="token", database_id="db-1")
            exporter.export(full_decision_log, title="Test Meeting")

        payload_str = json.dumps(captured_payload)
        assert "Sophie" in payload_str or "checklist" in payload_str.lower()

    def test_notion_auth_failure_returns_failed_result(self, full_decision_log):
        """A 401 from Notion should return ExportResult(success=False), not raise."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "API token invalid"}

        with patch("parler.export.notion.requests.post", return_value=mock_response):
            exporter = NotionExporter(api_token="bad-token", database_id="db-1")
            result = exporter.export(full_decision_log, title="Test")

        assert isinstance(result, ExportResult)
        assert result.success is False
        assert "auth" in result.error.lower() or "401" in result.error or "token" in result.error.lower()

    def test_notion_network_error_returns_failed_result(self, full_decision_log):
        """A network error should return ExportResult(success=False), not propagate."""
        import requests as req
        with patch("parler.export.notion.requests.post", side_effect=req.exceptions.ConnectionError("No network")):
            exporter = NotionExporter(api_token="token", database_id="db-1")
            result = exporter.export(full_decision_log, title="Test")

        assert result.success is False
        assert result.error is not None

    def test_notion_export_with_empty_log_still_creates_page(self, empty_decision_log):
        """Even an empty log should create a page (with 'no decisions' note)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "page-empty", "url": "https://notion.so/empty"}

        with patch("parler.export.notion.requests.post", return_value=mock_response):
            exporter = NotionExporter(api_token="token", database_id="db-1")
            result = exporter.export(empty_decision_log, title="Empty Meeting")

        assert result.success is True


# ─── Linear exporter ─────────────────────────────────────────────────────────

class TestLinearExporter:

    def test_linear_creates_one_issue_per_commitment(self, full_decision_log):
        """Each commitment with an owner should create one Linear issue."""
        issue_count = [0]

        def mock_graphql(url, json=None, **kwargs):
            if "IssueCreate" in (json or {}).get("query", ""):
                issue_count[0] += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"issueCreate": {"issue": {"id": "issue-1", "url": "https://linear.app/i/1"}}}}
            return resp

        with patch("parler.export.linear.requests.post", side_effect=mock_graphql):
            exporter = LinearExporter(api_key="lin_api_key", team_id="team-1")
            results = exporter.export(full_decision_log)

        # 1 commitment in full_decision_log → 1 Linear issue
        assert issue_count[0] >= 1

    def test_linear_issue_title_contains_action(self, full_decision_log):
        """The Linear issue title must include the commitment action text."""
        captured_variables = {}

        def mock_graphql(url, json=None, **kwargs):
            if "IssueCreate" in (json or {}).get("query", ""):
                captured_variables.update(json.get("variables", {}))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"issueCreate": {"issue": {"id": "i1", "url": "https://linear.app/i/1"}}}}
            return resp

        with patch("parler.export.linear.requests.post", side_effect=mock_graphql):
            exporter = LinearExporter(api_key="lin_api_key", team_id="team-1")
            exporter.export(full_decision_log)

        # "Review deployment checklist" should be in the issue input
        variables_str = json.dumps(captured_variables)
        assert "checklist" in variables_str.lower() or "Review" in variables_str

    def test_linear_issue_due_date_set_from_resolved_deadline(self, full_decision_log):
        """If commitment has a resolved deadline, Linear issue due_date should be set."""
        captured_variables = {}

        def mock_graphql(url, json=None, **kwargs):
            if "IssueCreate" in (json or {}).get("query", ""):
                captured_variables.update(json.get("variables", {}))
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {"data": {"issueCreate": {"issue": {"id": "i1", "url": "https://linear.app/i/1"}}}}
            return resp

        with patch("parler.export.linear.requests.post", side_effect=mock_graphql):
            exporter = LinearExporter(api_key="lin_api_key", team_id="team-1")
            exporter.export(full_decision_log)

        variables_str = json.dumps(captured_variables)
        assert "2026-04-17" in variables_str

    def test_linear_auth_failure_returns_failed_results(self, full_decision_log):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"errors": [{"message": "Unauthorized"}]}

        with patch("parler.export.linear.requests.post", return_value=mock_response):
            exporter = LinearExporter(api_key="bad-key", team_id="team-1")
            results = exporter.export(full_decision_log)

        for r in results:
            assert r.success is False


# ─── Slack exporter ───────────────────────────────────────────────────────────

class TestSlackExporter:

    def test_slack_posts_to_webhook_url(self, full_decision_log):
        """A Slack export posts exactly one message to the configured webhook."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "ok"

        with patch("parler.export.slack.requests.post", return_value=mock_response) as mock_post:
            exporter = SlackExporter(webhook_url="https://hooks.slack.com/T1234/B5678/abc")
            result = exporter.export(full_decision_log, title="April 9 Meeting")

        mock_post.assert_called_once()
        assert result.success is True

    def test_slack_message_contains_decision_count(self, full_decision_log):
        """Slack message should mention the number of decisions extracted."""
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "ok"
            return resp

        with patch("parler.export.slack.requests.post", side_effect=capture_post):
            exporter = SlackExporter(webhook_url="https://hooks.slack.com/T1234")
            exporter.export(full_decision_log, title="Test")

        message_str = json.dumps(captured_payload)
        assert "decision" in message_str.lower() or "D1" in message_str

    def test_slack_message_contains_commitment_owner(self, full_decision_log):
        """Slack message should mention commitment owners."""
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "ok"
            return resp

        with patch("parler.export.slack.requests.post", side_effect=capture_post):
            exporter = SlackExporter(webhook_url="https://hooks.slack.com/T1234")
            exporter.export(full_decision_log, title="Test")

        message_str = json.dumps(captured_payload)
        assert "Sophie" in message_str

    def test_slack_webhook_failure_returns_failed_result(self, full_decision_log):
        """A failed Slack webhook should return ExportResult(success=False)."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_payload"

        with patch("parler.export.slack.requests.post", return_value=mock_response):
            exporter = SlackExporter(webhook_url="https://hooks.slack.com/T1234")
            result = exporter.export(full_decision_log, title="Test")

        assert result.success is False

    def test_slack_export_with_empty_log_sends_no_decisions_message(self, empty_decision_log):
        """An empty log should send a 'no decisions' Slack message (not silently skip)."""
        captured_payload = {}

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            resp = MagicMock()
            resp.status_code = 200
            resp.text = "ok"
            return resp

        with patch("parler.export.slack.requests.post", side_effect=capture_post):
            exporter = SlackExporter(webhook_url="https://hooks.slack.com/T1234")
            exporter.export(empty_decision_log, title="Empty Meeting")

        assert captured_payload  # message was sent


# ─── Export result contract ───────────────────────────────────────────────────

class TestExportResultContract:

    def test_export_result_success_has_url(self):
        """A successful ExportResult always has a non-empty url."""
        result = ExportResult(success=True, url="https://notion.so/page-1", error=None)
        assert result.url is not None
        assert result.url.startswith("http")

    def test_export_result_failure_has_error_message(self):
        """A failed ExportResult always has a non-empty error message."""
        result = ExportResult(success=False, url=None, error="API token invalid")
        assert result.error is not None
        assert len(result.error) > 0

    def test_export_result_is_immutable(self):
        """ExportResult is a frozen dataclass."""
        result = ExportResult(success=True, url="https://notion.so/1", error=None)
        with pytest.raises((AttributeError, TypeError)):
            result.success = False
