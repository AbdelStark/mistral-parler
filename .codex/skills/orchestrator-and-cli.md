---
name: orchestrator-and-cli
description: Implement or debug the pipeline state machine, checkpoint/resume flow, cost-estimation guard, progress callbacks, and the canonical CLI surface. Use when touching `parler.pipeline.*`, `parler.cli`, exit codes, or `.parler-state.json` semantics.
prerequisites: pytest, click, json
---

# Orchestrator and CLI

<purpose>
Keep the user-facing pipeline deterministic, resumable, and explicit about failure modes. This skill is for orchestration and command-surface work, not for vendor adapter internals.
</purpose>

<context>
- `ProcessingState` is a frozen value object; each stage returns a new state.
- Canonical stage order: ingest -> transcribe -> quality check -> attribute -> extract -> render -> export.
- Fatal stages: ingest, transcribe, extract.
- Soft-failable stages: attribute, export.
- Checkpoint files serialize real artifacts and are sensitive local state.
- Canonical CLI commands:
  - `parler process <input>`
  - `parler transcribe <input>`
  - `parler extract --from-state <state.json>`
  - `parler report --from-state <state.json>`
  - `parler cache list|show|clear`
</context>

<procedure>
1. Implement `ProcessingState` and `PipelineStage` first.
2. Make checkpoint serialization/deserialization explicit and typed.
3. Validate resume by matching current audio content hash against checkpoint audio hash.
4. Compute cost estimate before the first billable API call.
5. Support stage skipping for cache hits, `--transcribe-only`, `--no-diarize`, and valid `--resume`.
6. Re-render from canonical state; never replay opaque side effects.
7. Map error classes to CLI exit codes exactly as defined in `SDD.md`.
</procedure>

<patterns>
<do>
  - Write checkpoints after meaningful billable-stage completion.
  - Keep progress callbacks side-effect free and informative.
  - Preserve local render success even if export adapters fail.
  - Expose a temporary `PipelineConfig` alias if E2E compatibility still requires it.
</do>
<dont>
  - Don't skip a stage on resume unless its serialized artifact is present and valid.
  - Don't store API keys or other secrets in checkpoints.
  - Don't let CLI convenience bypass the canonical command/flag surface from `SPEC.md`.
</dont>
</patterns>

<examples>
Example: minimal checkpoint shape

```json
{
  "audio_hash": "abc123abc123",
  "completed_stages": ["TRANSCRIBE"],
  "transcript": {
    "text": "Pre-cached.",
    "language": "fr",
    "duration_s": 5.0,
    "segments": []
  }
}
```

Example: orchestration verification order

```bash
pytest tests/unit/test_pipeline_orchestration.py -q
pytest features/cli_interface.feature -q
pytest features/error_handling.feature -q
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| `--resume` re-runs transcription unexpectedly | checkpoint is missing artifact data or hash validation fails | inspect checkpoint shape and validate the audio hash gate |
| cost-confirmation behavior is inconsistent | estimate is computed too late | move cost estimation before the first billable call |
| CLI report rerender hits APIs | report path is not using serialized state | route `parler report --from-state` through local render only |
</troubleshooting>

<references>
- `SPEC.md`: canonical CLI surface and resumability requirements
- `SDD.md`: `ProcessingState`, state machine, error model, checkpoint semantics
- `tests/unit/test_pipeline_orchestration.py`: orchestration contract
- `features/cli_interface.feature`: CLI behavior scenarios
- `features/error_handling.feature`: resume and exit-code scenarios
- `tests/e2e/test_full_pipeline_fr.py`: current `PipelineConfig` compatibility expectation
</references>
