Feature: Voxtral transcription
  As a user of parler
  I want my audio files accurately transcribed by Voxtral
  So that I have high-quality text to extract decisions from

  Background:
    Given a valid MISTRAL_API_KEY is configured
    And the Voxtral API is reachable

  # ─── Happy paths ────────────────────────────────────────────────────────────

  @smoke
  Scenario: Transcribe a short MP3 file
    Given an audio file "fixtures/short-fr-meeting.mp3" of duration 5 minutes
    When I run "parler transcribe fixtures/short-fr-meeting.mp3"
    Then the command exits with code 0
    And the transcript contains at least 50 words
    And the transcript has a primary language field set to "fr"
    And each segment has a start_s less than its end_s

  @smoke
  Scenario: Transcribe a WAV file
    Given an audio file "fixtures/short-en-call.wav" of duration 3 minutes
    When I run "parler transcribe fixtures/short-en-call.wav"
    Then the command exits with code 0
    And the transcript primary language is "en"

  Scenario: Auto-detect language when --lang is not specified
    Given an audio file "fixtures/french-only.mp3"
    When I run "parler transcribe fixtures/french-only.mp3" without --lang
    Then the transcript primary_language is "fr"
    And the output contains "Detected language: French"

  Scenario: Respect explicit language hint
    Given an audio file "fixtures/bilingual-meeting.mp3"
    When I run "parler transcribe fixtures/bilingual-meeting.mp3 --lang fr,en"
    Then the transcript detected_languages includes "fr"
    And the transcript detected_languages includes "en"

  @slow
  Scenario: Transcribe a long MP4 recording requiring chunking
    Given an audio file "fixtures/long-meeting.mp4" of duration 75 minutes
    When I run "parler transcribe fixtures/long-meeting.mp4"
    Then the command exits with code 0
    And the transcript duration_s is approximately 4500 seconds (within 5%)
    And the transcript segments form a continuous timeline with no gaps over 2 seconds
    And each segment has monotonically increasing start_s values

  Scenario: Write transcript to specified output file
    Given an audio file "fixtures/short-fr-meeting.mp3"
    When I run "parler transcribe fixtures/short-fr-meeting.mp3 --output /tmp/test-transcript.json --format json"
    Then a file "/tmp/test-transcript.json" is created
    And the file is valid JSON
    And the JSON contains a "segments" array

  # ─── Caching ────────────────────────────────────────────────────────────────

  @smoke
  Scenario: Cache is used on second run of same file
    Given an audio file "fixtures/short-fr-meeting.mp3"
    And the transcript cache is empty
    When I run "parler transcribe fixtures/short-fr-meeting.mp3" for the first time
    Then a cache entry is created for the audio file's content hash
    When I run "parler transcribe fixtures/short-fr-meeting.mp3" for the second time
    Then no Voxtral API call is made
    And the command completes in under 2 seconds

  Scenario: Cache miss when file content changes
    Given a cached transcript for "fixtures/short-fr-meeting.mp3"
    When the audio file is modified (e.g., re-encoded at different bitrate)
    And I run "parler transcribe fixtures/short-fr-meeting.mp3"
    Then a new Voxtral API call is made
    And the old cache entry is not used

  # ─── Chunking ───────────────────────────────────────────────────────────────

  @slow
  Scenario: Chunked audio produces a seamless transcript
    Given an audio file "fixtures/45min-meeting.mp3" requiring 5 chunks
    When I run "parler transcribe fixtures/45min-meeting.mp3"
    Then the transcript has no duplicate sentences at chunk boundaries
    And timestamps are monotonically increasing across the full transcript
    And the total transcript duration matches the audio duration within 2%

  Scenario: Chunk split prefers silence over mid-speech
    Given an audio file with a 5-second silence at 9:30 and hard chunk boundary at 10:00
    When the AudioIngester computes the chunk plan with max_chunk_s=600
    Then the chunk split point is at approximately 9:30 (within 60 seconds of silence)
    And not at exactly 10:00

  # ─── Quality signals ─────────────────────────────────────────────────────────

  Scenario: Low confidence transcript triggers warning
    Given an audio file "fixtures/noisy-recording.mp3" with expected average confidence below 0.5
    When I run "parler transcribe fixtures/noisy-recording.mp3"
    Then a warning is printed: "Low transcription confidence"
    And the command still exits with code 0

  Scenario: Very low confidence prompts user confirmation (interactive)
    Given an audio file "fixtures/very-noisy.mp3" with expected average confidence below 0.3
    And the TTY is interactive
    When I run "parler transcribe fixtures/very-noisy.mp3" without --yes
    Then a prompt is shown: "Transcription confidence is very low"
    And the user can respond "N" to abort
    And the command exits with code 1 if the user responds "N"

  Scenario: Very low confidence does not prompt with --yes
    Given an audio file "fixtures/very-noisy.mp3" with expected average confidence below 0.3
    When I run "parler transcribe fixtures/very-noisy.mp3 --yes"
    Then no prompt is shown
    And the transcript is produced regardless of confidence
