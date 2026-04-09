# Testing Philosophy and Standards

> Quality is not a feature — it is a constraint. Every test in this suite exists to
> make a refactoring safe, catch a regression before it reaches a user, or document
> a non-obvious contract. If a test does none of these things, delete it.

---

## Test taxonomy

```
tests/
├── unit/          Pure function tests. No I/O, no mocks of domain logic.
├── integration/   Mocked external APIs. Test adapters and wiring.
├── property/      Hypothesis-driven. Prove invariants over all inputs.
├── e2e/           Real API calls. Marked @slow. Run manually or in nightly CI.
├── benchmarks/    pytest-benchmark. Performance baselines, not correctness.
├── conftest.py    Shared fixtures — transcript factories, mock clients, config.
└── fixtures/      Static test data: audio, API responses, expected logs.
```

```
features/          Gherkin BDD scenarios. Acceptance criteria in plain English.
```

---

## The four test layers

### Layer 1: Unit tests

Scope: one function, one module. No mocks of domain logic — only stub I/O at the
system boundary (file system, network, time).

Rules:
- All unit tests run in < 1 second total (use `--benchmark-max-time` to enforce)
- No `@pytest.mark.slow` inside `tests/unit/`
- No `requests`, `httpx`, `MistralClient` real calls — mock everything
- Use `pytest.approx()` for all float comparisons
- Use `freezegun` for any test that depends on `date.today()` or `datetime.now()`

Anti-patterns to avoid:
```python
# BAD: testing implementation detail, not behaviour
def test_calls_internal_method():
    with patch("parler.extraction.parser._normalize_confidence") as mock:
        parse_extraction_response(...)
    mock.assert_called_once()  # ← testing how it works, not what it does

# GOOD: testing the observable contract
def test_invalid_confidence_normalized_to_medium():
    result = parse_extraction_response({"decisions": [{..., "confidence": "very_high"}]})
    assert result.decisions[0].confidence == "medium"
```

### Layer 2: Integration tests

Scope: one adapter + external boundary (mocked). Tests the request/response contract
with external systems without actually calling them.

Rules:
- All HTTP calls mocked via `unittest.mock.patch` or `respx`
- Test both happy path AND the three failure modes: auth error, network error, bad response
- Integration tests may read/write temp files (use `tmp_path` fixture)
- Never import from `tests/unit/` — share only through `conftest.py`

### Layer 3: Property tests

Scope: invariants that must hold for ALL inputs, not just the hand-crafted fixtures.

Rules:
- All property tests use Hypothesis (`@given`, `@settings`)
- Name properties explicitly in the module docstring: "P1 — never raises", etc.
- `max_examples = 200` minimum (configured in `pyproject.toml`)
- Run property tests in CI (`pytest tests/property/ -v`)
- When Hypothesis finds a failure, add the failing example to the parametrized
  regression table in the corresponding unit test file

### Layer 4: E2E tests

Scope: the full pipeline against real Mistral APIs. Require `MISTRAL_API_KEY`.

Rules:
- Always marked `@pytest.mark.slow`
- Must include explicit `@pytest.mark.skipif` guard for missing `MISTRAL_API_KEY`
- Never write E2E tests that test only one narrow behaviour — test the full pipeline
- Include a regression check against a pre-recorded `expected.json` fixture
- Budget assertions: test that the pipeline completes within a time budget

---

## Fixture factories

The `conftest.py` provides factory functions, not raw objects. Use them:

```python
# BAD: inline construction
seg = TranscriptSegment(id=0, start_s=0.0, end_s=5.0, text="Test",
                        language="fr", speaker_id=None, ...)  # 10 more fields

# GOOD: use the fixture
def test_something(sample_transcript_fr):
    ...
```

For property tests where you need custom shapes, use `hypothesis.strategies` directly
or the strategy helpers in `tests/property/`:

```python
from hypothesis import given
from hypothesis import strategies as st
from tests.property.strategies import decision_strategy

@given(decision=decision_strategy())
def test_decision_property(decision):
    ...
```

---

## Writing parametrized tests

Prefer `@pytest.mark.parametrize` over copy-pasted test functions:

```python
# BAD: copy-paste
def test_next_friday(): ...
def test_next_monday(): ...
def test_next_tuesday(): ...

# GOOD: parametrized table
@pytest.mark.parametrize("raw,expected", [
    ("next Friday", date(2026, 4, 17)),
    ("next Monday", date(2026, 4, 13)),
    ("next Tuesday", date(2026, 4, 14)),
])
def test_next_weekday(raw, expected):
    assert resolve_deadline(raw, ANCHOR, "en") == expected
```

