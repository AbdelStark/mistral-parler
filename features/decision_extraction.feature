Feature: Decision extraction
  As a meeting participant who needs to track outcomes
  I want parler to accurately extract decisions, commitments, rejections, and open questions
  So that I have a structured record of what was agreed without reading a full transcript

  Background:
    Given a valid MISTRAL_API_KEY is configured
    And a transcript is available for extraction

  # ─── Decisions ──────────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit decision extracted correctly
    Given a transcript containing: "We've decided to launch on May 15th. That's the date."
    When I run decision extraction on the transcript
    Then exactly one Decision is extracted
    And the Decision summary contains "May 15" or "launch"
    And the Decision confidence is "high"
    And the Decision quote contains the original sentence

  Scenario: Discussion is not extracted as a decision
    Given a transcript containing: "We should probably think about moving the launch date."
    When I run decision extraction on the transcript
    Then no Decision is extracted for the launch date topic
    # "should probably think about" is exploration, not a decision

  Scenario: Implicit consensus decision extracted with medium confidence
    Given a transcript containing: "So that means we'll go with option B then, right?"
    And the response is: "Yes, let's do that."
    When I run decision extraction on the transcript
    Then a Decision is extracted with confidence "medium"
    And the Decision summary mentions "option B"

  Scenario: Decision confirmed by multiple speakers has higher credibility
    Given a transcript where Pierre says "On part sur Mistral Small"
    And Sophie responds "Oui, je suis d'accord"
    And Marc says "Parfait pour moi"
    When I run decision extraction
    Then a Decision is extracted with confirmed_by containing "Sophie" and "Marc"

  Scenario: Decision reversed later in meeting is not included
    Given a transcript where at 10:00 "We decided to use GPT-4"
    And at 35:00 "Actually we're switching to Mistral Large, not GPT-4"
    When I run decision extraction
    Then no Decision mentioning "GPT-4" is in the final decision log
    And a Decision mentioning "Mistral Large" is present

  # ─── Commitments ────────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit commitment with owner and deadline extracted
    Given a transcript containing: "Sophie, can you review the checklist by Friday?"
    And Sophie responds: "Yes, I'll have it done by Friday."
    When I run decision extraction
    Then a Commitment is extracted with owner "Sophie"
    And the Commitment action contains "checklist" or "review"
    And the Commitment deadline raw contains "Friday"

  Scenario: Commitment without explicit deadline extracted with null deadline
    Given a transcript containing: "I'll handle the legal review."
    When I run decision extraction
    Then a Commitment is extracted
    And the Commitment deadline is null
    And the Commitment confidence is "medium" (no deadline = lower commitment signal)

  Scenario: Relative deadline resolved to absolute date
    Given today's date is 2026-04-09 (Wednesday)
    And a transcript containing: "I'll have it done by next Friday"
    When I run decision extraction with meeting_date=2026-04-09
    Then a Commitment is extracted
    And the Commitment deadline resolved_date is "2026-04-17"
    And the Commitment deadline is_explicit is False

  Scenario: Explicit date deadline resolved correctly
    Given a transcript containing: "Submit the proposal by April 14th"
    And the meeting year is 2026
    When I run decision extraction
    Then a Commitment is extracted
    And the Commitment deadline resolved_date is "2026-04-14"
    And the Commitment deadline is_explicit is True

  Scenario: French relative deadline resolved
    Given today's date is 2026-04-09
    And a transcript containing: "Je ferai ça vendredi prochain"
    When I run decision extraction with meeting_date=2026-04-09
    Then a Commitment is extracted
    And the Commitment deadline resolved_date is "2026-04-17"

  # ─── Rejections ─────────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit rejection with reason extracted
    Given a transcript containing: "We won't migrate to GPT-4o — the cost and US dependency are unacceptable."
    When I run decision extraction
    Then a Rejection is extracted with proposal containing "GPT-4o"
    And the Rejection reason mentions cost or dependency
    And the Rejection confidence is "high"

  Scenario: Soft rejection is not extracted as a hard rejection
    Given a transcript containing: "I'm not sure GPT-4o is the right choice here..."
    When I run decision extraction
    Then no Rejection is extracted for "GPT-4o"
    # Uncertainty is not a rejection

  Scenario: Deferred item not extracted as rejection
    Given a transcript containing: "Let's table the open-source discussion for next sprint."
    When I run decision extraction
    Then no Rejection is extracted
    And an OpenQuestion may be extracted if the topic is clearly unresolved

  # ─── Open questions ─────────────────────────────────────────────────────────

  @smoke
  Scenario: Unresolved question with stakes extracted
    Given a transcript containing: "We still don't know who handles legal review, and it blocks the launch."
    When I run decision extraction
    Then an OpenQuestion is extracted
    And the OpenQuestion question mentions "legal review"
    And the OpenQuestion stakes mentions "launch" or "blocks"

  Scenario: Resolved question not extracted as open
    Given a transcript containing: "Who owns the budget? — Marc does."
    When I run decision extraction
    Then no OpenQuestion is extracted for "budget ownership"

  # ─── Empty and edge cases ───────────────────────────────────────────────────

  Scenario: Empty transcript produces empty decision log
    Given a transcript containing only: "[silence] [inaudible]"
    When I run decision extraction
    Then the decision log has zero items
    And the command exits with code 0
    And a warning is printed: "No decisions found in transcript"

  Scenario: Multi-pass extraction for very long transcript
    Given a transcript of approximately 30,000 words (about 120 minutes of speech)
    When I run decision extraction
    Then multi-pass extraction is used (2+ Mistral calls)
    And no duplicate decisions appear in the final log
    And decisions from early in the meeting are included alongside decisions from later

  Scenario: Partial JSON response from Mistral handled gracefully
    Given the Mistral API returns a malformed JSON for extraction
    When I run decision extraction
    Then a warning is printed: "Could not fully parse extraction response"
    And any valid fields from the partial response are included
    And the command exits with code 0 (partial results, not failure)
