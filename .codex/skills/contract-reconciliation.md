---
name: contract-reconciliation
description: Reconcile drift between canonical docs, tests, feature files, RFCs, and planned module names. Use when imports disagree, specs and tests conflict, fixture assumptions diverge, or a code change touches `SPEC.md`, `SDD.md`, `TESTING.md`, `features/`, `tests/`, or `pyproject.toml`.
prerequisites: rg, pytest
---

# Contract Reconciliation

<purpose>
Resolve contradictions before implementation work compounds them. In this repository, drift is a primary failure mode; this skill exists to stop agents from coding against the wrong contract.
</purpose>

<context>
- `SPEC.md` and `SDD.md` are the canonical sources of truth.
- `TESTING.md` defines the verification contract, but it can still lag the canonical spec.
- Current known drifts:
  - `parler/transcription/assembly.py` in `SDD.md` vs `parler.transcription.assembler` in tests
  - `parler/attribution/attributor.py` in `SDD.md` vs `parler.transcription.attributor` in tests
  - `parler/util/*` in `SDD.md` vs `parler.utils.retry` in tests
  - `ParlerConfig` in unit tests vs `PipelineConfig` in E2E tests
  - E2E fixture assets described in docs are not committed yet
</context>

<procedure>
1. Prove the conflict with exact file paths and grep output.
2. Classify it:
   - contract drift: docs disagree with docs
   - import drift: docs are stable but code/tests point at old names
   - fixture/tooling drift: docs expect files or deps that are absent
3. Apply authority order:
   - `SPEC.md` + `SDD.md`
   - `TESTING.md`
   - `features/` + `tests/`
   - `rfcs/` + README examples
4. If the contract is stable, prefer compatibility shims over mass renames.
5. If the contract itself must change, update the contract and its affected tests/features in one change set or escalate.
6. Re-run the smallest affected pytest target or feature file before widening scope.
</procedure>

<patterns>
<do>
  - Quote both sides of a contradiction before resolving it.
  - Add shims for `assembler`, `transcription.attributor`, `utils.retry`, and `PipelineConfig` when that is cheaper than rewriting broad test surfaces.
  - Record the resolved rule in `CLAUDE.md` or the relevant canonical doc when the contradiction is structural.
</do>
<dont>
  - Don't change tests just because they fail -> first confirm whether the spec or the test is stale.
  - Don't reconcile drift by inventing a third naming scheme -> converge on the canonical one or add a compatibility layer.
  - Don't widen a refactor while canonical docs are unsettled -> settle names and contracts first.
</dont>
</patterns>

<examples>
Example: module-name drift

```text
Observed:
- SDD.md says `parler/transcription/assembly.py`
- tests/unit/test_chunk_assembly.py imports `parler.transcription.assembler`

Preferred resolution:
1. Implement the canonical module.
2. Add `parler/transcription/assembler.py` as a shim or alias if needed.
3. Remove the shim only when docs and tests are normalized together.
```

Example: config-type drift

```text
Observed:
- tests/unit/* use `ParlerConfig`
- tests/e2e/* use `PipelineConfig`

Preferred resolution:
1. Keep `ParlerConfig` canonical.
2. Export `PipelineConfig = ParlerConfig` temporarily if E2E compatibility is needed.
```
</examples>

<troubleshooting>
| Symptom | Cause | Fix |
|---|---|---|
| Every test fails with import errors under different module paths | drift spans multiple files | choose the canonical path once, then add targeted shims |
| A test contradicts `SPEC.md` wording | stale test or feature | update the test/feature with the same change that documents the resolution |
| E2E looks broken before code runs | fixtures/docs drift, not runtime logic | inspect `tests/fixtures/README.md` and committed assets first |
</troubleshooting>

<references>
- `SPEC.md`: canonical product contract
- `SDD.md`: canonical module map and component contracts
- `TESTING.md`: verification layers and traceability
- `IMPLEMENTATION_PLAN.md`: preferred build order
- `tests/unit/test_chunk_assembly.py`: `assembly` vs `assembler` drift
- `tests/unit/test_speaker_attribution.py`: `transcription.attributor` drift
- `tests/integration/test_retry_behavior.py`: `util` vs `utils` drift
- `tests/e2e/test_full_pipeline_fr.py`: `PipelineConfig` drift and missing fixture expectations
</references>
