# parler — Canonical Product and Technical Specification

**Version**: 0.2.0
**Status**: Implementation-ready baseline
**Date**: 2026-04-09

This document is the canonical contract for `parler`.

If any RFC, BDD scenario, TDD artifact, README example, or future implementation detail
conflicts with this file or with [`SDD.md`](./SDD.md), `SPEC.md` and `SDD.md` win.

---

## 1. Product Definition

`parler` is a local-first Python CLI and library that converts recorded audio or video
into a structured **Decision Log**.

The product is intentionally not a generic summarizer. Its primary output is a
machine-checkable record of:

- `decisions`: agreed outcomes or explicit decisions
- `commitments`: owned follow-up actions, with deadline when available
- `rejected`: explicit no-go decisions or rejected proposals
- `open_questions`: unresolved questions that materially remain open

The core value proposition is:

1. Better multilingual transcription for French-first and bilingual teams
2. Better extraction of accountable outcomes than generic meeting summaries
3. Local artefacts, resumability, caching, and predictable CLI behavior

---

## 2. Goals and Non-Goals

### 2.1 Goals

- Process recorded meetings, interviews, earnings calls, and similar long-form audio
- Support multilingual and code-switched business audio, especially French/English
- Produce human-readable and machine-readable outputs from the same canonical log
- Be resumable, cache-aware, and scriptable
- Make quality limitations explicit instead of silently hallucinating certainty

### 2.2 Non-Goals for v1

- Live meeting capture or realtime note-taking
- Calendar, email, or OAuth-heavy collaboration features
- Translation as a primary feature
- Biometric speaker identification
- Fully autonomous exports that mutate third-party systems without an explicit user action
- Guaranteed perfect diarization in noisy cross-talk-heavy recordings

---

## 3. Scope Boundaries

### 3.1 First-class inputs

- Local audio files
- Local video files with embedded audio
- Public `http` or `https` URLs
- `stdin` streams for scripted workflows

### 3.2 First-class outputs

- Markdown report
- HTML report
- JSON decision log
- Optional exports to Notion, Linear, Jira, and Slack

### 3.3 Official support envelope

- Recordings up to 3 hours are in the normal support envelope
- Recordings longer than 3 hours may still work through chunking, but are best-effort
- Recordings longer than 4 hours are out of scope for v1

This reflects a deliberate mix of product policy and current vendor capabilities. On
2026-04-09, Mistral’s official audio docs describe offline transcription support up to
3 hours per request for Voxtral Mini Transcribe V2.

---

## 4. External Dependency Baseline

The current draft set was written against older assumptions. The baseline below was
re-checked against official Mistral documentation on 2026-04-09.

### 4.1 Transcription backend

- Endpoint: `POST /v1/audio/transcriptions`
- Default model family: `voxtral-mini-latest`
- Current relevant API features:
  - segment or word timestamps
  - speaker diarization
  - context biasing
  - language parameter

### 4.2 Known vendor constraints to design around

- `timestamp_granularities` and explicit `language` are currently documented as not
  compatible on the offline transcription path
- diarization is supported by the transcription API and should no longer be treated as
  a hypothetical future capability
- JSON mode for extraction is available on `mistral-large-latest` via
  `response_format={"type": "json_object"}`

These constraints are design inputs, not implementation afterthoughts.

---

## 5. End-to-End System Behavior

The canonical pipeline is:

```text
Input Resolution
  -> Audio Ingestion / Normalization
  -> Transcription
  -> Transcript Quality Evaluation
  -> Speaker Resolution
  -> Decision Extraction
  -> Rendering
  -> Optional Export
```

### 5.1 Stage semantics

- `Input Resolution` resolves local file, URL, or `stdin` to a local artefact
- `Audio Ingestion` validates the file, extracts metadata, computes content hash,
  normalizes unsupported containers, and produces an `AudioFile`
- `Transcription` calls Voxtral, handles chunking if necessary, assembles a canonical
  `Transcript`, and writes transcription cache entries
- `Transcript Quality Evaluation` computes objective quality signals and decides whether
  to warn, prompt, or continue
