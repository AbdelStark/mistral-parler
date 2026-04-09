---
name: mistral-pipeline
description: Implement or debug the Voxtral/Mistral-facing pipeline: transcription requests, diarization policy, retry/backoff, chunk assembly, parser normalization, deadline resolution, cache fingerprints, and quality gating. Use for audio/transcription/extraction work, not for generic CLI plumbing.
prerequisites: mistralai, pytest, json
---

# Mistral Pipeline

<purpose>
Handle the external API boundary cleanly while keeping internal semantics deterministic, typed, and locally testable.
</purpose>

<context>
- Canonical models and behavior live in `SPEC.md` and `SDD.md`.
- Current baseline assumptions from `2026-04-09`:
  - transcription default model: `voxtral-mini-latest` [verify]
  - extraction default model: `mistral-large-latest` [verify]
  - diarization is supported by the transcription API
  - explicit `language` and timestamp granularities need a request-strategy abstraction
  - extraction must use JSON mode and conservative normalization
- Cache keys must include every semantic input, not just content hash + model.
</context>

<procedure>
1. Separate vendor request building from response normalization.
2. Implement retry/backoff once and reuse it around every outbound API call.
3. For transcription:
   - choose request mode (`timestamp_first` or `language_first`)
   - request diarization when allowed
   - chunk long audio only when required
   - assemble chunks into one canonical transcript
   - run quality evaluation immediately after transcript construction
4. For extraction:
   - call chat completion in JSON mode
   - parse defensively; never let malformed JSON crash the pipeline
   - normalize IDs, language, confidence, and deadlines locally
   - drop low-confidence or invalid items instead of poisoning the full log
5. Write caches as atomic JSON with fingerprinted keys.
6. Expose pure helpers for assembly, parser normalization, deadline resolution, and cache-key generation so they can be unit/property tested.
</procedure>

<patterns>
<do>
  - Keep model names, request strategy, and prompt version in config rather than scattering literals.
  - Preserve monotonic timestamps and reindex segment IDs after chunk assembly.
  - Normalize unresolved speakers to `Unknown` and unresolved deadlines to `None`.
  - Treat quality warnings and parse warnings as explicit output, not silent failures.
</do>
<dont>
  - Don't bury vendor constraints directly in orchestration code -> isolate them in adapter logic.
  - Don't let parser exceptions abort the whole extraction stage -> return an empty or partial `DecisionLog`.
  - Don't use weak cache keys -> include request-policy inputs and meeting-date anchors.
</dont>
</patterns>

<examples>
Example: transcription cache fingerprint inputs

```text
audio_hash
+ transcription_model
+ request_mode
+ diarization_enabled
+ timestamp_granularity_mode
+ preprocessing_fingerprint
+ context_bias_fingerprint
```

Example: extraction cache fingerprint inputs

```text
transcript_hash
+ extraction_model
+ prompt_version
+ schema_version
+ meeting_date_anchor
+ extraction_policy_version
+ normalization_policy_version
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| duplicate text at chunk boundaries | assembly is not deduplicating overlap conservatively | fix the pure assembly helper before touching the transcriber |
| extraction crashes on malformed JSON | parser assumes valid JSON | make the parser defensive and return an empty/partial log |
| cache hits return semantically stale results | fingerprint is missing a policy input | add the missing request/config field to the key builder and update tests |
</troubleshooting>

<references>
- `SPEC.md`: vendor constraints and functional requirements
- `SDD.md`: adapter responsibilities, cache contracts, and quality checker behavior
- `tests/integration/test_voxtral_integration.py`: transcription adapter contract
- `tests/integration/test_mistral_extraction.py`: extraction adapter contract
- `tests/integration/test_cache_behavior.py`: cache behavior contract
- `tests/integration/test_retry_behavior.py`: retry/backoff contract
- `tests/unit/test_chunk_assembly.py`: assembly invariants
- `tests/unit/test_transcript_quality.py`: quality checker contract
- `tests/unit/test_decision_extraction_parsing.py`: parser normalization contract
- `tests/property/test_deadline_resolver_properties.py`: deadline invariants
</references>
