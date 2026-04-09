Feature: Multilingual audio handling
  As a French-speaking professional working in a bilingual environment
  I want parler to handle French/English code-switching accurately
  So that my multilingual meetings are transcribed and analyzed correctly

  Background:
    Given a valid MISTRAL_API_KEY is configured

  # ─── French-first transcription ─────────────────────────────────────────────

  @smoke @fr
  Scenario: French meeting transcribed accurately
    Given an audio file "fixtures/french-meeting-clean.mp3"
    When I run "parler transcribe fixtures/french-meeting-clean.mp3 --lang fr"
    Then all segments have language "fr"
    And the transcript does not contain garbled French words like "Reza" for "résultats"
    And French names "Pierre", "Sophie", "Marc" are transcribed correctly if present

  @fr
  Scenario: French technical vocabulary preserved
    Given an audio file "fixtures/french-tech-discussion.mp3"
    When I run "parler transcribe fixtures/french-tech-discussion.mp3 --lang fr"
    Then the transcript contains technical terms from the audio accurately
    And French-origin English terms like "rendez-vous" are preserved if spoken

  # ─── Code-switching handling ─────────────────────────────────────────────────

  @multilingual @smoke
  Scenario: French/English code-switching detected
    Given an audio file "fixtures/bilingual-fr-en.mp3" where speakers alternate French and English
    When I run "parler transcribe fixtures/bilingual-fr-en.mp3 --lang fr,en"
    Then the transcript contains segments tagged "fr" and segments tagged "en"
    And at least one segment has code_switch set to true
    And the overall text is coherent without language-switch artifacts

  @multilingual
  Scenario: Code-switch within a single sentence tagged correctly
    Given an audio file "fixtures/codeswitching-sentence.mp3"
    Where a speaker says "On va merger la PR et ensuite on runs the benchmark"
    When I run "parler transcribe fixtures/codeswitching-sentence.mp3 --lang fr,en"
    Then the transcript contains the full sentence without truncation
    And the segment containing this sentence has code_switch set to true
    And both "merger" and "benchmark" appear in the transcript text

  @multilingual
  Scenario: Multiple European language pairs
    Given an audio file "fixtures/fr-de-meeting.mp3" with French and German speakers
    When I run "parler transcribe fixtures/fr-de-meeting.mp3 --lang fr,de"
    Then the transcript detected_languages includes "fr" and "de"
    And segments are tagged with the correct language per speaker

  # ─── Language auto-detection ──────────────────────────────────────────────────

  @multilingual
  Scenario: Auto-detection identifies primary language from first 30 seconds
    Given an audio file "fixtures/french-meeting-english-intro.mp3"
    Where the first 30 seconds are in English but 80% of the recording is in French
    When I run "parler transcribe" without --lang
    Then the primary_language is "fr"
    And detected_languages includes "en"
    And the output informs the user: "Detected languages: French (primary), English"

  Scenario: Auto-detection suggests --lang flag for ambiguous cases
    Given an audio file "fixtures/equal-fr-en.mp3" with approximately equal French and English
    When I run "parler transcribe fixtures/equal-fr-en.mp3" without --lang
    Then the output suggests: "Specify --lang fr,en for better accuracy"

  # ─── Language in decision extraction ────────────────────────────────────────

  @multilingual @fr
  Scenario: French decisions extracted from French transcript
    Given a transcript where a French speaker says "On part sur le 15 mai, c'est décidé"
    When I run decision extraction on that transcript
    Then a Decision is extracted with summary containing "15 mai" or "May 15"
    And the Decision has language "fr"
    And the quote contains the original French text

  @multilingual
  Scenario: Bilingual commitment extracted with correct attribution
    Given a transcript where "Thomas" says "I'll run the benchmarks by Friday" in English
    And "Sophie" says "Je vais revoir le checklist avant mercredi" in French
    When I run decision extraction
    Then a Commitment is extracted with owner "Thomas", action containing "benchmarks", language "en"
    And a Commitment is extracted with owner "Sophie", action containing "checklist", language "fr"

  @multilingual
  Scenario: Rejection stated in French is preserved with original quote
    Given a transcript where a speaker says in French "Non, on ne va pas migrer vers GPT-4o — les coûts sont trop élevés"
    When I run decision extraction
    Then a Rejection is extracted with proposal containing "GPT-4o"
    And the quote field contains the original French sentence
    And the reason contains a reference to cost ("coûts" or "cost")

  @multilingual
  Scenario: Decision log generated for French meeting has French quotes
    Given a 30-minute French meeting "fixtures/french-product-sync.mp3"
    When I run "parler process fixtures/french-product-sync.mp3 --lang fr"
    Then the decision log quotes are in French
    And summaries may be translated to English or remain in French (either is acceptable)
    And the metadata primary_language is "fr"