Always provide meaningful `ids`:

```python
@pytest.mark.parametrize("raw,lang,expected", CASES, ids=[
    f"{lang}:{raw!r}" for raw, lang, _ in CASES
])
```

---

## Mocking guidelines

### What to mock
- External API clients (`MistralClient`, `requests.post`, `httpx.AsyncClient`)
- File system when testing non-IO logic (`Path.stat`, `Path.read_bytes`)
- Time (`freezegun.freeze_time`) when testing date-relative logic

### What NOT to mock
- Internal domain logic (parse, resolve, validate)
- Data models (use real `TranscriptSegment`, `Decision`, etc.)
- Standard library (unless testing error handling paths)

### Mock isolation checklist
Before writing a mock:
1. Is this mock testing the right thing, or obscuring the bug?
2. Would a real call be fast and deterministic? (if yes, don't mock)
3. Does this mock make the test pass for wrong reasons? (mock too permissive)

---

## Coverage targets

Run with: `pytest --cov=parler --cov-report=term-missing --cov-fail-under=90`

| Module | Line | Branch |
|--------|------|--------|
| `parler.audio.ingester` | ≥ 95% | ≥ 90% |
| `parler.transcription.*` | ≥ 90% | ≥ 85% |
| `parler.extraction.extractor` | ≥ 95% | ≥ 90% |
| `parler.extraction.deadline_resolver` | ≥ 98% | ≥ 95% |
| `parler.extraction.parser` | ≥ 98% | ≥ 95% |
| `parler.rendering.renderer` | ≥ 90% | ≥ 85% |
| `parler.pipeline.orchestrator` | ≥ 85% | ≥ 80% |
| `parler.cli` | ≥ 85% | ≥ 75% |
| **Total** | **≥ 90%** | **≥ 85%** |

### What 90% line coverage actually means

Line coverage measures whether a line was *executed*, not whether it was *tested correctly*.
A test that calls `parse_extraction_response({})` once can hit 90% coverage while
leaving the entire normalization and validation path untested.

The real coverage metric here is **decision coverage** — every conditional branch
is exercised with both a truthy and falsy case. Use branch coverage (`--branch`) to
enforce this.

---

## Mutation testing

Run monthly or before a major refactor:

```bash
hatch run mutate
# or
mutmut run --paths-to-mutate parler/
mutmut results
```

Target: ≥ 80% mutation score for core modules (`extraction/`, `transcription/`).
A killed mutation = your tests caught the change. A surviving mutation = gap in coverage.

Common surviving mutation patterns to watch for:
- Off-by-one in confidence thresholds (`>= 0.50` vs `> 0.50`)
- Wrong default value (empty list vs empty tuple)
- Missing `is_explicit=False` in deadline construction
- `and` vs `or` in quality verdict logic

---

## CI workflow

```yaml
# .github/workflows/test.yml (excerpt)
jobs:
  unit:
    - pytest tests/unit/ tests/integration/ features/ tests/property/
        --cov=parler --cov-fail-under=90 -x --tb=short

  slow:
    if: github.event_name == 'schedule' || contains(github.event.inputs.run_e2e, 'true')
    - pytest tests/e2e/ -v -s
    env:
      MISTRAL_API_KEY: ${{ secrets.MISTRAL_API_KEY }}

  benchmarks:
    if: github.event_name == 'schedule'
    - pytest tests/benchmarks/ --benchmark-compare=baseline --benchmark-fail-max-time=0.5
```

---

## Adding a new test

Checklist:
- [ ] Is this testing behaviour (observable output) or implementation (internal call)?
- [ ] Does the test name describe what it tests, not how? (`test_missing_summary_dropped` not `test_parsing_path_3`)
- [ ] Is there a failing case as well as a passing case?
- [ ] If testing a boundary: test both sides of the boundary
- [ ] If the function might raise: test that it doesn't raise for invalid inputs
- [ ] If the function returns a mutable type: test that it returns a new object
- [ ] Is this better expressed as a property test (Hypothesis) rather than 5 hand-crafted cases?

---

## Test data policy

- Audio fixtures are **synthetic** (gTTS-generated) — never real meeting recordings
- No real personal data in any fixture (names are fictional: Pierre, Sophie, Marc, Alice)
- Transcript fixtures are real Voxtral responses committed to git once recorded
- API response fixtures are real Mistral responses committed to git once recorded
- Fixture files never contain: real API keys, real personal emails, real company data
