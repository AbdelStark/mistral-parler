---
name: test-driven-delivery
description: Apply the repository's layered verification strategy correctly. Use when adding or fixing tests, deciding what to run, working with pytest-bdd, Hypothesis, benchmarks, or verifying a slice against the fast path without wasting time on E2E too early.
prerequisites: pytest, pytest-bdd, hypothesis, ruff, mypy
---

# Test-Driven Delivery

<purpose>
Use the existing test surface as a delivery system instead of a generic safety net. This skill keeps work traceable from contract to test layer.
</purpose>

<context>
- `TESTING.md` defines six layers: unit, integration, property, BDD, E2E, benchmarks/mutation.
- The canonical fast path is `tests/unit + tests/integration + tests/property + features`.
- E2E is real-cost, real-network, and currently blocked by missing fixture assets unless generated.
- `tests/conftest.py` already defines the canonical sample transcript/log/config fixtures.
</context>

<procedure>
1. Map the change to the relevant capability row in `TESTING.md` or `SPEC.md`.
2. Start with the narrowest local layer that proves the contract:
   - unit for pure logic
   - integration for vendor/export/cache adapters
   - property for parser/resolver invariants
   - BDD for CLI or user-visible behavior
3. Reuse `tests/conftest.py` fixtures before inventing new factories.
4. Run the smallest pytest target first.
5. Widen to the fast path once the narrow target is green.
6. Run E2E only when fixtures and credentials exist, and only after fast-path green.
7. Keep traceability intact when adding new tests.
</procedure>

<patterns>
<do>
  - Use real domain objects in unit tests instead of mocking them.
  - Mock vendor SDK clients, transports, clocks, and sleeps at integration boundaries.
  - Promote Hypothesis-found regressions into concrete regression tests.
  - Keep BDD steps about observable outcomes, not internal helper calls.
</do>
<dont>
  - Don't mock parser, deadline resolver, cache round-trip, or renderer output when those are the actual units under test.
  - Don't use E2E to compensate for missing unit or integration coverage.
  - Don't let a feature land without an obvious traceability path back to the spec.
</dont>
</patterns>

<examples>
Example: fast verification sequence

```bash
pytest tests/unit/test_decision_extraction_parsing.py -q
pytest tests/integration/test_mistral_extraction.py -q
pytest tests/property/test_parsing_properties.py -q
pytest features/decision_extraction.feature -q
ruff check .
mypy parler/
```

Example: CLI-facing change

```text
If changing checkpoint/resume or exit codes:
1. update/fix unit coverage in `tests/unit/test_pipeline_orchestration.py`
2. update/fix BDD coverage in `features/cli_interface.feature` or `features/error_handling.feature`
3. only then consider E2E
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| `pytest tests/e2e` fails before reaching the API | missing fixture audio/transcripts | generate or commit synthetic fixtures first |
| BDD steps import code that does not exist | runtime package still missing or wrong import path | bootstrap the slice or add the required shim |
| Coverage is low despite many passing tests | wrong layer mix or too much mocking | add unit/property coverage on pure logic and reduce mock-heavy assertions |
</troubleshooting>

<references>
- `TESTING.md`: canonical verification policy
- `tests/conftest.py`: shared fixtures and config objects
- `tests/README.md`: test layout and command examples
- `features/README.md`: BDD layout and tags
- `features/steps/extraction_steps.py`: existing pytest-bdd step pattern
- `tests/fixtures/README.md`: fixture generation and data policy
</references>
