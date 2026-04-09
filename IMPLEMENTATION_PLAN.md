# parler — Implementation Plan

**Version**: 0.2.0
**Date**: 2026-04-09
**Purpose**: convert the implementation-ready specification baseline into an executable,
test-driven delivery plan

This plan assumes the canonical contracts in [`SPEC.md`](./SPEC.md) and
[`SDD.md`](./SDD.md).

---

## 1. Delivery Strategy

Implementation should proceed in narrow, test-backed vertical slices.

The critical path is:

1. lock the canonical data model and config model
2. build local-only pipeline primitives
3. build transcription and quality gating
4. build extraction and rendering
5. build orchestration and CLI
6. add exports and hardening

Do not start with a broad “full pipeline” implementation. That creates immediate drift
between the design and the tests.

---

## 2. Phase 0 — Spec and Test Alignment

### Objective

Bring RFC, BDD, and TDD language into line with the canonical baseline before code
accumulates around contradictory assumptions.

### Work

- sync RFC-0001 through RFC-0005 with `SPEC.md` and `SDD.md`
- normalize terminology:
  - `AudioFile`
  - `Transcript.language`
  - `DecisionLog`
  - `Rejection.summary`
  - checkpoint as sensitive serialized artefact
- update BDD and TDD references that assume:
  - LLM-only diarization
  - hash-only checkpoints
  - oversimplified cache keys

### Primary references

- RFC-0001 to RFC-0005
- `features/README.md`
- `tests/README.md`

### Exit criteria

- one canonical definition per major concept
- zero unresolved contradictions in cache, checkpoint, or data-model semantics

---

## 3. Phase 1 — Core Skeleton and Models

### Objective

Create the minimal package skeleton and canonical typed models.

### Modules

- `parler/models.py`
- `parler/errors.py`
- `parler/config.py`
- `parler/util/hashing.py`
- `parler/util/serialization.py`

### Tests to turn green first

- `tests/unit/test_config_loading.py`
- model-shape portions of:
  - `tests/conftest.py`
  - `tests/unit/test_pipeline_orchestration.py`
  - `tests/unit/test_report_rendering.py`

### Key design requirements

- frozen dataclasses where the spec says immutable
- secret scrubbing in config repr/str
- format validation and cross-field config validation

### Risks

- draft tests currently reference more than one model shape
- import-path drift between `parler.attribution.*` and `parler.transcription.attributor`

### Exit criteria

- canonical models and config load successfully
- no placeholder schema ambiguity remains in core types

---

## 4. Phase 2 — Audio Ingestion and Local Utilities

### Objective

Implement deterministic local preprocessing.

### Modules

- `parler/audio/ingester.py`
- `parler/audio/ffmpeg.py`
- `parler/util/retry.py`

### Tests

- `tests/unit/test_audio_ingestion.py`
- `tests/integration/test_retry_behavior.py`

### Relevant RFCs and features

- RFC-0001
- RFC-0002
- `features/transcription.feature`
- `features/error_handling.feature`

### Notes

- use magic bytes before extension-based detection
- keep FFmpeg invocation isolated and shell-safe
- compute content hash during ingestion

### Exit criteria

- all ingestion unit tests pass
- retry primitive exists and is reused, not reimplemented ad hoc later

---

## 5. Phase 3 — Transcription, Quality, and Caching

### Objective

Deliver a production-grade transcription subsystem with correct caching and quality
evaluation.

### Modules

- `parler/transcription/transcriber.py`
- `parler/transcription/assembly.py`
- `parler/transcription/cache.py`
- `parler/transcription/quality.py`

### Tests

- `tests/unit/test_chunk_assembly.py`
- `tests/unit/test_transcript_quality.py`
- `tests/integration/test_voxtral_integration.py`
- `tests/integration/test_cache_behavior.py`
- relevant scenarios in:
  - `features/transcription.feature`
  - `features/multilingual.feature`
  - `features/caching.feature`

### Key implementation decisions

- encode transcription request mode explicitly
- implement cache key fingerprinting as a pure function
- keep chunk assembly pure and separately testable
- run quality evaluation immediately after transcript construction

### Vendor-specific requirements

- default model currently `voxtral-mini-latest`
- handle diarization-capable responses
- handle current vendor constraint between timestamps and explicit language mode

### Exit criteria

- transcription cache behavior is correct
- quality gates are available to the orchestrator
- transcript assembly invariants are stable

---

## 6. Phase 4 — Speaker Resolution

### Objective

Resolve speaker identities conservatively and transparently.

### Modules

- `parler/attribution/attributor.py`
- `parler/attribution/resolver.py`
- `parler/prompts/attribution.py`

### Tests

- `tests/unit/test_speaker_attribution.py`
- `features/speaker_attribution.feature`

### Relevant RFC

- RFC-0004

### Design notes

- preserve segment IDs and timestamps
- support participant hints
- prefer vendor diarization labels when present
- only use transcript-based inference as fallback or enrichment
- anonymization must be deterministic within a run

### Exit criteria

- attribution improves speaker labels without mutating transcript structure
- unknowns remain unknown instead of being force-filled

