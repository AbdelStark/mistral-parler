---
name: vertical-slice-implementation
description: Build the missing `parler/` runtime package in narrow, test-backed phases. Use when creating new modules, bootstrapping the package skeleton, or turning one implementation-plan phase green without over-scaffolding unrelated domains.
prerequisites: mkdir, pytest, ruff, mypy
---

# Vertical Slice Implementation

<purpose>
Grow `parler/` from nothing into the module map defined by `SDD.md`, one constrained phase at a time. This skill is for implementation work, not contract debates.
</purpose>

<context>
- The repository is spec/test-first. The runtime package does not exist yet.
- `IMPLEMENTATION_PLAN.md` is the build order. Follow it.
- Phase 1 stabilizes models/config/errors. Many later tests depend on that baseline.
- The fastest wrong move is broad scaffolding that hides contract drift behind placeholders.
</context>

<procedure>
1. Pick one phase from `IMPLEMENTATION_PLAN.md`.
2. Read the phase objective, module list, and exact tests listed for that phase.
3. Create only the required package directories and `__init__.py` files for that slice.
4. Implement the smallest complete seam first:
   - Phase 1: `models.py`, `errors.py`, `config.py`, hashing/serialization helpers
   - Phase 2+: pure helpers before adapters; adapters before orchestrator glue
5. Add compatibility shims if import drift blocks the test surface.
6. Run the narrowest tests first; expand only after the slice is green.
7. Finish with `ruff check .` and `mypy parler/`.
</procedure>

<patterns>
<do>
  - Start with immutable dataclasses and typed config objects.
  - Keep pure logic in standalone modules that can be tested without mocks.
  - Use the phase plan to avoid implementing downstream modules early.
  - Prefer one working vertical seam over many placeholder modules.
</do>
<dont>
  - Don't scaffold the full package tree and leave stubbed functions everywhere -> it creates false progress and noisy failures.
  - Don't start with E2E or full-pipeline tests -> stabilize the local contracts first.
  - Don't hide naming drift by rewriting many tests at once -> add a shim and keep moving unless the contract itself is wrong.
</dont>
</patterns>

<examples>
Example: Phase 1 bootstrap

```text
Create:
- parler/__init__.py
- parler/models.py
- parler/errors.py
- parler/config.py
- parler/util/__init__.py
- parler/util/hashing.py
- parler/util/serialization.py

Run:
- pytest tests/unit/test_config_loading.py -q
- pytest tests/unit/test_pipeline_orchestration.py -q -k "ProcessingState or checkpoint"
```

Example: Phase 2 audio slice

```text
Create:
- parler/audio/__init__.py
- parler/audio/ingester.py
- parler/audio/ffmpeg.py
- parler/utils/__init__.py  # compatibility if retry tests still import parler.utils.retry
- parler/utils/retry.py

Run:
- pytest tests/unit/test_audio_ingestion.py -q
- pytest tests/integration/test_retry_behavior.py -q
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| Install/test commands fail before any assertions run | `parler/` is absent | create the minimal package skeleton for the active phase |
| Later-phase tests fail while early-phase tests still fail | slice order violation | go back to the earliest red test in the implementation plan |
| Too many unrelated import errors after scaffolding | over-scaffolded tree with missing exports | shrink scope and add only the imports the active tests need |
</troubleshooting>

<references>
- `IMPLEMENTATION_PLAN.md`: ordered phase plan
- `SDD.md`: canonical module map and data contracts
- `tests/unit/test_config_loading.py`: Phase 1 anchor
- `tests/unit/test_audio_ingestion.py`: Phase 2 anchor
- `tests/unit/test_decision_extraction_parsing.py`: Phase 5 parser anchor
- `tests/unit/test_pipeline_orchestration.py`: orchestrator/state anchor
</references>
