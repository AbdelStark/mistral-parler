Feature: Speaker attribution
  As a user reviewing decisions from a meeting
  I want each statement attributed to the correct speaker
  So that commitments have clear owners and decisions have clear authors

  Background:
    Given a valid MISTRAL_API_KEY is configured
    And a transcript is available for speaker attribution

  # ─── Name extraction ─────────────────────────────────────────────────────────

  @smoke
  Scenario: Named speakers detected from transcript text
    Given a transcript where the text contains "Thanks Pierre" and "as Sophie mentioned"
    When I run speaker attribution
    Then ParticipantCandidates include "Pierre" and "Sophie" with role "speaker" or "mentioned"
    And the name extraction uses no external API — only the transcript text

  Scenario: Role references resolved when participant list provided
    Given a transcript containing "the CTO said" and "notre DG a confirmé"
    And participant list is ["Pierre Martin (CTO)", "Sophie Legrand (DG)"]
    When I run speaker attribution
    Then "the CTO" resolves to "Pierre Martin"
    And "notre DG" resolves to "Sophie Legrand"

  Scenario: Nickname aliases matched to full names
    Given a transcript alternating between "Tom" and "Thomas"
    And participant list is ["Thomas Dubois"]
    When I run speaker attribution
    Then both "Tom" and "Thomas" map to "Thomas Dubois"

  # ─── Turn attribution ─────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit turn attribution from direct address
    Given a transcript segment: "Pierre: On va partir sur le 15 mai."
    When I run speaker attribution
    Then the segment is attributed to "Pierre" with confidence "high"
    And the attribution method is "explicit"

  Scenario: Question-answer pattern attributed correctly
    Given a transcript sequence:
      | segment | text |
      | 1 | "Sophie, can you take the action item?" |
      | 2 | "Sure, I'll have it done by Friday." |
    When I run speaker attribution on segment 2
    Then segment 2 is attributed to "Sophie"
    And the attribution confidence is "medium" or "high"

  Scenario: Ambiguous segment attributed as Unknown
    Given a transcript segment with no contextual clues for speaker identity
    When I run speaker attribution
    Then the segment is attributed to "Unknown"
    And the attribution confidence is "unknown"

  Scenario: Consecutive segments from same speaker merged into a turn
    Given three consecutive segments all attributed to "Pierre" with high confidence
    When the attribution is applied
    Then the three segments are represented as a single turn in the report
    And the turn timestamp spans from segment 1 start to segment 3 end

  # ─── Anonymization ────────────────────────────────────────────────────────────

  Scenario: --anonymize-speakers replaces names with Speaker labels
    Given a transcript with speakers "Pierre" and "Sophie"
    When I run "parler process meeting.mp3 --anonymize-speakers"
    Then the decision log contains "Speaker A" and "Speaker B" instead of real names
    And the mapping is deterministic (same speaker always gets same label within a session)
    And the real names do not appear in any output file

  # ─── Diarization fallback ─────────────────────────────────────────────────────

  Scenario: --no-diarize skips attribution entirely
    Given a transcript with 5 speakers
    When I run "parler process meeting.mp3 --no-diarize"
    Then all segment speaker_id fields are null
    And all commitments in the decision log have owner "Unknown"
    And the command exits with code 0

  Scenario: Attribution degrades gracefully for large noisy meetings
    Given a transcript from a 10-person meeting with frequent cross-talk
    When I run speaker attribution
    Then at least 60% of speech segments have a non-Unknown speaker
    And the attribution does not hallucinate names not present in the participant list or transcript