- `Speaker Resolution` converts vendor diarization labels or opaque speaker clusters
  into stable speaker names or `Unknown`
- `Decision Extraction` produces a typed `DecisionLog`
- `Rendering` converts the `DecisionLog` into Markdown, HTML, or JSON
- `Optional Export` maps the `DecisionLog` into external systems without mutating the
  local canonical log

---

## 6. Canonical Data Contracts

This section is intentionally brief. The full type contracts live in [`SDD.md`](./SDD.md).

### 6.1 Audio

Canonical internal artefact: `AudioFile`

Required fields:

- `path`
- `original_path`
- `format`
- `duration_s`
- `sample_rate`
- `channels`
- `size_bytes`
- `content_hash`

### 6.2 Transcript

Canonical internal artefact: `Transcript`

Required fields:

- `text`
- `language`
- `detected_languages`
- `duration_s`
- `segments`
- `model`
- `content_hash`

Notes:

- `language` is the dominant language code for the full transcript
- `detected_languages` is the normalized set of languages observed across segments
- external JSON may expose `primary_language` as a presentation alias, but the
  canonical internal field remains `language`

### 6.3 Decision log

Canonical internal artefact: `DecisionLog`

Top-level sections:

- `decisions`
- `commitments`
- `rejected`
- `open_questions`
- `metadata`

Rules:

- all top-level sections are arrays, never `null`
- item IDs are stable within a rendered artefact and normalized on parse
- invalid or partial LLM objects are dropped, not allowed to poison the entire result

### 6.4 Item semantics

`Decision`
- explicit agreed outcome

`Commitment`
- owned follow-up action
- `owner` and `action` are required
- `deadline` is optional but strongly preferred
- missing owner becomes `Unknown`

`Rejection`
- explicit rejection or explicit decision not to do something
- canonical field is `summary`
- `reason` is optional

`OpenQuestion`
- unresolved question with practical consequence
- `asked_by` and `stakes` are optional but recommended

---

## 7. Functional Requirements

### 7.1 Input and ingestion

- `FR-001`: `parler` must reject obviously non-audio input with actionable error text
- `FR-002`: cache keys must be content-based, never filename-based
- `FR-003`: unsupported containers must be normalized through FFmpeg when available
- `FR-004`: missing FFmpeg must surface an environment error, not a generic failure

### 7.2 Transcription

- `FR-005`: transcription must default to deterministic, resumable behavior
- `FR-006`: the transcription cache key must include every request attribute that can
  change transcript meaning, including at least:
  - audio content hash
  - model identifier
  - diarization mode
  - timestamp mode
  - language-mode strategy fingerprint
  - preprocessing fingerprint
- `FR-007`: transcript assembly must preserve monotonic timestamps and must not emit
  duplicated boundary text
- `FR-008`: transcript quality must be evaluated before downstream extraction

### 7.3 Speaker resolution

- `FR-009`: `parler` must prefer vendor diarization labels when available
- `FR-010`: name resolution may use transcript cues and participant hints, but must
  never hallucinate a name not present in either the transcript, participant list, or
  trusted upstream diarization metadata
- `FR-011`: unresolved speakers must remain `Unknown`

### 7.4 Decision extraction

- `FR-012`: extraction must use structured output mode and schema validation
- `FR-013`: low-confidence extracted items must be excluded from the final log
- `FR-014`: extraction cache keys must include every input that can change semantic
  output, including at least:
  - transcript content hash
  - extraction model
  - prompt version
  - schema version
  - meeting date or deadline resolution anchor
  - extraction policy version

### 7.5 Rendering and exports

- `FR-015`: Markdown, HTML, and JSON must all derive from the same canonical
  `DecisionLog`
- `FR-016`: HTML output must be self-contained
- `FR-017`: export failures must not erase or invalidate local outputs

### 7.6 CLI and resumability

- `FR-018`: the CLI must be deterministic, scriptable, and explicit about exit codes
- `FR-019`: resumability must operate from serialized stage outputs, not by replaying
  opaque side effects
- `FR-020`: checkpoint files must be treated as sensitive local artefacts because they
  can contain transcript and extraction data

