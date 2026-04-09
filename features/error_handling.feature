Feature: Error handling and recovery
  As a user or operator running parler
  I want clear, actionable error messages and graceful recovery from failures
  So that I can diagnose and fix problems without needing to read source code

  # ─── Input errors ─────────────────────────────────────────────────────────────

  @smoke
  Scenario: Missing audio file produces clear error
    When I run "parler process nonexistent-file.mp3"
    Then the command exits with code 2
    And stderr contains: "File not found: nonexistent-file.mp3"
    And stdout is empty

  Scenario: Unsupported format without FFmpeg produces actionable error
    Given FFmpeg is NOT installed
    When I run "parler process meeting.mkv"
    Then the command exits with code 3
    And stderr contains: "FFmpeg required for .mkv"
    And stderr contains an installation command: "brew install ffmpeg" or "apt install ffmpeg"

  Scenario: Unsupported format with FFmpeg succeeds
    Given FFmpeg IS installed
    When I run "parler process meeting.mkv"
    Then FFmpeg converts the file to a supported format
    And the pipeline continues normally

  # ─── Authentication ───────────────────────────────────────────────────────────

  @smoke
  Scenario: Missing API key produces actionable error
    Given the MISTRAL_API_KEY environment variable is NOT set
    When I run "parler process meeting.mp3"
    Then the command exits with code 3
    And stderr contains: "MISTRAL_API_KEY not set"
    And stderr contains instructions to set the key

  Scenario: Invalid API key returns authentication error
    Given MISTRAL_API_KEY is set to an invalid value "sk-invalid"
    When I run "parler process meeting.mp3"
    Then the command exits with code 4
    And stderr contains: "API authentication failed"

  # ─── Rate limiting ────────────────────────────────────────────────────────────

  Scenario: Rate limit is retried with backoff
    Given the Voxtral API returns HTTP 429 for the first 2 requests
    And the 3rd request succeeds
    When I run "parler transcribe meeting.mp3"
    Then 3 total API attempts are made
    And the command exits with code 0
    And the output shows a retry warning: "Rate limited, retrying..."

  Scenario: Rate limit exhausted after max retries exits cleanly
    Given the Voxtral API returns HTTP 429 for all 3 retry attempts
    When I run "parler transcribe meeting.mp3"
    Then the command exits with code 4
    And stderr contains: "Rate limit exceeded after 3 retries"
    And a .parler-state.json checkpoint is saved if ingestion was completed

  # ─── Partial failures ─────────────────────────────────────────────────────────

  Scenario: Network timeout during long transcription saves checkpoint and suggests --resume
    Given transcription of a 90-minute file is in progress
    And a network timeout occurs after chunk 3 of 8
    When the timeout error is raised
    Then a .parler-state.json checkpoint is saved with the 3 completed chunk transcriptions
    And stderr contains: "Timeout during transcription. Use --resume to continue."
    And the command exits with code 4

  Scenario: --resume picks up from checkpoint after timeout
    Given a .parler-state.json with 3 of 8 chunks completed
    When I run "parler process meeting.mp3 --resume"
    Then chunks 1-3 are loaded from the checkpoint (no API call)
    And chunks 4-8 are transcribed via Voxtral
    And the final transcript covers the full meeting

  # ─── Export failures ──────────────────────────────────────────────────────────

  Scenario: Notion export failure does not fail the whole run
    Given the Notion API is unavailable
    When I run "parler process meeting.mp3 --export notion"
    Then the decision log markdown is saved locally as normal
    And a warning is printed: "Notion export failed: [reason]"
    And the command exits with code 0

  # ─── Low quality warnings ─────────────────────────────────────────────────────

  Scenario: Low confidence warning includes actionable suggestions
    Given average transcription confidence is 0.45
    When transcription completes
    Then a warning is printed mentioning confidence
    And the warning suggests: "Use a higher-quality recording or specify --lang for better results"
    And processing continues normally
