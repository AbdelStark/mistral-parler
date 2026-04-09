Feature: CLI interface
  As a developer or analyst
  I want a clear, predictable CLI with well-defined exit codes and helpful output
  So that parler can be scripted and integrated into workflows

  # ─── Core commands ────────────────────────────────────────────────────────────

  @smoke
  Scenario: parler process runs the full pipeline
    Given a valid MISTRAL_API_KEY and audio file "fixtures/short-fr-meeting.mp3"
    When I run "parler process fixtures/short-fr-meeting.mp3"
    Then the command exits with code 0
    And a file "short-fr-meeting-decisions.md" is created in the current directory
    And the file contains at least one section heading

  @smoke
  Scenario: parler transcribe runs transcription only
    Given a valid MISTRAL_API_KEY and audio file "fixtures/short-fr-meeting.mp3"
    When I run "parler transcribe fixtures/short-fr-meeting.mp3 --output /tmp/t.json --format json"
    Then the command exits with code 0
    And "/tmp/t.json" is valid JSON
    And "/tmp/t.json" does NOT contain "decisions" key (decisions not extracted)

  Scenario: parler report re-renders from cached state
    Given a ".parler-state.json" checkpoint exists with a completed decision_log
    When I run "parler report --from-state .parler-state.json --format html"
    Then the command exits with code 0
    And no Voxtral API call is made
    And no Mistral extraction API call is made
    And an HTML report is produced

  Scenario: parler cache list shows cached transcripts
    Given transcript cache contains 3 entries
    When I run "parler cache list"
    Then the output shows 3 entries with file hash, date, and size
    And the command exits with code 0

  Scenario: parler cache clear removes all cached transcripts
    Given transcript cache contains 3 entries
    When I run "parler cache clear --yes"
    Then the cache directory contains 0 entries
    And the command exits with code 0

  # ─── Output path and format ──────────────────────────────────────────────────

  Scenario: Default output path derived from input filename
    Given audio file "weekly-sync-2026-04-09.mp3" in the current directory
    When I run "parler process weekly-sync-2026-04-09.mp3"
    Then output file is "weekly-sync-2026-04-09-decisions.md"
    And the original audio file is not modified

  Scenario: Explicit --output path used when provided
    When I run "parler process meeting.mp3 --output /tmp/my-report.html"
    Then output file is "/tmp/my-report.html"
    And the format is HTML (inferred from .html extension)

  Scenario: --format overrides extension-based format detection
    When I run "parler process meeting.mp3 --output /tmp/report.txt --format markdown"
    Then output is written as Markdown to "/tmp/report.txt"

  Scenario: --format json writes valid JSON to stdout when no --output given
    When I run "parler process meeting.mp3 --format json"
    Then the stdout output is valid JSON
    And it contains "decisions", "commitments", "rejected", "open_questions" keys

  # ─── Cost estimation ─────────────────────────────────────────────────────────

  @smoke
  Scenario: --cost-estimate prints cost without making API calls
    Given audio file "fixtures/45min-meeting.mp3"
    When I run "parler process fixtures/45min-meeting.mp3 --cost-estimate"
    Then the command exits with code 0
    And the output contains an estimated total cost in USD
    And no Voxtral API call is made
    And no Mistral API call is made
    And the .parler-state.json checkpoint is NOT created

  Scenario: Cost confirmation prompt shown above threshold
    Given config.cost.confirm_above_usd is 1.00
    And the estimated run cost is $1.50
    When I run "parler process long-meeting.mp3" interactively
    Then a prompt shows: "Estimated cost: $1.50. Continue? [y/N]"
    And the user can respond "N" to abort

  Scenario: --yes skips cost confirmation
    Given the estimated run cost is $2.00
    When I run "parler process long-meeting.mp3 --yes"
    Then no cost confirmation prompt is shown
    And the run proceeds

  # ─── Participants ─────────────────────────────────────────────────────────────

  Scenario: --participants improves speaker attribution
    When I run:
      """
      parler process meeting.mp3 \
        --participants "Pierre Martin (Tech Lead), Sophie Legrand (Product), Marc (Eng)"
      """
    Then the participant list is passed to the SpeakerAttributor
    And role references like "the Tech Lead" resolve to "Pierre Martin"

  # ─── Exit codes ──────────────────────────────────────────────────────────────

  Scenario Outline: Exit codes for different error conditions
    When I run "parler process <input>" and <condition> occurs
    Then the command exits with code <code>

    Examples:
      | input | condition | code |
      | nonexistent.mp3 | file not found | 2 |
      | meeting.mp3 | MISTRAL_API_KEY not set | 3 |
      | meeting.mp3 | API authentication fails (401) | 4 |
      | meeting.mp3 | rate limit exceeded after max retries | 4 |
      | meeting.mp3 | output directory not writable | 6 |