---

## 8. Quality and Safety Requirements

### 8.1 Quality gates

- average transcript quality below warning threshold must emit a warning
- transcript quality below hard-stop threshold must prompt unless `--yes` is set
- extraction parse failure must degrade gracefully to partial or empty output

### 8.2 Security and privacy

- API keys must never appear in logs, reprs, or checkpoints
- checkpoints and caches must be written with restrictive local permissions where the
  OS supports them
- no stateful cloud service is part of the v1 architecture

### 8.3 Performance

Target budgets:

- interactive 30-minute meeting: under 2 minutes end-to-end on warm internet path
- warm-cache rerender: under 3 seconds
- rendering: under 2 seconds

---

## 9. Supported CLI Surface

Canonical commands:

```text
parler process <input>
parler transcribe <input>
parler extract --from-state <state.json>
parler report --from-state <state.json>
parler cache list
parler cache clear
parler cache show <key>
```

Canonical high-value flags:

- `--lang`
- `--participants`
- `--output`
- `--format`
- `--no-diarize`
- `--resume`
- `--yes`
- `--cost-estimate`
- `--config`
- `--anonymize-speakers`

The CLI contract in the draft artefacts must be normalized to this surface. Legacy
examples that pass state as a positional argument should be retired in favor of the
explicit `--from-state` form.

---

## 10. Draft Reconciliation Decisions

The review surfaced multiple contradictions. These are the resolved positions.

### 10.1 Canonical naming

- package/distribution name for this repository: `parler`
- license for this repository baseline: MIT
- config primary format: TOML, with YAML and JSON accepted as input formats

### 10.2 Canonical checkpoint semantics

- checkpoint files serialize real stage artefacts, including transcript and extraction
  outputs when available
- checkpoint files are sensitive local state, not “hash-only metadata”

### 10.3 Canonical diarization approach

- v1 is hybrid, not LLM-only
- primary segmentation source:
  1. vendor diarization if available
  2. existing opaque diarization IDs in transcript input
  3. text-only fallback heuristics

### 10.4 Canonical commitment semantics

- deadline is optional
- owner defaults to `Unknown` when absent
- vague, ownerless action language is allowed only if it still meets the extraction
  threshold for a commitment; otherwise it belongs in `open_questions` or is dropped

### 10.5 Canonical cache policy

- cache keys are request-policy fingerprints, not only content hashes plus model names

---

## 11. Traceability Snapshot

| Domain | Canonical RFCs | Primary BDD | Primary TDD |
|--------|----------------|-------------|-------------|
| Pipeline and CLI | RFC-0001 | `features/cli_interface.feature`, `features/error_handling.feature` | `tests/unit/test_pipeline_orchestration.py`, `tests/unit/test_config_loading.py` |
| Transcription | RFC-0002 | `features/transcription.feature`, `features/multilingual.feature`, `features/caching.feature` | `tests/unit/test_audio_ingestion.py`, `tests/unit/test_chunk_assembly.py`, `tests/unit/test_transcript_quality.py`, `tests/integration/test_voxtral_integration.py` |
| Extraction | RFC-0003 | `features/decision_extraction.feature` | `tests/unit/test_decision_extraction_parsing.py`, `tests/unit/test_deadline_resolution.py`, `tests/integration/test_mistral_extraction.py`, `tests/property/test_parsing_properties.py` |
| Speaker resolution | RFC-0004 | `features/speaker_attribution.feature` | `tests/unit/test_speaker_attribution.py` |
| Rendering and export | RFC-0005 | `features/output_formats.feature` | `tests/unit/test_report_rendering.py`, `tests/integration/test_export_integrations.py` |

---

## 12. Exit Criteria for “Spec Complete”

The specification baseline is considered complete only when:

1. `SPEC.md`, `SDD.md`, and `TESTING.md` agree on the canonical data model
2. every cache, checkpoint, and config contract is defined exactly once
3. every draft RFC is either synchronized to the baseline or explicitly marked as
   superseded detail
4. every major feature area has an implementation phase and test plan

That is the standard this repository should now operate under.
