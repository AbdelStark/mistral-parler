# RFCs — parler

Component design records for the `parler` project.

Canonical baseline documents now live at the repository root:

- [`SPEC.md`](../SPEC.md)
- [`SDD.md`](../SDD.md)
- [`TESTING.md`](../TESTING.md)
- [`IMPLEMENTATION_PLAN.md`](../IMPLEMENTATION_PLAN.md)

If an RFC conflicts with those documents, the root documents win until the RFC is
updated.

| RFC | Title | Status |
|-----|-------|--------|
| [RFC-0001](./RFC-0001-architecture-and-pipeline.md) | Architecture and Processing Pipeline | Draft, pending sync with v0.2 baseline |
| [RFC-0002](./RFC-0002-voxtral-multilingual-transcription.md) | Voxtral Integration and Multilingual Handling | Draft, pending sync with v0.2 baseline |
| [RFC-0003](./RFC-0003-decision-extraction-schema.md) | Decision Extraction Schema | Draft, pending sync with v0.2 baseline |
| [RFC-0004](./RFC-0004-speaker-attribution.md) | Speaker Attribution and Diarization | Draft, pending sync with v0.2 baseline |
| [RFC-0005](./RFC-0005-report-format-and-export.md) | Report Format and Export Integrations | Draft, pending sync with v0.2 baseline |

## RFC process

1. Copy an existing RFC as a template
2. Fill in Abstract, Motivation, Design, Alternatives, Open Questions
3. Open a PR for discussion
4. Status moves: `Draft` → `Accepted` → `Implemented` | `Withdrawn`
