# Test Fixtures

Test data for the parler test suite. All fixtures are synthetic — no real meeting recordings.

## Directory layout

```
fixtures/
├── audio/                          # Synthetic audio files for E2E tests
│   ├── fr_meeting_5min.mp3         # Short French business meeting (gTTS)
│   ├── bilingual_meeting_5min.mp3  # FR/EN code-switching meeting (gTTS)
│   └── silence_30s.wav             # 30 seconds of silence (edge case)
│
├── transcripts/                    # Pre-recorded Voxtral JSON responses
│   ├── fr_meeting_5min.json        # Voxtral output for fr_meeting_5min.mp3
│   └── bilingual_meeting_5min.json # Voxtral output for bilingual fixture
│
├── extractions/                    # Pre-recorded Mistral extraction responses
│   ├── fr_meeting_5min.json        # Raw Mistral chat response (before parsing)
│   └── bilingual_meeting_5min.json
│
└── decision_logs/                  # Expected final DecisionLog outputs
    ├── fr_meeting_5min_expected.json
    └── bilingual_expected.json
```

## Generating fixtures

### Audio fixtures

```bash
# Install gTTS
pip install gTTS

# Generate French fixture
python tests/fixtures/generate_fixtures.py --lang fr --output tests/fixtures/audio/fr_meeting_5min.mp3

# Generate bilingual fixture
python tests/fixtures/generate_fixtures.py --bilingual --output tests/fixtures/audio/bilingual_meeting_5min.mp3
```

### Transcript fixtures (requires real API key)

```bash
# Record real Voxtral responses against fixture audio
MISTRAL_API_KEY=sk-... python tests/fixtures/record_voxtral.py

# This creates tests/fixtures/transcripts/*.json
```

### Extraction fixtures (requires real API key)

```bash
# Record real Mistral extraction responses against transcript fixtures
MISTRAL_API_KEY=sk-... python tests/fixtures/record_extraction.py
```

## Data policy

- Audio fixtures are **synthetic** (gTTS-generated) — never real meeting recordings
- Text content is fictional French business meeting dialogue
- No real personal data (names are fictional: Pierre, Sophie, Marc, Alice)
- French text draws on fictional business scenarios, not real events
- Transcript fixtures are real Voxtral responses recorded against the synthetic audio
- Once recorded, transcripts are committed to git so CI never needs real API keys

## Content of fr_meeting_5min fixture

A 5-minute synthetic French meeting about a product launch:

| Time | Speaker | Content |
|------|---------|---------|
| 0:00 | Pierre | Opens meeting, sets agenda |
| 0:30 | Sophie | Reports deployment status |
| 1:20 | Pierre | **Decision: launch on May 15** |
| 1:50 | Sophie | Confirms decision |
| 2:10 | Pierre | Assigns checklist review to Sophie |
| 2:30 | Sophie | **Commitment: checklist by next Friday** |
| 3:00 | Pierre | Discusses Q2 roadmap |
| 4:00 | Sophie | **Rejection: March launch not feasible** |
| 4:30 | Pierre | **Open question: database migration owner?** |
| 5:00 | Both   | Closing remarks |

## Content of bilingual_meeting_5min fixture

A 5-minute FR/EN code-switching meeting:

| Time | Speaker | Language | Content |
|------|---------|----------|---------|
| 0:00 | Pierre | FR | Opens in French |
| 0:30 | Pierre | FR→EN | Code-switch: Python SDK discussion |
| 1:10 | Alice | EN | English-only response |
| 1:50 | Pierre | FR | **Decision: adopt Python SDK** |
| 2:20 | Pierre | EN | Assigns migration guide to Alice (English) |
| 2:50 | Alice | EN | **Commitment: guide by EOW** |