---

## 7. Phase 5 — Extraction Parser, Deadline Resolver, and Extractor

### Objective

Implement the semantic heart of the product.

### Modules

- `parler/extraction/parser.py`
- `parler/extraction/deadline_resolver.py`
- `parler/extraction/extractor.py`
- `parler/extraction/cache.py`
- `parler/prompts/extraction.py`

### Tests

- `tests/unit/test_decision_extraction_parsing.py`
- `tests/unit/test_deadline_resolution.py`
- `tests/unit/test_deadline_resolution_parametrized.py`
- `tests/property/test_deadline_resolver_properties.py`
- `tests/property/test_parsing_properties.py`
- `tests/integration/test_mistral_extraction.py`
- `features/decision_extraction.feature`
- multilingual extraction scenarios in `features/multilingual.feature`

### Relevant RFC

- RFC-0003

### Design notes

- parser must never crash on malformed JSON
- parser must normalize IDs, confidence, language, and quotes
- extractor must use JSON mode
- extraction cache key must include meeting-date-dependent deadline resolution inputs
- multi-pass extraction should be introduced only after single-pass logic is stable

### Exit criteria

- parser and resolver logic are heavily covered
- multi-pass behavior is correct and deduplicates safely
- extraction output is consistently typed and renderable

---

## 8. Phase 6 — Rendering and Export Mapping

### Objective

Turn the canonical log into shareable artefacts and export payloads.

### Modules

- `parler/rendering/renderer.py`
- `parler/rendering/templates/*`
- `parler/export/notion.py`
- `parler/export/linear.py`
- `parler/export/jira.py`
- `parler/export/slack.py`

### Tests

- `tests/unit/test_report_rendering.py`
- `tests/integration/test_export_integrations.py`
- `features/output_formats.feature`

### Relevant RFC

- RFC-0005

### Design notes

- render from canonical `DecisionLog`, never from raw LLM output
- HTML must be self-contained and escape hostile content
- export adapters must not be mixed into renderer logic

### Exit criteria

- Markdown, HTML, and JSON outputs are stable
- exporter failures are isolated and do not abort local render success

---

## 9. Phase 7 — Orchestrator and CLI

### Objective

Connect the pieces into one resumable user-facing tool.

### Modules

- `parler/pipeline/state.py`
- `parler/pipeline/orchestrator.py`
- `parler/cli.py`

### Tests

- `tests/unit/test_pipeline_orchestration.py`
- remaining config tests
- `features/cli_interface.feature`
- `features/error_handling.feature`

### Relevant RFC

- RFC-0001

### Design notes

- orchestrator owns sequencing and failure isolation
- checkpoint writing occurs after meaningful stage completion
- cost estimate runs before first billable API call
- CLI exit codes must map cleanly to error classes

### Exit criteria

- full mocked pipeline runs from CLI
- checkpoint/resume behavior is correct
- `--cost-estimate`, `--resume`, `--no-diarize`, `--format`, and cache commands work

---

## 10. Phase 8 — Full-System Verification

### Objective

Turn the suite from module confidence into product confidence.

### Tests

- `tests/e2e/test_full_pipeline_fr.py`
- `tests/e2e/test_full_pipeline_bilingual.py`
- `tests/e2e/test_earnings_call.py`
- `tests/benchmarks/test_performance.py`

### Requirements

- real API key guard
- explicit cost budget
- fixture-backed regression checks
- benchmark baselines committed and reviewed

### Exit criteria

- E2E happy paths pass reliably
- performance is within stated budgets

---

## 11. RFC-to-Implementation Mapping

| RFC | Primary implementation areas |
|-----|-------------------------------|
| RFC-0001 | `config.py`, `pipeline/orchestrator.py`, `pipeline/state.py`, `cli.py` |
| RFC-0002 | `audio/ingester.py`, `transcription/transcriber.py`, `transcription/assembly.py`, `transcription/quality.py`, `transcription/cache.py` |
| RFC-0003 | `extraction/extractor.py`, `extraction/parser.py`, `extraction/deadline_resolver.py`, `extraction/cache.py`, `prompts/extraction.py` |
| RFC-0004 | `attribution/attributor.py`, `attribution/resolver.py`, `prompts/attribution.py` |
| RFC-0005 | `rendering/renderer.py`, `rendering/templates/*`, `export/*.py` |

---

## 12. Missing Tests to Add During Implementation

The existing draft suite is strong, but not complete.

Add:

- contract tests for transcription request strategy selection
- cache key fingerprint unit tests as pure functions
- checkpoint permission tests where platform supports mode assertions
- adversarial HTML escaping tests for renderer
- extraction cache invalidation tests for meeting date changes
- explicit tests for vendor diarization pass-through and fallback behavior

---

## 13. Definition of Done

`parler` is implementation-complete only when:

1. the canonical spec is reflected in code
2. the test matrix is traceable and green
3. the CLI is usable end-to-end on at least French and bilingual fixtures
4. cache, checkpoint, and error behavior are production-safe
5. the remaining open questions are deliberate product decisions, not unresolved design drift
