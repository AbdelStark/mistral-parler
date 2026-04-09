Feature: Output formats and report rendering
  As a user sharing meeting outcomes
  I want decision logs in different formats that render well and look professional
  So that I can share them via Slack, embed them in Notion, or post screenshots

  Background:
    Given a decision log with 3 decisions, 5 commitments, 1 rejection, 2 open questions

  # ─── Markdown ─────────────────────────────────────────────────────────────────

  @smoke
  Scenario: Markdown output has correct structure
    When I render the decision log as Markdown
    Then the output contains a "# Decision Log" heading
    And it contains a "## ✅ Decisions" section
    And it contains a "## → Commitments" section
    And it contains a "## ❓ Open Questions" section
    And it contains a "## ✗ Rejected" section
    And all 3 decisions appear in the Decisions section
    And all 5 commitments appear in the Commitments section

  Scenario: Commitment table in Markdown has correct columns
    When I render the decision log as Markdown
    Then the Commitments section contains a table with columns "Owner", "Action", "Deadline"
    And each commitment row has all three fields populated or shows "—" for null deadline

  Scenario: Resolved deadline shown as date in Markdown
    Given a commitment with deadline resolved_date "2026-04-17" and raw "next Friday"
    When I render as Markdown
    Then the table shows "2026-04-17" not "next Friday"

  Scenario: Unresolvable relative deadline shown as raw string
    Given a commitment with deadline resolved_date null and raw "sometime next week"
    When I render as Markdown
    Then the table shows "sometime next week" with a "?" indicator

  Scenario: Transcript excerpts in Markdown collapsible section
    When I render as Markdown with include_quotes=True
    Then there is a <details> section with transcript quotes for each item

  # ─── HTML ─────────────────────────────────────────────────────────────────────

  @smoke
  Scenario: HTML output is self-contained (no external dependencies)
    When I render the decision log as HTML
    Then the output is a single HTML file
    And no <link rel="stylesheet"> tags reference external URLs
    And no <script src=...> tags reference external URLs
    And no web fonts are loaded from external origins
    And the file renders correctly with the "file://" protocol

  Scenario: HTML timeline shows decisions at correct timestamps
    Given decisions at 14:02, 22:41, and 38:15
    When I render as HTML
    Then the timeline visualization places markers at those timestamps
    And the timeline is proportional to total meeting duration

  Scenario: HTML report looks correct when the decision log is empty
    Given a decision log with 0 items
    When I render as HTML
    Then the HTML renders without error
    And the output shows "No decisions were extracted from this meeting"

  Scenario: HTML screenshot dimensions are appropriate for Twitter sharing
    When I render as HTML
    Then the summary card (first viewport) fits within 1200×630 pixels
    And the most important information (totals, title, date) is visible without scrolling

  # ─── JSON ─────────────────────────────────────────────────────────────────────

  @smoke
  Scenario: JSON output validates against DecisionLog schema
    When I render the decision log as JSON
    Then the output is valid JSON
    And it conforms to the DecisionLog JSON schema (all required fields present)
    And decision IDs follow the pattern "D1", "D2", ...
    And commitment IDs follow the pattern "C1", "C2", ...

  Scenario: JSON timestamps are in seconds from meeting start (float)
    Given a decision at 14 minutes and 2 seconds
    When I render as JSON
    Then the decision timestamp_s is approximately 842.0

  Scenario: JSON for empty decision log has empty arrays not null
    Given a decision log with no rejections and no open questions
    When I render as JSON
    Then "rejected" is [] not null
    And "open_questions" is [] not null
