Feature: Decision and commitment extraction
  As a meeting participant
  I want parler to extract decisions, commitments, rejections, and open questions
  So that I have a structured, actionable record of what was decided and who owns what

  Background:
    Given the Mistral extraction API is mocked
    And the meeting date is 2026-04-09
    And the extraction model is "mistral-large-latest"

  # ─── Decisions ──────────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit decision with speaker confirmation is extracted
    Given a French transcript containing:
      """
      Pierre: On part sur le 15 mai pour le lancement, c'est décidé.
      Sophie: D'accord, je note : lancement le 15 mai.
      """
    When extraction runs
    Then the decision log contains 1 decision
    And decision D1 has summary containing "15 mai" or "May 15"
    And decision D1 has speaker "Pierre"
    And decision D1 has confirmed_by including "Sophie"
    And decision D1 has confidence "high"
    And decision D1 has language "fr"

  Scenario: Statement of fact is NOT extracted as a decision
    Given a French transcript containing:
      """
      Sophie: Le projet est en retard de deux semaines.
      Pierre: Les résultats du Q3 sont dans ce document.
      """
    When extraction runs
    Then the decision log contains 0 decisions
    And the decision log contains 0 commitments

  Scenario: Implicit consensus is extracted as a decision
    Given a French transcript containing:
      """
      Pierre: Donc on s'aligne sur la date du 20 avril ?
      Sophie: Oui, tout à fait.
      Marc: Parfait pour moi.
      """
    When extraction runs
    Then the decision log contains 1 decision
    And decision D1 has confidence "high" or "medium"

  Scenario: A decision reversed later in the meeting is not extracted
    Given a French transcript containing:
      """
      Pierre: On lance en mars.
      [...]
      Sophie: Finalement, le lancement en mars est annulé. On repousse à mai.
      Pierre: D'accord, c'est officiel — lancement en mai.
      """
    When extraction runs
    Then the decision log contains 0 decisions about "mars"
    And the decision log contains 1 decision about "mai"

  # ─── Commitments ────────────────────────────────────────────────────────────

  @smoke
  Scenario: Explicit commitment with relative deadline is extracted and resolved
    Given a French transcript containing:
      """
      Sophie: Je vais revoir la checklist de déploiement avant vendredi prochain.
      """
    When extraction runs with meeting_date=2026-04-09
    Then the decision log contains 1 commitment
    And commitment C1 has owner "Sophie"
    And commitment C1 has action containing "checklist"
    And commitment C1 has deadline.raw "vendredi prochain"
    And commitment C1 has deadline.resolved_date 2026-04-17
    And commitment C1 has deadline.is_explicit false

  Scenario Outline: Deadline resolution for various French and English patterns
    Given a transcript containing a commitment with deadline phrase "<phrase>"
    When extraction runs with meeting_date=<anchor>
    Then the commitment has deadline.resolved_date <expected_date>
    And the commitment has deadline.is_explicit <is_explicit>

    Examples:
      | phrase                  | anchor     | expected_date | is_explicit |
      | vendredi prochain       | 2026-04-09 | 2026-04-17    | false       |
      | demain                  | 2026-04-09 | 2026-04-10    | false       |
      | la semaine prochaine    | 2026-04-09 | 2026-04-13    | false       |
      | fin du mois             | 2026-04-09 | 2026-04-30    | false       |
      | next Friday             | 2026-04-09 | 2026-04-17    | false       |
      | by end of week          | 2026-04-09 | 2026-04-11    | false       |
      | end of month            | 2026-04-09 | 2026-04-30    | false       |
      | 14 avril                | 2026-04-09 | 2026-04-14    | true        |
      | avant le 17 avril       | 2026-04-09 | 2026-04-17    | true        |
      | 2026-04-20              | 2026-04-09 | 2026-04-20    | true        |
      | April 20th              | 2026-04-09 | 2026-04-20    | true        |
      | le 20                   | 2026-04-09 | 2026-04-20    | true        |
      | le 5                    | 2026-04-09 | 2026-05-05    | true        |
      | bientôt                 | 2026-04-09 | null          | false       |
      | dès que possible        | 2026-04-09 | null          | false       |
      | sometime soon           | 2026-04-09 | null          | false       |

  Scenario: Commitment without explicit owner defaults to Unknown
    Given a transcript containing:
      """
      Il faudra envoyer le rapport avant vendredi.
      """
    When extraction runs
    Then the decision log contains 1 commitment
    And commitment C1 has owner "Unknown"

  Scenario: Commitment with implicit owner resolved via participant list
    Given a transcript containing:
      """
      Pierre demande à Sophie d'envoyer le rapport.
      """
    And the participant list is ["Pierre", "Sophie"]
    When extraction runs
    Then commitment C1 has owner "Sophie"

  # ─── Rejections ─────────────────────────────────────────────────────────────

  Scenario: Explicitly rejected proposal is captured in rejected list
    Given a French transcript containing:
      """
      Pierre: Je propose qu'on lance en mars.
      Sophie: Non, c'est impossible. On n'a pas les ressources.
      Pierre: D'accord, on oublie mars.
      """
    When extraction runs
    Then the decision log contains 1 rejected item
    And rejected item R1 has summary containing "mars"

  Scenario: Declined proposal without consensus is not a rejection
    Given a French transcript containing:
      """
      Pierre: On pourrait peut-être lancer en mars ?
      Sophie: Je ne sais pas... c'est compliqué.
      """
    When extraction runs
    Then the decision log contains 0 rejected items

  # ─── Open questions ──────────────────────────────────────────────────────────

  Scenario: Unanswered question is captured as open question
    Given a French transcript containing:
      """
      Pierre: Qui s'occupe de la migration de la base de données ?
      [silence]
      Pierre: On verra ça plus tard.
      """
    When extraction runs
    Then the decision log contains 1 open question
    And open question Q1 has question containing "migration"

  Scenario: Answered question is NOT extracted as open question
    Given a French transcript containing:
      """
      Pierre: Qui s'occupe de la migration ?
      Sophie: C'est moi, je le ferai vendredi.
      """
    When extraction runs
    Then the decision log contains 0 open questions
    And the decision log contains 1 commitment

  # ─── Edge cases ─────────────────────────────────────────────────────────────

  @smoke
  Scenario: Empty transcript produces an empty log
    Given an empty transcript
    When extraction runs
    Then the decision log is empty
    And the command exits with code 0

  Scenario: Very long transcript triggers multi-pass extraction
    Given a transcript with more than 25000 words
    When extraction runs
    Then at least 2 extraction API calls are made
    And the results from all passes are merged and deduplicated

  Scenario: Partially valid JSON response from LLM is handled gracefully
    Given the extraction API returns malformed JSON on the first attempt
    And returns valid JSON on the second attempt
    When extraction runs
    Then extraction completes successfully
    And exactly 2 API calls were made

  Scenario: Low confidence items excluded from output
    Given a transcript where the LLM returns a decision with confidence "low"
    When extraction runs
    Then the decision log contains 0 decisions

  # ─── Confidence normalization ────────────────────────────────────────────────

  Scenario Outline: Confidence values are normalized to valid set
    Given a transcript where the LLM returns confidence "<raw_confidence>"
    When extraction runs
    Then the extracted item has confidence "<normalized>"

    Examples:
      | raw_confidence | normalized |
      | high           | high       |
      | medium         | medium     |
      | low            | [DROPPED]  |
      | very_high      | medium     |
      | 0.9            | medium     |
      | HIGH           | high       |
      | MEDIUM         | medium     |
      |                | medium     |
      | null           | medium     |

  # ─── Language normalization ──────────────────────────────────────────────────

  Scenario Outline: Language codes are normalized to ISO 639-1 lowercase
    Given a transcript where the LLM returns language "<raw_lang>"
    When extraction runs
    Then the extracted item has language "<normalized_lang>"

    Examples:
      | raw_lang | normalized_lang |
      | fr       | fr              |
      | en       | en              |
      | FR       | fr              |
      | French   | fr              |
      | FRENCH   | fr              |
      | english  | en              |
      | English  | en              |
      | de       | de              |
      | unknown  | fr              |
      |          | fr              |

  # ─── ID assignment ────────────────────────────────────────────────────────────

  Scenario: Items without IDs get auto-assigned IDs in order
    Given a transcript with 3 decisions, none with explicit IDs
    When extraction runs
    Then the decisions have IDs "D1", "D2", "D3" in order

  Scenario: Duplicate IDs from the LLM are renumbered
    Given a transcript where the LLM returns two decisions both with id "D1"
    When extraction runs
    Then the decision log contains 2 decisions
    And all decision IDs are unique

  # ─── Quote validation ──────────────────────────────────────────────────────

  Scenario: Empty quote is accepted with a warning in logs
    Given a transcript where the LLM returns a decision with an empty quote
    When extraction runs
    Then the decision log contains 1 decision
    And a warning is logged containing "empty quote"

  Scenario: Quote longer than 500 characters is truncated
    Given a transcript where the LLM returns a decision with a 600-character quote
    When extraction runs
    Then the decision quote is at most 503 characters long
