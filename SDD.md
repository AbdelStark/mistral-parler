# parler — Software Design Document

**Version**: 0.1.0  
**Status**: Draft  
**Date**: 2026-04-09  
**Authors**: Design phase — pre-implementation

---

## Table of Contents

1. [Purpose and Scope](#1-purpose-and-scope)
2. [System Context](#2-system-context)
3. [Architectural Decisions Record](#3-architectural-decisions-record)
4. [Component Design](#4-component-design)
5. [Data Models](#5-data-models)
6. [State Machine](#6-state-machine)
7. [API Contracts](#7-api-contracts)
8. [Configuration Schema](#8-configuration-schema)
9. [Error Taxonomy](#9-error-taxonomy)
10. [Performance Budget](#10-performance-budget)
11. [Security and Privacy Model](#11-security-and-privacy-model)
12. [Dependency Graph](#12-dependency-graph)
13. [Testing Strategy](#13-testing-strategy)
14. [Observability](#14-observability)

---

## 1. Purpose and Scope

### 1.1 Problem statement

`parler` solves a specific, painful gap in the European knowledge-work market: **voice recordings that should produce decisions produce summaries instead**.

The failure is twofold:
1. **Language failure**: transcription tools trained predominantly on English data degrade sharply on French, German, Spanish, Italian, and mixed-language (code-switching) audio. Phoneme confusion, name mangling, and technical vocabulary errors are pervasive.
2. **Abstraction failure**: even when transcription is correct, tools produce summaries ("the team discussed X") rather than structured decisions ("the team decided X; @person owns it by date"). Summaries require interpretation; decisions require action.

`parler` addresses both failures by building on Voxtral (Mistral's natively multilingual voice model) and applying a structured decision-extraction pass that distinguishes commitment from discussion.

### 1.2 Primary use cases

| Use case | User | Input | Expected output |
|----------|------|-------|----------------|
| Weekly team meeting | French tech team | 45-min Zoom recording | Decision log + commitment table |
| Earnings call analysis | Finance analyst | 90-min public earnings call | Decision log + commitment tracker |
| Sales call review | Account executive | 30-min call recording | Commitments + open questions |
| Board meeting minutes | Executive assistant | 2-hour board recording | Full decision log for minutes |
| Podcast intelligence | Developer/researcher | Public podcast episode | Key statements and positions |

### 1.3 Out of scope (v1)

- Real-time / streaming transcription of live meetings
- Audio capture from screen (requires OS-level permission complexity)
- Speaker identification via voice biometrics (privacy-sensitive; deferred)
- Custom vocabulary injection (Voxtral API limitation)
- Translation (transcription language = source language only)
- Processing audio longer than 4 hours in a single run

---

## 2. System Context

### 2.1 System context diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL USERS                                │
│                                                                      │
│  Developer/Analyst ─────────────────────────────────────────────    │
│       │ parler CLI / Python API                                  │  │
└───────┼──────────────────────────────────────────────────────────┘  │
        │                                                              │
        ▼                                                              │
┌───────────────────────────────────────────────────────────────────┐  │
│                         parler                                    │  │
│                                                                   │  │
│  ┌──────────┐  ┌────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  Audio   │  │  Voxtral   │  │   Decision   │  │  Report   │  │  │
│  │ Ingestion│→ │Transcriber │→ │  Extractor   │→ │ Renderer  │  │  │
│  └──────────┘  └────────────┘  └──────────────┘  └───────────┘  │  │
│       │              │               │                │           │  │
│       │              │               │                │           │  │
└───────┼──────────────┼───────────────┼────────────────┼───────────┘  │
        │              │               │                │              │
        ▼              ▼               ▼                ▼              │
  Local filesystem   Voxtral API    Mistral API     Local files /      │
  FFmpeg (optional)  (Mistral La    (mistral-       export APIs        │
  HTTP (for URLs)    Plateforme)    large-latest)   (Notion/Linear)    │
```

### 2.2 Deployment model

`parler` is a local CLI tool. There is no server, no daemon, no cloud sync. All state is local to the user's machine.

```
~/.cache/parler/
  transcripts/               # Voxtral transcription cache (keyed by audio hash)
    <sha256-prefix>.json
  extractions/               # Decision extraction cache (keyed by transcript hash + prompt version)
    <sha256-prefix>.json
  geodata/                   # (certifiable integration) ASN → country data
    asn-country-map.mmdb

./.parler-state.json         # Per-run pipeline state checkpoint (working directory)
```

### 2.3 Integration surfaces

| Surface | Direction | Protocol | Auth |
|---------|-----------|----------|------|
| Voxtral API | outbound | HTTPS/REST | `MISTRAL_API_KEY` |
| Mistral Chat API | outbound | HTTPS/REST | `MISTRAL_API_KEY` |
| Local filesystem | bidirectional | POSIX file I/O | none |
| FFmpeg | outbound | subprocess | none |
| Notion API | outbound | HTTPS/REST | `NOTION_API_KEY` |
| Linear API | outbound | HTTPS/GraphQL | `LINEAR_API_KEY` |
| Jira API | outbound | HTTPS/REST | `JIRA_EMAIL` + `JIRA_API_TOKEN` |
| Slack Webhooks | outbound | HTTPS/POST | `SLACK_WEBHOOK_URL` |

---

## 3. Architectural Decisions Record

### ADR-001: LLM-based diarization over pyannote

**Decision**: Use Mistral LLM to attribute speaker turns from transcript text rather than a local voice-diarization ML model.

**Context**: Speaker attribution requires either (a) acoustic analysis (voice fingerprinting, separation) or (b) linguistic analysis (who said what based on text context). Option (a) is more accurate for audio with multiple simultaneous speakers or low-quality audio; option (b) is sufficient for structured business meetings with named participants.

**Consequence**: Installation is 5× simpler. Accuracy is adequate for structured meetings (the primary use case). A `parler[diarize]` optional extra will add pyannote support for users who need higher accuracy.

**Supersedes**: N/A. **Status**: Accepted.

---

### ADR-002: Separate transcription and extraction caches

**Decision**: Cache the Voxtral transcript separately from the Mistral extraction result, keyed by different hashes.

**Context**: A user may want to re-run extraction with a different system prompt (e.g., trying a more aggressive decision-confidence threshold) without paying for re-transcription. Transcription is the expensive step ($0.15 for 45 minutes); extraction is cheaper ($0.08) and prompt-sensitive.

**Consequence**: Two cache directories. The extraction cache key includes a hash of the extraction prompt version, so prompt changes automatically invalidate only the extraction cache, not the transcript.

**Status**: Accepted.

---

### ADR-003: Single Mistral API key for both Voxtral and chat

**Decision**: Use a single `MISTRAL_API_KEY` environment variable for both the Voxtral transcription API and the Mistral chat API.

**Context**: Both services are under Mistral La Plateforme and use the same key. Requiring two separate keys would be confusing and unnecessary.

**Consequence**: If the user's API key is rate-limited on Voxtral, it will also be rate-limited on chat. In practice, these are likely different rate-limit buckets, but the user only needs to manage one key.

**Status**: Accepted.

---

### ADR-004: Resumable pipeline via .parler-state.json checkpoint

**Decision**: Write a `.parler-state.json` checkpoint file to the current working directory that allows `--resume` to pick up where a failed run left off.

**Context**: A 2-hour earnings call takes ~3 minutes to transcribe. If the extraction or rendering fails after transcription, the user should not need to re-transcribe. The checkpoint file captures the `ProcessingState` at each stage boundary.

**Consequence**: Working directories accumulate `.parler-state.json` files. Document in README that these can be safely deleted. Add `.parler-state.json` to global `.gitignore` recommendations.

**Status**: Accepted.

---

### ADR-005: Strip reasoning traces from output before returning to application

**Decision**: When explanation mode is active (future, certifiable integration), strip `<certifiable:reasoning>` blocks from the model output before it reaches the decision extraction logic.

**Context**: The decision extraction logic parses model outputs for decisions and commitments. Leaving reasoning traces embedded in the output would cause them to be extracted as spurious "decisions" or "commitments."

**Consequence**: The extraction logic receives clean output. The reasoning trace is stored separately in the audit log (certifiable integration) and is not visible to the extractor.

**Status**: Accepted (forward-looking, not yet implemented).

---

## 4. Component Design

### 4.1 AudioIngester

**Responsibility**: resolve the input (path, URL, or stdin) to a normalized audio file; detect format; chunk if necessary.

**Interface**:
```python
class AudioIngester:
    def __init__(self, config: ParlerConfig): ...
    
    def ingest(self, source: str) -> AudioIngestionResult:
        """
        source: local path, http/https URL, or "-" for stdin.
        Returns AudioIngestionResult with all fields populated.
        Never raises for audio quality issues (those are warnings);
        raises only for unrecoverable errors (file not found, network failure).
        """
    
    def estimate_chunking(self, metadata: AudioMetadata) -> ChunkPlan:
        """
        Given audio metadata, produce a chunking plan without reading the full file.
        Used by --cost-estimate to predict API call count.
        """
```

**State**: stateless. Each `ingest()` call is independent.

**Side effects**: 
- May write temporary files to `tempfile.gettempdir()` for format conversion (FFmpeg) and URL downloads
- Temporary files are registered in `AudioIngestionResult.temp_files` for cleanup

**Invariants**:
- Output file path is always in a supported Voxtral format (`mp3`, `mp4`, `m4a`, `wav`, `ogg`, `webm`)
- Output file is always readable by the current process
- `AudioMetadata.duration_s` is always populated (never None after successful ingestion)

---

### 4.2 VoxtralTranscriber

**Responsibility**: send audio chunks to the Voxtral API; cache results; assemble chunked transcripts.

**Interface**:
```python
class VoxtralTranscriber:
    def __init__(self, client: Mistral, config: ParlerConfig, cache: TranscriptCache): ...
    
    def transcribe(self, ingestion: AudioIngestionResult) -> Transcript:
        """
        Transcribes all chunks, caches each result, assembles into a single Transcript.
        Progress is reported via config.progress_callback if set.
        """
    
    def transcribe_chunk(self, chunk: AudioChunk) -> RawVoxtralResponse:
        """
        Single chunk transcription. Cached by chunk content hash.
        Retries on transient errors per config.retry_policy.
        """
    
    def assemble(self, chunk_responses: list[RawVoxtralResponse], plan: ChunkPlan) -> Transcript:
        """
        Merges overlapping segments from adjacent chunks.
        Deduplicates by timestamp and confidence.
        """
```

**State**: stateless except for the injected cache. Thread-safe (cache is responsible for its own thread-safety).

**Retry policy**: exponential backoff with jitter on HTTP 429 and 5xx. Raises `VoxtralAPIError` after `config.retry_policy.max_attempts` failures.

**Cache contract**: cache read/write is always keyed by `sha256(chunk_bytes)[:16] + "-" + voxtral_model_version`. A cache miss triggers a Voxtral API call; a cache hit skips it entirely.

---

### 4.3 SpeakerAttributor

**Responsibility**: assign speaker labels to transcript segments using LLM-based linguistic analysis.

**Interface**:
```python
class SpeakerAttributor:
    def __init__(self, client: Mistral, config: ParlerConfig): ...
    
    def attribute(self, transcript: Transcript, participants: list[str] | None = None) -> Transcript:
        """
        Returns a new Transcript with speaker_id populated on segments.
        Does not modify the input transcript (immutable update).
        """
    
    def extract_names(self, transcript: Transcript) -> list[ParticipantCandidate]:
        """
        First pass: extract names from the transcript text.
        Returns candidates with role (speaker | mentioned) and aliases.
        """
    
    def assign_turns(
        self,
        transcript: Transcript,
        participants: list[ParticipantCandidate]
    ) -> list[SpeakerAttribution]:
        """
        Second pass: assign each segment to a participant.
        Returns ordered attributions matching transcript segment order.
        """
```

**State**: stateless.

**Confidence contract**: if the LLM cannot attribute a segment with at least `medium` confidence, the segment's `speaker_id` is set to `"Unknown"`. Unknown segments are never forced into an attribution.

**LLM call count**: exactly 2 Mistral calls per `attribute()` invocation (name extraction + turn assignment), regardless of transcript length.

---

### 4.4 DecisionExtractor

**Responsibility**: extract structured decisions, commitments, rejections, and open questions from an attributed transcript.

**Interface**:
```python
class DecisionExtractor:
    def __init__(self, client: Mistral, config: ParlerConfig, cache: ExtractionCache): ...
    
    def extract(self, transcript: Transcript, meeting_date: date | None = None) -> DecisionLog:
        """
        Extracts structured decision log from transcript.
        Uses single-pass for transcripts < 25,000 words; multi-pass for longer.
        Resolves relative deadlines using meeting_date (or today if None).
        """
    
    def _single_pass_extract(self, transcript: Transcript) -> RawDecisionLog: ...
    def _multi_pass_extract(self, transcript: Transcript) -> RawDecisionLog: ...
    def _resolve_deadlines(self, raw: RawDecisionLog, meeting_date: date) -> DecisionLog: ...
    def _validate_output(self, raw: dict) -> RawDecisionLog: ...
```

**State**: stateless except for the injected cache.

**Validation contract**: the raw LLM JSON output is validated against the `RawDecisionLog` Pydantic model before use. Invalid fields are silently dropped (not propagated as errors) with a warning log. The extraction never fails due to a partial or malformed LLM response — it degrades gracefully to an empty section.

**Cache key**: `sha256(transcript.text + extraction_prompt.version)[:16]`. Cache hits skip the Mistral API call entirely.

---

### 4.5 ReportRenderer

**Responsibility**: render a `DecisionLog` (+ `AudioMetadata`) into one of the supported output formats.

**Interface**:
```python
class ReportRenderer:
    def __init__(self, config: ParlerConfig): ...
    
    def render(
        self,
        log: DecisionLog,
        audio: AudioMetadata,
        format: Literal["markdown", "html", "json"]
    ) -> str:
        """
        Returns the rendered report as a string.
        For JSON: valid JSON. For Markdown/HTML: UTF-8 string.
        Never raises for empty decision logs (renders an empty report).
        """
    
    def render_to_file(
        self,
        log: DecisionLog,
        audio: AudioMetadata,
        output_path: Path
    ) -> None:
        """
        Renders and writes to path. Infers format from file extension.
        """
```

**State**: stateless.

**Template engine**: Jinja2 for HTML. Custom formatter for Markdown (no template engine — simpler and more predictable for table generation).

**HTML contract**: the HTML output is a single self-contained file. No external CSS, no web fonts, no JavaScript (except minimal inline JS for collapsible sections). Must render correctly when opened as a local file with `file://` protocol.

---

### 4.6 ExportManager

**Responsibility**: export a `DecisionLog` to external task management or communication tools.

**Interface**:
```python
class ExportManager:
    def __init__(self, config: ParlerConfig): ...
    
    def export(
        self,
        log: DecisionLog,
        audio: AudioMetadata,
        target: Literal["notion", "linear", "jira", "slack"]
    ) -> ExportResult: ...
```

**State**: stateless.

**Failure isolation**: export failures are non-fatal. If the Notion API call fails, the CLI prints a warning and exits 0 (the report was already generated successfully). The `ExportResult` contains a success flag and error details.

---

### 4.7 PipelineOrchestrator

**Responsibility**: coordinate the pipeline stages, manage the checkpoint, enforce configuration, and report progress.

**Interface**:
```python
class PipelineOrchestrator:
    def __init__(
        self,
        config: ParlerConfig,
        ingester: AudioIngester,
        transcriber: VoxtralTranscriber,
        attributor: SpeakerAttributor,
        extractor: DecisionExtractor,
        renderer: ReportRenderer
    ): ...
    
    def run(self, source: str, output_path: Path | None = None) -> PipelineResult: ...
    def resume(self, state_path: Path) -> PipelineResult: ...
    def estimate_cost(self, source: str) -> CostEstimate: ...
```

**State**: writes `.parler-state.json` checkpoint to the output directory after each completed stage.

**Checkpoint contract**: if `state_path` is provided and exists, the orchestrator reads it and skips all stages whose output is already in the checkpoint. A stage is re-run if and only if its output is absent from the checkpoint.

---

## 5. Data Models

### 5.1 Complete type definitions

```python
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal
from pathlib import Path


# ─── Audio ───────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AudioChunk:
    index: int                  # 0-indexed
    path: Path
    start_s: float
    end_s: float
    duration_s: float           # = end_s - start_s
    overlap_start_s: float      # seconds of overlap with prev chunk (0 for first)
    overlap_end_s: float        # seconds of overlap with next chunk (0 for last)
    content_hash: str           # sha256[:16] of file bytes


@dataclass(frozen=True)
class AudioMetadata:
    path: Path
    original_path: Path         # before any format conversion
    format: str                 # "mp3", "wav", "mp4", etc.
    duration_s: float
    sample_rate: int
    channels: int               # 1 = mono, 2 = stereo
    bitrate_kbps: int | None
    title: str | None
    recording_date: date | None
    temp_files: tuple[Path, ...]  # to be cleaned up after run
    needs_chunking: bool
    chunk_plan: ChunkPlan | None


@dataclass(frozen=True)
class ChunkPlan:
    chunks: tuple[AudioChunk, ...]
    max_chunk_s: float
    overlap_s: float
    split_on_silence: bool


# ─── Transcript ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TranscriptWord:
    word: str
    start_s: float
    end_s: float
    probability: float          # 0.0 - 1.0


@dataclass
class TranscriptSegment:
    id: int                     # sequential, 0-indexed
    start_s: float
    end_s: float
    text: str
    language: str               # ISO 639-1: "fr", "en", "de", etc.
    speaker_id: str | None      # None until SpeakerAttributor runs
    speaker_confidence: Literal["high", "medium", "low", "unknown"] | None
    confidence: float           # 0.0 - 1.0 (mapped from Voxtral logprob)
    no_speech_prob: float       # 0.0 - 1.0
    code_switch: bool           # True if segment contains multiple languages
    words: list[TranscriptWord] | None  # word-level, if available


@dataclass(frozen=True)
class Transcript:
    duration_s: float
    primary_language: str
    detected_languages: tuple[str, ...]   # all languages detected
    segments: tuple[TranscriptSegment, ...]
    voxtral_model: str
    content_hash: str           # sha256[:16] of full transcript text (for cache key)
    
    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments)
    
    @property
    def word_count(self) -> int:
        return len(self.text.split())
    
    @property
    def avg_confidence(self) -> float:
        speech_segments = [s for s in self.segments if s.no_speech_prob < 0.5]
        if not speech_segments:
            return 0.0
        return sum(s.confidence for s in speech_segments) / len(speech_segments)
    
    @property
    def speakers(self) -> list[str]:
        return sorted(set(
            s.speaker_id for s in self.segments
            if s.speaker_id and s.speaker_id != "Unknown"
        ))


# ─── Speaker Attribution ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ParticipantCandidate:
    name: str
    role: Literal["speaker", "mentioned"]
    aliases: tuple[str, ...]
    first_mention_s: float


@dataclass(frozen=True)
class SpeakerAttribution:
    segment_id: int
    speaker: str          # name or "Unknown"
    confidence: Literal["high", "medium", "low", "unknown"]
    method: Literal["explicit", "contextual", "inferred", "unknown"]


# ─── Decision Log ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CommitmentDeadline:
    raw: str                    # verbatim as stated in meeting
    resolved_date: date | None  # None if relative and unresolvable
    is_explicit: bool           # True = exact date stated; False = relative


@dataclass(frozen=True)
class Decision:
    id: str                     # "D1", "D2", ...
    summary: str
    timestamp_s: float | None
    speaker: str | None
    confirmed_by: tuple[str, ...]
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class Commitment:
    id: str                     # "C1", "C2", ...
    owner: str
    action: str
    deadline: CommitmentDeadline | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class Rejection:
    id: str                     # "R1", "R2", ...
    proposal: str
    reason: str | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class OpenQuestion:
    id: str                     # "Q1", "Q2", ...
    question: str
    stakes: str | None
    timestamp_s: float | None
    quote: str
    confidence: Literal["high", "medium"]
    language: str


@dataclass(frozen=True)
class ExtractionMetadata:
    model: str
    prompt_version: str
    extracted_at: datetime
    transcript_word_count: int
    pass_count: int             # 1 for single-pass, 2+ for multi-pass
    extraction_duration_ms: int


@dataclass(frozen=True)
class DecisionLog:
    decisions: tuple[Decision, ...]
    commitments: tuple[Commitment, ...]
    rejected: tuple[Rejection, ...]
    open_questions: tuple[OpenQuestion, ...]
    metadata: ExtractionMetadata
    
    @property
    def total_items(self) -> int:
        return len(self.decisions) + len(self.commitments) + len(self.rejected) + len(self.open_questions)
    
    @property
    def is_empty(self) -> bool:
        return self.total_items == 0


# ─── Pipeline State ───────────────────────────────────────────────────────────

@dataclass
class ProcessingState:
    schema_version: str = "0.1.0"
    created_at: datetime = field(default_factory=datetime.utcnow)
    source: str = ""
    config_hash: str = ""       # hash of ParlerConfig for invalidation
    
    # Completed stage outputs (None = stage not yet run)
    audio: AudioMetadata | None = None
    transcript: Transcript | None = None
    decision_log: DecisionLog | None = None
    
    # Timing
    ingestion_ms: int | None = None
    transcription_ms: int | None = None
    attribution_ms: int | None = None
    extraction_ms: int | None = None
    rendering_ms: int | None = None
    
    @property
    def completed_stages(self) -> list[str]:
        stages = []
        if self.audio: stages.append("ingestion")
        if self.transcript: stages.append("transcription")
        if self.decision_log: stages.append("extraction")
        return stages
```

---

## 6. State Machine

### 6.1 Pipeline state transitions

```
                    ┌─────────────────────────────────────────────────────┐
                    │                   PIPELINE STATES                   │
                    └─────────────────────────────────────────────────────┘

IDLE ──────► INGESTING ──────► TRANSCRIBING ──────► ATTRIBUTING ──────► EXTRACTING ──────► RENDERING ──────► DONE
              │    │              │    │                │    │              │    │              │    │
              │    └──► ERROR     │    └──► ERROR       │    └──► ERROR    │    └──► ERROR    │    └──► ERROR
              │          │        │          │           │          │       │          │       │
              └──►CANCELLED      └──►CANCELLED          └──►CANCELLED     └──►CANCELLED      └──►CANCELLED

ERROR ──────► (user fixes issue) ──────► INGESTING (via --resume, skipping cached stages)
```

### 6.2 Stage skip conditions (for --resume)

| Stage | Skip condition |
|-------|---------------|
| INGESTING | `state.audio` is not None AND source file unchanged (hash matches) |
| TRANSCRIBING | `state.transcript` is not None AND `state.audio` matches current |
| ATTRIBUTING | `--no-diarize` flag OR transcript has speakers populated |
| EXTRACTING | `state.decision_log` is not None AND transcript hash matches cache key |
| RENDERING | Never cached — always re-render from DecisionLog |

### 6.3 Voxtral request state machine

```
PENDING ──────► SENDING ──────► AWAITING_RESPONSE ──────► PARSING ──────► CACHED ──────► DONE
                  │                    │                      │
                  │                    ▼                      ▼
                  │               RATE_LIMITED          PARSE_ERROR
                  │                    │                      │
                  │                    ▼                      ▼
                  │              RETRY_WAIT              FAILED (non-retryable)
                  │                    │
                  └────────────────────┘ (up to max_attempts)
```

---

## 7. API Contracts

### 7.1 Voxtral transcription request

```http
POST https://api.mistral.ai/v1/audio/transcriptions
Authorization: Bearer <MISTRAL_API_KEY>
Content-Type: multipart/form-data

file:                  <audio_file_bytes>
model:                 "voxtral-v0.1"
language:              "fr"           (optional; omit for auto-detect)
response_format:       "verbose_json"
timestamp_granularities: ["segment"]  (or ["word"] if available)
```

**Expected response** (200 OK):
```json
{
  "text": "...",
  "language": "fr",
  "duration": 2843.0,
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 4.2,
      "text": "Bonjour à tous, merci d'être là.",
      "avg_logprob": -0.23,
      "no_speech_prob": 0.02,
      "words": null
    }
  ]
}
```

**Error handling**:

| HTTP status | Error type | Action |
|-------------|-----------|--------|
| 400 | `VoxtralBadRequestError` | Fail immediately. Log the request details. |
| 401 | `AuthenticationError` | Fail immediately. Print "Check your MISTRAL_API_KEY." |
| 413 | `FileTooLargeError` | Fail immediately. "Audio chunk exceeds API size limit. Reduce chunk size in config." |
| 429 | `RateLimitError` | Retry after `Retry-After` header delay (or exponential backoff if header absent). |
| 500, 502, 503 | `ServerError` | Retry with exponential backoff. |
| 504 | `TimeoutError` | Retry with exponential backoff. Long audio may need extended timeout. |

### 7.2 Mistral chat completion request (decision extraction)

```http
POST https://api.mistral.ai/v1/chat/completions
Authorization: Bearer <MISTRAL_API_KEY>
Content-Type: application/json

{
  "model": "mistral-large-latest",
  "messages": [
    {
      "role": "system",
      "content": "<EXTRACTION_SYSTEM_PROMPT>"
    },
    {
      "role": "user",
      "content": "TRANSCRIPT:\n<transcript_text>\n\nReturn JSON only."
    }
  ],
  "response_format": { "type": "json_object" },
  "temperature": 0.0,
  "max_tokens": 4096
}
```

**Response validation**: the response JSON is validated against the `RawDecisionLog` Pydantic model. If validation fails:
1. Log the full raw response at DEBUG level
2. Attempt partial extraction from whatever fields are present
3. Return a `DecisionLog` with only the valid fields populated
4. Set `ExtractionMetadata.parse_warnings` with a description of what was invalid

---

## 8. Configuration Schema

Complete `ParlerConfig` specification:

```python
@dataclass
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_s: float = 1.0
    backoff_factor: float = 2.0
    max_delay_s: float = 30.0
    jitter: bool = True


@dataclass
class ChunkingConfig:
    max_chunk_s: float = 600.0           # 10 minutes
    overlap_s: float = 30.0
    split_on_silence: bool = True
    silence_threshold_db: float = -30.0
    silence_min_duration_s: float = 0.5
    silence_search_window_s: float = 60.0  # how far from target split to look for silence


@dataclass
class TranscriptionConfig:
    model: str = "voxtral-v0.1"
    languages: list[str] = field(default_factory=list)  # empty = auto-detect
    response_format: str = "verbose_json"
    timestamp_granularities: list[str] = field(default_factory=lambda: ["segment"])
    request_timeout_s: float = 120.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class AttributionConfig:
    enabled: bool = True
    confidence_threshold: Literal["high", "medium", "low"] = "medium"
    model: str = "mistral-large-latest"
    temperature: float = 0.0
    use_local_diarize: bool = False      # requires certifiable[diarize]


@dataclass
class ExtractionConfig:
    model: str = "mistral-large-latest"
    temperature: float = 0.0
    max_tokens: int = 4096
    prompt_version: str = "v1"
    confidence_threshold: Literal["high", "medium"] = "medium"
    multi_pass_threshold_words: int = 25_000
    retry: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class CacheConfig:
    enabled: bool = True
    directory: Path = field(default_factory=lambda: Path.home() / ".cache" / "parler")
    max_size_gb: float = 2.0
    ttl_days: int | None = None         # None = no expiry


@dataclass
class OutputConfig:
    format: Literal["markdown", "html", "json"] = "markdown"
    output_path: Path | None = None     # None = auto-name from input
    include_transcript: bool = False
    include_quotes: bool = True
    anonymize_speakers: bool = False
    timezone: str = "UTC"               # for timestamp display


@dataclass
class CostConfig:
    max_transcription_usd: float | None = None   # None = no cap
    max_extraction_usd: float | None = None
    confirm_above_usd: float = 1.0      # prompt before runs over this cost


@dataclass
class ParlerConfig:
    # API
    api_key: str = field(default_factory=lambda: os.environ.get("MISTRAL_API_KEY", ""))
    api_base_url: str = "https://api.mistral.ai/v1"
    
    # Components
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    attribution: AttributionConfig = field(default_factory=AttributionConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    
    # Runtime
    participants: list[str] = field(default_factory=list)  # e.g. ["Pierre (PM)", "Sophie (Eng)"]
    meeting_date: date | None = None    # for deadline resolution; defaults to today
    verbose: bool = False
    quiet: bool = False
    yes: bool = False                   # skip confirmation prompts
    progress_callback: Callable | None = None
```

**Config file** (`.parlerrc.json`, auto-discovered from CWD up):
```json
{
  "transcription": {
    "languages": ["fr", "en"],
    "model": "voxtral-v0.1"
  },
  "extraction": {
    "confidence_threshold": "high"
  },
  "output": {
    "format": "html"
  },
  "participants": ["Pierre (Tech Lead)", "Sophie (Product)", "Marc (Eng)"]
}
```

---

## 9. Error Taxonomy

### 9.1 Error hierarchy

```python
class ParlerError(Exception):
    """Base class for all parler errors."""
    exit_code: int = 1

# ─── Input errors ─────────────────────────────────────────────────────────────
class InputError(ParlerError):
    exit_code = 2

class FileNotFoundError(InputError): pass
class UnsupportedFormatError(InputError): pass
class FileTooLargeError(InputError): pass
class InvalidURLError(InputError): pass
class NetworkDownloadError(InputError): pass

# ─── Environment errors ────────────────────────────────────────────────────────
class EnvironmentError(ParlerError):
    exit_code = 3

class MissingAPIKeyError(EnvironmentError): pass
class FFmpegNotFoundError(EnvironmentError): pass
class CachePermissionError(EnvironmentError): pass
class InsufficientDiskSpaceError(EnvironmentError): pass

# ─── API errors ────────────────────────────────────────────────────────────────
class APIError(ParlerError):
    exit_code = 4

class AuthenticationError(APIError): pass
class RateLimitError(APIError):
    retry_after_s: float | None
class VoxtralAPIError(APIError): pass
class MistralAPIError(APIError): pass
class APITimeoutError(APIError): pass

# ─── Processing errors ──────────────────────────────────────────────────────────
class ProcessingError(ParlerError):
    exit_code = 5

class TranscriptionQualityError(ProcessingError):
    avg_confidence: float
class ChunkAssemblyError(ProcessingError): pass
class ExtractionParseError(ProcessingError):
    raw_response: str
class ExtractionEmptyError(ProcessingError): pass

# ─── Output errors ─────────────────────────────────────────────────────────────
class OutputError(ParlerError):
    exit_code = 6

class OutputWriteError(OutputError): pass
class ExportError(OutputError):
    target: str
```

### 9.2 Error handling matrix

| Error | User message | Action | Recoverable? |
|-------|-------------|--------|-------------|
| `MissingAPIKeyError` | "MISTRAL_API_KEY not set. Export it: `export MISTRAL_API_KEY=...`" | Exit 3 | Yes (set key, rerun) |
| `FFmpegNotFoundError` | "FFmpeg required for .{ext} files. Install: brew install ffmpeg" | Exit 3 | Yes (install FFmpeg) |
| `FileNotFoundError` | "File not found: {path}" | Exit 2 | Yes (check path) |
| `UnsupportedFormatError` | "Unsupported format: {ext}. Supported: mp3, mp4, m4a, wav, ogg, webm. Add FFmpeg for others." | Exit 2 | Yes (install FFmpeg) |
| `FileTooLargeError` (chunk) | "Audio chunk exceeds API limit. Reduce max_chunk_s in config (current: {n}s)" | Exit 2 | Yes (reduce chunk size) |
| `AuthenticationError` | "API authentication failed. Check your MISTRAL_API_KEY." | Exit 4 | Yes (check key) |
| `RateLimitError` (max retries) | "Rate limit exceeded after {n} retries. Try again later or reduce concurrency." | Exit 4 | Yes (wait) |
| `APITimeoutError` | "Voxtral API timed out after {n}s. Network issue or very long audio. Use `--resume` to retry." | Exit 4 + checkpoint | Yes (resume) |
| `TranscriptionQualityError` | "⚠ Low transcript confidence ({pct}%). Results may be inaccurate. Continue? [y/N]" | Prompt | Yes (continue or abort) |
| `ExtractionParseError` | "⚠ Could not parse extraction response. Partial results available." | Warning + partial log | Partial |
| `ExtractionEmptyError` | "No decisions found in transcript. This may be normal for non-decision meetings." | Warning | N/A |
| `OutputWriteError` | "Cannot write to {path}: {reason}" | Exit 6 | Yes (check path) |
| `ExportError` | "Export to {target} failed: {reason}. Decision log was saved locally." | Warning | Yes (retry export) |

---

## 10. Performance Budget

### 10.1 Latency targets

| Phase | Input size | Target (P50) | Target (P95) | Hard limit |
|-------|-----------|-------------|-------------|-----------|
| Audio ingestion | Any | < 2s | < 5s | 30s |
| Format conversion (FFmpeg) | 2-hour file | < 30s | < 60s | 120s |
| Voxtral transcription | 30-min audio | < 60s | < 120s | 300s |
| Voxtral transcription | 2-hour audio | < 4 min | < 8 min | 20 min |
| Speaker attribution | 10,000 words | < 15s | < 30s | 60s |
| Decision extraction (single-pass) | 10,000 words | < 20s | < 40s | 90s |
| Decision extraction (multi-pass) | 50,000 words | < 60s | < 120s | 300s |
| Report rendering | Any | < 1s | < 2s | 10s |

### 10.2 Cost targets

| Operation | 30-min meeting | 2-hour meeting | Public earnings call (90 min) |
|-----------|---------------|---------------|-------------------------------|
| Voxtral transcription | ~$0.10 | ~$0.40 | ~$0.30 |
| Speaker attribution (2 calls) | ~$0.02 | ~$0.04 | ~$0.03 |
| Decision extraction (1 call) | ~$0.06 | ~$0.10 (multi-pass) | ~$0.08 |
| **Total** | **~$0.18** | **~$0.54** | **~$0.41** |

Cost model assumptions: Voxtral at $0.003/min, mistral-large-latest at $2/M input + $6/M output tokens.

### 10.3 Cache effectiveness targets

| Scenario | Cache hit rate | Cost without cache | Cost with cache |
|----------|---------------|-------------------|----------------|
| Same file, different output format | 100% (both caches hit) | $0.18 | $0.00 |
| Same file, different extraction params | 100% transcript, 0% extraction | $0.18 | $0.08 |
| Different file, same structure | 0% (content hash miss) | $0.18 | $0.18 |

---

## 11. Security and Privacy Model

### 11.1 Data classification

| Data type | Classification | Where it lives | Retention |
|-----------|---------------|---------------|-----------|
| Original audio file | User data (potentially PII) | Local disk only | Not retained by parler |
| Voxtral transcription cache | Potentially PII (transcript of speech) | `~/.cache/parler/transcripts/` | User-controlled |
| Decision extraction cache | Derivative PII | `~/.cache/parler/extractions/` | User-controlled |
| API key | Secret | Environment variable | Not written to disk by parler |
| Decision log output | Potentially PII | User-specified output path | User-controlled |
| Pipeline checkpoint | Potentially PII (hashes + metadata) | `./.parler-state.json` | Auto-deleted on success |

### 11.2 Data transmission

Audio data is transmitted to Voxtral. Transcript text is transmitted to Mistral's chat API. Both transmissions:
- Use HTTPS (TLS 1.2+ enforced via `httpx` default settings)
- Are subject to Mistral's data processing terms (EU servers, no training data use per enterprise terms)
- Can be avoided for re-runs if the cache is warm

**What is NOT transmitted**:
- The original audio file URL/path
- Any local environment variables (only the API key is used in headers)
- Any file system metadata other than audio content

### 11.3 Threat model

| Threat | Mitigation |
|--------|-----------|
| API key exposed in logs | Never log the API key. Redact `Authorization` header in debug logs. |
| Transcript written to temp file before cache | Use `tempfile.NamedTemporaryFile(delete=True)` so temp is cleaned on crash |
| Cache readable by other processes | Default cache directory is `~/.cache/parler/` (user home, 700 permissions recommended) |
| Pipeline state contains PII | `.parler-state.json` contains only hashes, not plaintext content. Auto-deleted on successful run. |
| Export API key exposure | Export API keys logged only at DEBUG level; never in normal output |
| FFmpeg subprocess injection | Audio file paths are passed as arguments (not shell-interpolated). FFmpeg is invoked via `subprocess.run(..., shell=False)`. |

### 11.4 GDPR compliance notes

`parler` processes meeting audio that may contain personal data (names, voices, discussions involving individuals). The data controller is the user. `parler` is a data processor. Relevant obligations:

- **Data minimization**: audio is chunked and sent to Voxtral; the full file is never uploaded as a single payload
- **Purpose limitation**: transcription and decision extraction are the sole processing purposes
- **Storage limitation**: caches have configurable TTL; default is no TTL (user's responsibility to clear)
- **Security**: HTTPS for all transmissions; local cache at OS-level file permissions

---

## 12. Dependency Graph

### 12.1 Required dependencies (minimal install)

```
parler-voice
├── mistralai >= 1.0.0          # Voxtral + Mistral API client
├── httpx >= 0.27.0             # HTTP client (used by mistralai)
├── pydantic >= 2.0.0           # Data validation (DecisionLog schema)
├── jinja2 >= 3.1.0             # HTML report templating
├── python-dateparser >= 1.2.0  # Multi-language date parsing
├── click >= 8.1.0              # CLI framework
└── rich >= 13.0.0              # Terminal progress and formatting
```

### 12.2 Optional dependencies

```
parler-voice[pdf]
└── weasyprint >= 60.0          # PDF generation from HTML

parler-voice[diarize]
├── pyannote.audio >= 3.1.0     # Voice diarization
└── torch >= 2.0.0              # PyTorch (required by pyannote)

parler-voice[export]
├── notion-client >= 2.0.0      # Notion export
└── linear-client >= 0.1.0      # Linear export (if available as pip package)
```

### 12.3 Optional system dependencies

```
ffmpeg                          # Format conversion for non-native audio formats
                                # Optional: detected at runtime; clear error if missing
```

### 12.4 Python version requirement

Python >= 3.11 (uses `match/case`, `tomllib`, `datetime.fromisoformat` improvements).

---

## 13. Testing Strategy

Full test specifications are in the [`tests/`](./tests/) directory.

Summary:

| Layer | Count | Tooling | Coverage target |
|-------|-------|---------|----------------|
| Unit tests | ~85 | pytest | 90% line, 85% branch |
| Integration tests | ~25 | pytest + mock API | All API call paths |
| E2E tests | ~12 | pytest + real API | Core happy paths |
| BDD scenarios | ~60 | pytest-bdd + Gherkin | All user-facing behaviors |
| Property tests | ~10 | hypothesis | Core data transformations |

---

## 14. Observability

### 14.1 Logging

`parler` uses Python's standard `logging` module. Log format:

```
%(asctime)s  %(levelname)-8s  %(name)s  %(message)s
```

Log levels:
- `INFO`: stage transitions, cache hits/misses, API call start/end, output written
- `WARNING`: low confidence, partial extraction, export failures
- `ERROR`: unrecoverable failures (printed to stderr before raising)
- `DEBUG`: full API request/response bodies (with API key redacted), FFmpeg command lines, full prompts

`--verbose` enables DEBUG. `--quiet` suppresses INFO and WARNING (only ERROR printed).

### 14.2 Progress reporting

For interactive use (stdout is a TTY), progress is shown via Rich:

```
Processing meeting.mp3 (47:23)

  ✓  Audio ingested         0.3s
  ⠿  Transcribing...        Chunk 3/5  (12:00 - 22:00)  ████████░░  [60%]  ~45s remaining
```

For non-interactive use (stdout redirected), progress is suppressed. Machine-readable status is available via `--format json` on the `report` command.

### 14.3 Metrics (future)

Phase 2 may add optional telemetry (opt-in) reporting:
- Transcription duration per audio minute
- Decision extraction token counts
- Cache hit rates

All telemetry is opt-in, anonymous, and documented.
