# parler — Software Design Document

**Version**: 0.2.0
**Status**: Implementation-ready baseline
**Date**: 2026-04-09

This document defines the canonical software design for `parler`.

It resolves the main inconsistencies present in the draft artefacts:

- one canonical internal data model
- one canonical cache-key policy
- one explicit checkpoint model
- one explicit contract for current Mistral API constraints and capabilities

---

## 1. Design Principles

### 1.1 Deterministic where it matters

- configuration loading is deterministic
- cache keys are stable and fully derived from semantic inputs
- extraction uses structured output mode and parser normalization

### 1.2 Explicit degradation

`parler` must degrade visibly, not silently:

- unknown speaker remains `Unknown`
- unresolved deadline remains `None`
- malformed LLM items are dropped with warnings
- low transcript quality emits warnings or hard-stop prompts

### 1.3 Local artefacts are first-class

The local filesystem is part of the product design:

- cache is deliberate, inspectable state
- checkpoint is deliberate, inspectable state
- reports are durable outputs

### 1.4 Thin external boundary, strong internal normalization

Vendor APIs, exports, and CLI parsing are adapters. Internal logic runs on typed,
normalized models.

---

## 2. Canonical Module Map

```text
parler/
  __init__.py
  cli.py
  config.py
  errors.py
  models.py
  prompts/
    extraction.py
    attribution.py
  audio/
    ingester.py
    ffmpeg.py
  transcription/
    transcriber.py
    assembly.py
    cache.py
    quality.py
  attribution/
    attributor.py
    resolver.py
  extraction/
    extractor.py
    parser.py
    cache.py
    deadline_resolver.py
  rendering/
    renderer.py
    templates/
  export/
    notion.py
    linear.py
    jira.py
    slack.py
  pipeline/
    orchestrator.py
    state.py
  util/
    hashing.py
    serialization.py
    retry.py
```

Compatibility shims may be added for draft test imports such as
`parler.transcription.attributor`.

---

## 3. Architecture Overview

```text
CLI / Python API
  -> Config Loader
  -> PipelineOrchestrator
       -> AudioIngester
       -> VoxtralTranscriber
       -> TranscriptQualityChecker
       -> SpeakerAttributor
       -> DecisionExtractor
       -> ReportRenderer
       -> Export adapters
```

The orchestrator owns sequencing, checkpointing, cache interactions, and failure
isolation. Individual components are intentionally narrow.

---

## 4. Canonical Data Model

### 4.1 Audio

```python
@dataclass(frozen=True)
class AudioFile:
    path: Path
    original_path: Path | None
    format: str
    duration_s: float
    sample_rate: int
    channels: int
    size_bytes: int
    content_hash: str
```

Notes:

- `content_hash` is `sha256(file_bytes)[:16]`
- `original_path` is populated when FFmpeg normalization creates a new artefact

### 4.2 Transcript

```python
@dataclass(frozen=True)
class TranscriptWord:
    word: str
    start_s: float
    end_s: float
    probability: float


@dataclass(frozen=True)
class TranscriptSegment:
    id: int
    start_s: float
    end_s: float
    text: str
    language: str
    speaker_id: str | None
    speaker_confidence: Literal["high", "medium", "low", "unknown"] | None
    confidence: float
    no_speech_prob: float
    code_switch: bool
    words: tuple[TranscriptWord, ...] | None


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    detected_languages: tuple[str, ...]
    duration_s: float
    segments: tuple[TranscriptSegment, ...]
    model: str
    content_hash: str
```

Important aliases:

- `language` is the canonical internal field for dominant language
- `primary_language` may exist as a property or serialized alias

### 4.3 Decision log

```python
@dataclass(frozen=True)
class CommitmentDeadline:
    raw: str
    resolved_date: date | None
    is_explicit: bool


@dataclass(frozen=True)
class Decision:
    id: str
    summary: str
    timestamp_s: float | None
    speaker: str | None
    confirmed_by: tuple[str, ...]
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class Commitment:
    id: str
    owner: str
    action: str
    deadline: CommitmentDeadline | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class Rejection:
    id: str
    summary: str
    reason: str | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class OpenQuestion:
    id: str
    question: str
    asked_by: str | None
    stakes: str | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class ExtractionMetadata:
    model: str
    prompt_version: str
    meeting_date: date | None
    extracted_at: str
    input_tokens: int
    output_tokens: int
    pass_count: int
    parse_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionLog:
    decisions: tuple[Decision, ...]
    commitments: tuple[Commitment, ...]
    rejected: tuple[Rejection, ...]
    open_questions: tuple[OpenQuestion, ...]
    metadata: ExtractionMetadata
```

