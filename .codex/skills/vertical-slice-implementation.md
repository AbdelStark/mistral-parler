---
name: vertical-slice-implementation
description: Extend the existing `parler/` runtime package in narrow, test-backed phases. Use when implementing the next slice from `IMPLEMENTATION_PLAN.md` without over-scaffolding unrelated domains.
prerequisites: mkdir, pytest, ruff, mypy
---

# Vertical Slice Implementation

<purpose>
Grow the existing `parler/` runtime package through the remaining phases defined by `SDD.md`, one constrained slice at a time. This skill is for implementation work, not contract debates.
</purpose>

<context>
- The repository is spec/test-first. The runtime package already exists through Phase 4.
- `IMPLEMENTATION_PLAN.md` is the build order. Follow it.
- The current stable baseline already includes models, config, audio ingestion, transcription, attribution, orchestration, packaging, and compatibility shims.
- The fastest wrong move is broad scaffolding that hides contract drift behind placeholders or rewrites settled seams.
</context>

<procedure>
1. Pick one phase from `IMPLEMENTATION_PLAN.md`.
2. Read the phase objective, module list, and exact tests listed for that phase.
3. Create only the required package directories and `__init__.py` files for that slice.
4. Implement the smallest complete seam first:
   - extend pure helpers before adapters
   - extend adapters before orchestrator glue
   - prefer adding one real domain module over widening multiple partial stubs
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
Example: Phase 4 attribution slice

```text
Create:
- parler/attribution/__init__.py
- parler/attribution/attributor.py
- parler/attribution/resolver.py
- parler/prompts/attribution.py
- parler/transcription/attributor.py  # compatibility shim

Run:
- pytest tests/unit/test_speaker_attribution.py -q
- pytest tests/unit/test_pipeline_orchestration.py -q -k "attribute or no_diarize"
```

Example: Phase 5 extraction slice

```text
Create:
- parler/extraction/extractor.py
- parler/extraction/parser.py
- parler/extraction/deduper.py
- parler/extraction/deadline_resolver.py

Run:
- pytest tests/unit/test_decision_extraction_parsing.py -q
- pytest tests/integration/test_mistral_extraction.py -q
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| Install/test commands fail before any assertions run | new module/export is missing from the existing package | add only the files and exports required for the active slice |
| Later-phase tests fail while early-phase tests still fail | slice order violation | go back to the earliest red test in the implementation plan |
| Too many unrelated import errors after scaffolding | over-scaffolded tree with missing exports | shrink scope and add only the imports the active tests need |
</troubleshooting>

<references>
- `IMPLEMENTATION_PLAN.md`: ordered phase plan
- `SDD.md`: canonical module map and data contracts
- `tests/unit/test_speaker_attribution.py`: Phase 4 anchor
- `tests/unit/test_decision_extraction_parsing.py`: Phase 5 parser anchor
- `tests/unit/test_pipeline_orchestration.py`: orchestrator/state anchor
</references>
