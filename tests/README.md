# Test Specifications

TDD test specifications for `parler`. These define expected behavior at unit,
integration, property, and E2E levels and are implemented with `pytest`.

The canonical contract for these tests is now:

- [`SPEC.md`](../SPEC.md)
- [`SDD.md`](../SDD.md)
- [`TESTING.md`](../TESTING.md)

Where an individual draft test reflects an older assumption, the canonical documents
win and the test should be updated as part of the same change.

## Structure

```
tests/
├── README.md                     (this file)
├── conftest.py                   (shared fixtures — see fixtures/)
├── fixtures/                     (test data and mock responses)
│   ├── audio/                    (sample audio files for tests)
│   ├── transcripts/              (pre-recorded Voxtral responses)
│   ├── extractions/              (pre-recorded Mistral extraction responses)
│   └── decision_logs/            (expected decision log outputs)
├── unit/                         (pure function tests, no API calls)
│   ├── test_audio_ingestion.py
│   ├── test_chunk_assembly.py
│   ├── test_deadline_resolution.py
│   ├── test_decision_extraction_parsing.py
│   ├── test_speaker_attribution.py
│   ├── test_transcript_quality.py
│   ├── test_report_rendering.py
│   └── test_config_loading.py
├── integration/                  (tests that mock external APIs)
│   ├── test_voxtral_integration.py
│   ├── test_mistral_extraction.py
│   ├── test_retry_behavior.py
│   ├── test_cache_behavior.py
│   └── test_export_integrations.py
└── e2e/                          (real API calls, marked @slow)
    ├── test_full_pipeline_fr.py
    ├── test_full_pipeline_bilingual.py
    └── test_earnings_call.py
```

## Running tests

```bash
# All unit tests (fast, no API)
pytest tests/unit/ -v

# All integration tests (mocked API)
pytest tests/integration/ -v

# All BDD scenarios (mocked API)
pytest features/ -v

# Everything except E2E (CI default)
pytest tests/unit tests/integration features/ -v --tb=short

# E2E only (requires MISTRAL_API_KEY, costs ~$0.50)
pytest tests/e2e/ -v -s

# With coverage
pytest tests/unit tests/integration features/ \
  --cov=parler --cov-report=term-missing \
  --cov-fail-under=90
```

## Coverage targets

| Module | Line coverage | Branch coverage |
|--------|-------------|----------------|
| `parler.audio.ingester` | ≥ 95% | ≥ 90% |
| `parler.transcription.transcriber` | ≥ 90% | ≥ 85% |
| `parler.attribution.attributor` | ≥ 90% | ≥ 80% |
| `parler.extraction.extractor` | ≥ 95% | ≥ 90% |
| `parler.extraction.deadline_resolver` | ≥ 98% | ≥ 95% |
| `parler.rendering.renderer` | ≥ 90% | ≥ 85% |
| `parler.pipeline.orchestrator` | ≥ 85% | ≥ 80% |
| `parler.cli` | ≥ 85% | ≥ 75% |

## Test data policy

- Audio fixtures are synthetic (generated with pyttsx3 or gTTS) — never real meeting recordings
- Transcripts in `fixtures/transcripts/` are real Voxtral responses recorded against fixture audio
- No real personal data in any test fixture
- French test fixtures use French text generated from public domain sources (e.g., Zola, Hugo)