Derived properties:

- `DecisionLog.total_items`
- `DecisionLog.is_empty`

### 4.4 Processing state

```python
@dataclass(frozen=True)
class ProcessingState:
    audio_file: AudioFile | None
    transcript: Transcript | None
    attributed_transcript: Transcript | None
    decision_log: DecisionLog | None
    report: str | None
    completed_stages: frozenset["PipelineStage"]
    checkpoint_path: Path | None
```

This shape intentionally matches the existing orchestration tests better than the older
hash-only draft.

---

## 5. Component Contracts

### 5.1 Config loader

Responsibilities:

- merge defaults, config file, env vars, and CLI overrides
- validate cross-field constraints
- scrub secrets from `repr` and `str`

Canonical precedence:

1. built-in defaults
2. config file
3. environment
4. CLI overrides

Accepted config formats:

- TOML preferred
- YAML accepted
- JSON accepted

### 5.2 AudioIngester

Responsibilities:

- validate input existence and type
- detect file format by magic bytes first, extension second
- compute file size and content hash
- run FFmpeg normalization for unsupported containers
- probe duration, sample rate, and channel count

Must raise:

- `InputError` for bad input
- `EnvironmentError` for missing FFmpeg when conversion is required

### 5.3 VoxtralTranscriber

Responsibilities:

- build and execute transcription requests
- apply bounded retries
- write and read transcript cache
- chunk long audio when request mode or operational policy demands it
- assemble chunk outputs into a canonical transcript

#### 5.3.1 Request strategy abstraction

The implementation must hide current vendor constraints behind an internal request mode:

- `timestamp_first`
- `language_first`

Default mode: `timestamp_first`

Reason:

- Mistral currently documents `timestamp_granularities` and explicit `language` as
  incompatible on the offline path

This must be explicit in code and test fixtures, not hardcoded implicitly.

#### 5.3.2 Diarization policy

When transcription-mode and vendor support allow it, request diarization from Voxtral.
If diarization is unavailable or disabled, preserve any existing upstream `speaker_id`
values and fall back to later name resolution heuristics.

### 5.4 TranscriptQualityChecker

Responsibilities:

- compute duration-weighted mean confidence
- compute no-speech ratio
- identify contiguous low-confidence spans
- emit `OK`, `WARN`, or `POOR`

This is a pure local component and must never raise.

### 5.5 SpeakerAttributor

Responsibilities:

- normalize opaque speaker labels into stable names
- use participant hints when present
- extract names from transcript cues
- preserve segment IDs and timing
- support deterministic anonymization

Important rule:

- attribution may improve names but must not collapse transcript segments
- “speaker turns” are a rendering concept, not a mutation of the canonical transcript

### 5.6 DecisionExtractor

Responsibilities:

- build structured extraction prompts
- invoke chat completion in JSON mode
- perform single-pass or multi-pass extraction
- validate, normalize, and filter raw items
- resolve deadlines against meeting date
- write and read extraction cache

Important rule:

- parser normalization is part of the product contract, not a convenience layer

### 5.7 ReportRenderer

Responsibilities:

- render Markdown, HTML, and JSON from the same `DecisionLog`
- escape unsafe content in HTML
- preserve empty sections with explicit placeholders where appropriate

### 5.8 Export adapters

Responsibilities:

- translate canonical log into target-specific payloads
- isolate export failures from local output success

---

## 6. Cache Contracts

### 6.1 Transcript cache key

The draft cache key of `audio_hash + model` is too weak.

Canonical transcript cache key fingerprint must include:

- audio content hash
- transcription model
- request mode
- diarization enabled/disabled
- timestamp granularity mode
- preprocessing fingerprint
- context bias fingerprint
- any explicit vendor parameter that can alter transcript semantics

### 6.2 Extraction cache key

The draft key of `transcript_hash + prompt_version` is also too weak.

Canonical extraction cache key fingerprint must include:

- transcript content hash
- extraction model
- prompt version
- schema version
- meeting date anchor
- extraction policy version
- normalization policy version

