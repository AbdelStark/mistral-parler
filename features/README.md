# BDD Feature Specifications

Behavior-Driven Development feature files for `parler`. Written in Gherkin. Implemented with `pytest-bdd`.

## Feature index

| File | Domain | Scenarios |
|------|--------|-----------|
| [transcription.feature](./transcription.feature) | Voxtral API integration | 12 |
| [multilingual.feature](./multilingual.feature) | Language handling and code-switching | 10 |
| [decision_extraction.feature](./decision_extraction.feature) | Decision, commitment, rejection extraction | 14 |
| [speaker_attribution.feature](./speaker_attribution.feature) | Speaker identification | 8 |
| [cli_interface.feature](./cli_interface.feature) | CLI commands and flags | 12 |
| [output_formats.feature](./output_formats.feature) | Report rendering | 8 |
| [caching.feature](./caching.feature) | Cache behavior and invalidation | 7 |
| [error_handling.feature](./error_handling.feature) | Error scenarios and recovery | 10 |

**Total: ~81 scenarios**

## Running BDD tests

```bash
# All BDD scenarios
pytest features/ -v

# Single feature file
pytest features/multilingual.feature -v

# Tagged scenarios only
pytest features/ -v -k "not @slow"

# With real Voxtral API (requires MISTRAL_API_KEY)
pytest features/ -v --real-api
```

## Tags

| Tag | Meaning |
|-----|---------|
| `@smoke` | Fast, critical path — run on every commit |
| `@slow` | Requires real API call — run in CI only |
| `@wip` | Work in progress — excluded from CI |
| `@regression` | Added to prevent a regression |
| `@fr` | French-specific behavior |
| `@multilingual` | Multilingual / code-switching |
