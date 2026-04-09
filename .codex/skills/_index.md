# Skill Registry

Last updated: 2026-04-09

Observed existing repo-local skills before this pass: none.

| Skill | File | Triggers | Priority |
|---|---|---|---|
| Contract Reconciliation | `contract-reconciliation.md` | spec drift, import drift, canonical docs vs tests, RFC mismatch, dependency mismatch | Core |
| Vertical Slice Implementation | `vertical-slice-implementation.md` | create `parler/`, phase work, bootstrap modules, test-backed build-out | Core |
| Test-Driven Delivery | `test-driven-delivery.md` | pytest, BDD, property tests, coverage, mutation, benchmark, fixture use | Core |
| Mistral Pipeline | `mistral-pipeline.md` | Voxtral, Mistral, transcription, extraction, cache, retry, parser, quality | Core |
| Orchestrator and CLI | `orchestrator-and-cli.md` | `ProcessingState`, checkpoint, resume, exit codes, `parler process`, `parler cache` | Core |

## Activation Order

1. Use `contract-reconciliation.md` first when sources disagree.
2. Use `vertical-slice-implementation.md` when creating or extending runtime code.
3. Load a domain skill (`mistral-pipeline.md` or `orchestrator-and-cli.md`) for implementation details.
4. Load `test-driven-delivery.md` before widening verification or adding tests.

## Current Gap Analysis

High-priority gaps addressed in this pass:
- No repo-local guidance for spec-vs-test drift resolution
- No guidance for growing the runtime package from the phase plan
- No reusable workflow for the layered pytest/BDD/property/E2E suite
- No domain guidance for Mistral/Voxtral adapters, parser normalization, cache semantics, and checkpoint/CLI behavior
- No release/packaging baseline for `uv`-based development and publishing

Lower-priority recommended skills not scaffolded yet:
- [ ] `rendering-and-export.md` — add when Phase 6 work begins in earnest
- [ ] `fixture-generation.md` — add if synthetic fixture generation becomes recurring work
- [ ] `security-review.md` — add before handling real transcript/checkpoint data

## Known Baseline Risks

- Phase 1 through Phase 3 exist, but later domains are still missing: attribution, decision extraction, exports, and the broader CLI/report flows built on top of them.
- E2E fixture assets listed in `tests/fixtures/README.md` are not committed yet.
- Tests and docs still drift on module names: `assembly` vs `assembler`, `attribution` vs `transcription.attributor`, and `util` vs `utils`.
- `PipelineConfig` compatibility is currently provided by aliasing `ParlerConfig`.
- `uv`, `uv_build`, `PyYAML`, and `requests` are now declared and validated; keep future tooling changes inside the same packaging model.
- CI intentionally validates only the implemented Phase 1-3 slice; widen it only when later domains are actually delivered.