### 6.3 Cache storage rules

- stored as JSON on disk
- expired entries are cache misses, not hard failures
- cache clear supports all entries or one entry
- cache read/write operations must be atomic at file level

---

## 7. Checkpoint Contract

### 7.1 Content

Checkpoint files serialize real stage outputs:

- `audio_file`
- `transcript`
- `attributed_transcript`
- `decision_log`
- `completed_stages`

### 7.2 Security stance

Checkpoint files are sensitive because they may contain transcript text and extracted
meeting content. Therefore:

- default filename: `.parler-state.json`
- default location: current working directory unless explicitly overridden
- file mode should be as restrictive as the platform allows
- CLI help and docs must describe checkpoint sensitivity clearly

### 7.3 Resume rules

- resume is valid only if current audio content hash matches checkpoint audio hash
- completed stages are skipped only when their serialized artefacts are present and valid
- rendering is always replayed from canonical state

---

## 8. Error Model

Use project-specific names that do not shadow Python built-ins.

```python
class ParlerError(Exception): ...

class InputError(ParlerError): ...
class EnvironmentError(ParlerError): ...
class ConfigError(ParlerError): ...
class APIError(ParlerError): ...
class ProcessingError(ParlerError): ...
class OutputError(ParlerError): ...
class ExportError(OutputError): ...
```

Do not define a custom `FileNotFoundError` class. That decision in the earlier draft was
needlessly confusing.

Exit-code mapping:

- `2`: input/configuration of user-supplied artefact
- `3`: environment or missing dependency
- `4`: API/auth/rate-limit/network
- `5`: processing failure after valid input
- `6`: output/export write failure

---

## 9. Configuration Schema

High-level config groups:

- `transcription`
- `chunking`
- `attribution`
- `extraction`
- `cache`
- `output`
- `cost`

Notable corrections to earlier drafts:

- primary config filename is `parler.toml`, not `.parlerrc.json`
- env vars may use `MISTRAL_API_KEY` or `PARLER_API_KEY`
- `cost.max_usd` is the canonical total-cost cap field

Cross-field constraints:

- `overlap_s < max_chunk_s`
- cost caps must be non-negative
- output format must be one of `markdown`, `html`, `json`
- extraction multi-pass threshold must be positive

---

## 10. State Machine

```text
IDLE
  -> INGEST
  -> TRANSCRIBE
  -> QUALITY_CHECK
  -> ATTRIBUTE
  -> EXTRACT
  -> RENDER
  -> EXPORT
  -> DONE
```

Failure behavior:

- `INGEST`, `TRANSCRIBE`, and `EXTRACT` are fatal
- `ATTRIBUTE` is soft-failable and may degrade to `Unknown`
- `EXPORT` is soft-failable and must not invalidate a successful local render

---

## 11. Observability

Required observable events:

- stage start
- stage completion with duration
- cache hit/miss
- retry event
- quality warning
- parse warning
- export failure

Required logging guarantees:

- redact secrets
- avoid logging raw transcript by default
- allow opt-in verbose diagnostics

---

## 12. Security and Privacy Notes

Earlier drafts understated the sensitivity of local state. The corrected position is:

- caches and checkpoints may contain PII or confidential business content
- the user remains responsible for local storage hygiene
- the software must not pretend these artefacts are harmless metadata

Recommended defaults:

- no telemetry
- no background sync
- no hidden upload beyond explicit transcription/extraction requests

---

## 13. Design Risks to Manage

### 13.1 Vendor capability drift

Transcription API behavior is vendor-defined and changing. Guardrails:

- adapter layer isolates Mistral SDK specifics
- model names and request strategy are configuration, not string literals everywhere

### 13.2 Extraction over-assertion

The biggest product risk is false certainty. Guardrails:

- low-confidence items dropped
- quote support required
- parser normalization conservative by default

### 13.3 Test drift

The current repository already shows drift between RFCs, feature files, and unit tests.
Guardrail:

- every implementation phase must update traceability and keep contracts synchronized

---

## 14. Design Definition of Done

The design is only complete when:

1. every type in this document has one canonical home in code
2. every cache key input is explicit and testable
3. every stage has fatal vs non-fatal behavior defined
4. the BDD and TDD suite reflects this design instead of older assumptions
