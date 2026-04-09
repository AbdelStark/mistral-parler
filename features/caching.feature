Feature: Caching behavior
  As a user running parler multiple times on the same audio
  I want results cached so I don't pay for the same transcription twice
  And I want the cache invalidated correctly when inputs or config changes

  Background:
    Given a valid MISTRAL_API_KEY is configured
    And cache is enabled in config

  @smoke
  Scenario: Transcript cache hit skips Voxtral API call
    Given "fixtures/meeting.mp3" has been transcribed before
    When I run "parler transcribe fixtures/meeting.mp3"
    Then no Voxtral API call is made
    And the output transcript is identical to the cached transcript
    And the command completes in under 3 seconds

  @smoke
  Scenario: Extraction cache hit skips Mistral chat API call
    Given a transcript for "fixtures/meeting.mp3" is cached
    And the extraction for that transcript is also cached
    When I run "parler process fixtures/meeting.mp3"
    Then no Mistral chat API call is made
    And the decision log matches the cached extraction result

  Scenario: Cache miss on modified audio file
    Given "fixtures/meeting.mp3" has a cached transcript
    When the audio file is re-encoded or modified (content hash changes)
    And I run "parler transcribe fixtures/meeting.mp3"
    Then a new Voxtral API call is made
    And the old cache entry is NOT used

  Scenario: Extraction cache invalidated when extraction prompt version changes
    Given a transcript cache entry exists with extraction cached at prompt_version "v1"
    When the extraction prompt is updated to version "v2"
    And I run "parler process fixtures/meeting.mp3"
    Then a new Mistral extraction call is made
    And the result is cached under the new prompt version

  Scenario: Extraction re-run when --lang changes even for same audio
    Given "fixtures/meeting.mp3" was processed with "--lang fr"
    And the transcript is cached with language "fr"
    When I run "parler process fixtures/meeting.mp3 --lang fr,en"
    Then a new Voxtral transcription is made (different language hint = different request)
    # Note: language hint changes the Voxtral request, so cache key is different

  Scenario: Cache key is based on content hash not filename
    Given a file "meeting-copy.mp3" with identical content to "meeting.mp3"
    And "meeting.mp3" has a cached transcript
    When I run "parler transcribe meeting-copy.mp3"
    Then the cached transcript from "meeting.mp3" is used (same content hash)
    And no Voxtral API call is made

  Scenario: parler cache clear --yes empties both caches
    Given the transcript cache has 5 entries
    And the extraction cache has 3 entries
    When I run "parler cache clear --yes"
    Then the transcript cache has 0 entries
    And the extraction cache has 0 entries
    And the command exits with code 0
