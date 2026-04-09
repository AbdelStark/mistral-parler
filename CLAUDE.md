<identity>
`parler` is a local-first Python CLI/library that turns recorded audio or video into a structured Decision Log with transcription, speaker resolution, extraction, rendering, and optional exports.
</identity>

<stack>

| Layer | Technology | Version | Notes |
|---|---|---:|---|
| Runtime | Python | `>=3.11` | local interpreter seen here: `3.14.3` [verify] |
| Build backend | Hatchling | [verify] | configured in `pyproject.toml`; no lockfile committed |
| Package manager | `python3 -m pip` | [verify] | use editable installs once the `parler/` package exists |
| CLI | Click | `>=8.1` | `parler = parler.cli:main` |
| Core models | stdlib dataclasses + typed validation | current | canonical shapes live in `SDD.md` |
| LLM vendor SDK | `mistralai` | `>=1.0.0` | Voxtral transcription + Mistral extraction [verify] |
| Rendering | Jinja2 + Rich | `>=3.1`, `>=13.0` | HTML/Markdown/terminal output |
| Testing | pytest | `>=8.0` | plus `pytest-bdd`, `hypothesis`, `pytest-benchmark`, `pytest-asyncio` |
| Lint / format | Ruff | `>=0.4` | `ruff check`, `ruff format` |
| Type check | mypy / pyright | `>=1.9` / `>=1.1` | mypy is configured as strict |
| Optional speaker diarization | `pyannote.audio` | `>=3.1` | optional extra: `parler[diarize]` |
| External binary | FFmpeg | [verify] | required only when normalization/conversion is needed |

</stack>

<repo_state>

- Repository status on `2026-04-09`: implementation-ready baseline, not implementation-complete.
- The `parler/` runtime package described by `SDD.md` does not exist yet. Agents are expected to create it.
- No CI workflow file is committed under `.github/workflows/`.
- E2E fixture audio/transcript/extraction assets referenced by tests are not committed yet; only `tests/fixtures/decision_logs/fr_meeting_5min_expected.json` exists.
- Git history is linear and docs/tests-heavy; current branch is `main`.

</repo_state>

<structure>

Current repository:

```text
README.md                # Public project overview [gated]
SPEC.md                  # Canonical product contract [gated]
SDD.md                   # Canonical software design and module map [gated]
TESTING.md               # Canonical verification contract [gated]
IMPLEMENTATION_PLAN.md   # Phase-by-phase build order [gated]
rfcs/                    # Historical component records; SPEC/SDD win on conflict [gated]
features/                # BDD acceptance contracts [gated]
tests/                   # pytest TDD/integration/property/E2E/benchmark contracts [gated]
tests/fixtures/          # Synthetic fixture policy; actual audio/transcript assets mostly missing [gated]
parler/                  # Expected runtime package; absent as of 2026-04-09 [agent: create/modify]
.codex/skills/           # Repo-local agent skills [agent: create/modify]
.claude/skills -> ../.codex/skills
.agents/skills -> ../.codex/skills
CLAUDE.md                # Primary agent context [agent: modify]
agents.md                # Multi-agent orchestration protocol [agent: modify]
```

Expected package boundary from `SDD.md`:

```text
parler/
  cli.py
  config.py
  errors.py
  models.py
  prompts/
  audio/
  transcription/
  attribution/
  extraction/
  rendering/
  export/
  pipeline/
  util/                  # tests still reference `parler.utils.retry`; keep a shim until drift is resolved
```

</structure>

<commands>

Commands marked `Phase 1+` assume the `parler/` package skeleton exists.

| Task | Command | Phase | Notes |
|---|---|---|---|
| Read canonical headings | `rg -n "^## |^### " SPEC.md SDD.md TESTING.md IMPLEMENTATION_PLAN.md` | now | fastest orientation pass |
| Bootstrap package skeleton | `mkdir -p parler/{audio,transcription,attribution,extraction,rendering,export,pipeline,util,prompts}` | now | create only the slice you need plus `__init__.py` files |
| Install dev deps | `python3 -m pip install -e '.[dev]'` | Phase 1+ | likely blocked until `parler/` exists |
| Focused unit slice | `pytest tests/unit/test_config_loading.py -q` | Phase 1+ | recommended first green test |
| Fast verification | `pytest tests/unit tests/integration tests/property features -v --cov=parler` | Phase 1+ | canonical fast path from `TESTING.md` |
| E2E | `pytest tests/e2e -v -s -m slow` | Phase 8 | requires `MISTRAL_API_KEY` and generated fixtures [verify] |
| Benchmarks | `pytest tests/benchmarks --benchmark-only` | Phase 8 | not for day-to-day changes |
| Lint | `ruff check .` | Phase 1+ | run before finalizing |
| Format | `ruff format .` | Phase 1+ | repo formatting standard |
| Type check | `mypy parler/` | Phase 1+ | strict config in `pyproject.toml` |

</commands>

<conventions>
  <code_style>
    Naming: `snake_case` modules/functions, `PascalCase` classes, `SCREAMING_SNAKE_CASE` constants.
    Files: keep Python modules in `snake_case.py`; preserve the SDD package split by domain.
    Imports: prefer absolute `parler.<domain>` imports inside the package. Add compatibility shims instead of broad import rewrites when tests and docs still drift.
    Models: prefer frozen dataclasses for canonical domain objects and processing state.
    Paths and I/O: use `pathlib.Path`, JSON/TOML/YAML parsing, and atomic file writes for cache/checkpoint artifacts.
    Errors: use the project-specific error hierarchy from `SDD.md`; do not invent shadowing names such as a custom `FileNotFoundError`.
    Secrets: API keys must be scrubbed from repr/str/log output and never written to checkpoints.
  </code_style>

  <patterns>
    <do>
      - Implement one `IMPLEMENTATION_PLAN.md` phase at a time; get the narrowest related tests green before expanding scope.
      - Treat `SPEC.md` and `SDD.md` as the source of truth; read them before assuming a test or RFC is correct.
      - Keep `assemble_chunks`, deadline resolution, parser normalization, retry logic, and cache-key builders pure and separately testable.
      - Preserve transcript segment IDs and timestamps; speaker turns are a rendering concern, not a mutation of canonical transcript structure.
      - Add compatibility shims for known drift points: `parler.transcription.assembler`, `parler.transcription.attributor`, `parler.utils.retry`, and `PipelineConfig`.
      - Keep export adapters isolated from renderer logic; local output success must survive export failure.
      - Treat checkpoints and caches as sensitive local artifacts; use restrictive permissions where the OS supports them.
    </do>
    <dont>
      - Don't invent new canonical model fields or rename canonical fields without updating the contract and its tests together.
      - Don't start with a full-pipeline implementation; build thin vertical slices from models/config outward.
      - Don't collapse transcript segments during attribution or assembly cleanup.
      - Don't key caches on filenames, paths, or weak `hash + model` shortcuts.
      - Don't read or commit real recordings, real transcripts, or real credentials into `tests/fixtures/`.
      - Don't treat RFC text or README examples as authoritative when they conflict with `SPEC.md` or `SDD.md`.
    </dont>
  </patterns>

  <commit_conventions>
    No commit-msg hook is present. Prefer concise conventional-style subjects such as `feat(audio): normalize unsupported containers` or `fix(extraction): drop low-confidence items`.
    Keep contract-only changes separate from implementation-only changes when possible.
  </commit_conventions>
</conventions>

<workflows>
  <implementation_slice>
    1. Read the relevant phase in `IMPLEMENTATION_PLAN.md`.
    2. Read the matching `SPEC.md` / `SDD.md` sections and the narrowest defining tests/features.
    3. If `parler/` is absent, create only the modules required for that slice plus `__init__.py`.
    4. Implement pure models/config/helpers first, then adapters, then orchestration glue.
    5. Add compatibility shims when import-path drift would otherwise block progress.
    6. Run the narrowest tests first, then widen to related unit/integration/BDD coverage.
    7. Finish with `ruff check .`, `mypy parler/`, and the fast verification path.
  </implementation_slice>

  <contract_reconciliation>
    1. Prove the contradiction with exact file paths before changing anything.
    2. Resolve authority in this order: `SPEC.md` + `SDD.md` -> `TESTING.md` -> `features/` + `tests/` -> `rfcs/` + README examples.
    3. If the contract is stable but imports drift, prefer a compatibility shim.
    4. If the contract itself must change, update docs/tests in the same change or get approval first.
    5. Re-run only the tests/features touched by the reconciliation, then widen once stable.
  </contract_reconciliation>

  <failure_triage>
    1. Start from the first failing import or assertion, not the noisiest traceback.
    2. Check for missing package skeleton, missing synthetic fixtures, or import-path drift before debugging business logic.
    3. Reproduce with the smallest failing unit/integration/BDD target.
    4. Fix one seam at a time: models/config -> helpers -> adapters -> orchestrator -> CLI.
    5. Only run E2E or benchmarks after the fast path is green.
  </failure_triage>
</workflows>

<boundaries>
  <zones>

| Path | Zone | Reason |
|---|---|---|
| `parler/` | autonomous | primary implementation surface; currently missing |
| `.codex/skills/`, `CLAUDE.md`, `agents.md` | autonomous | repo-local agent context |
| `README.md`, `SPEC.md`, `SDD.md`, `TESTING.md`, `IMPLEMENTATION_PLAN.md`, `pyproject.toml` | gated | public/tooling/canonical contract files |
| `rfcs/`, `features/`, `tests/`, `tests/fixtures/` | gated | contract and verification artifacts; update deliberately |
| `.env`, `.env.*`, `*.pem`, `*.key`, real recordings, real transcript dumps, real checkpoints/caches | forbidden | secrets or sensitive data |

  </zones>

  <forbidden>
    DO NOT modify under any circumstances:
    - `.env`, `.env.*`, credentials, tokens, private keys
    - user-supplied recordings or transcript dumps containing real meeting content
    - generated checkpoints or caches from real runs unless the user explicitly asks for cleanup
    - the `main` branch directly without explicit human instruction
  </forbidden>

  <gated>
    Modify only with explicit human approval, or when the task is explicitly about contract/tooling alignment:
    - `SPEC.md`, `SDD.md`, `TESTING.md`, `IMPLEMENTATION_PLAN.md`
    - `pyproject.toml` dependency/tooling changes
    - `README.md` public behavior/examples
    - `rfcs/`, `features/`, `tests/`, `tests/fixtures/`
    - any future `.github/workflows/` or release automation
  </gated>

  <safety_checks>
    Before any destructive operation (delete, overwrite, migration, fixture regeneration):
    1. State exactly what will be removed or replaced.
    2. State the contract or artifact that could break.
    3. Wait for confirmation.
  </safety_checks>
</boundaries>

<troubleshooting>
  <known_issues>

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'parler'` | repo has no runtime package yet | start Phase 1 and create the minimal `parler/` skeleton before running tests |
| `ModuleNotFoundError: parler.transcription.assembler` or `...attributor` | import-path drift between tests and `SDD.md` | add compatibility shims or coordinate an approved rename |
| `ModuleNotFoundError: parler.utils.retry` | tests import `utils`, design docs say `util` | expose `parler/utils/` shim or normalize references in one coordinated pass |
| `ConfigError: api_key` or CLI exit code `3` | `MISTRAL_API_KEY` / `PARLER_API_KEY` missing | set one env var; never hardcode the key |
| E2E fixture audio or transcript JSON missing | only the decision-log fixture is committed today | generate synthetic fixtures per `tests/fixtures/README.md` or skip E2E |
| YAML config support or export adapter tests fail [inference] | tests assume YAML parsing and `requests`-based exporters, but `pyproject.toml` does not currently declare `PyYAML` or `requests` | add the dependency or standardize the implementation in an approved tooling pass |

  </known_issues>

  <recovery_patterns>
    When stuck, follow this order:
    1. Re-read the relevant `SPEC.md` and `SDD.md` section.
    2. Confirm the file or import path named in the error actually exists.
    3. Check whether the failure is due to missing package skeleton, missing fixtures, or drift.
    4. Run the smallest relevant pytest target again after each fix.
    5. If the failure implies a contract change, stop and surface the contradiction explicitly.
  </recovery_patterns>
</troubleshooting>

<environment>
  - Harness: Codex-compatible local coding agent
  - File system scope: full read/write access to the repository
  - Network access: available in the current harness; verify before real API calls
  - Tool access: shell, git, local file editing; no repo-local CI/MCP automation is committed
  - Human interaction model: synchronous chat with explicit approval for gated zones
</environment>

<skills>
  Repo-local skills live in `.codex/skills/` with symlinks at `.claude/skills/` and `.agents/skills/`.
  Load only the skill relevant to the task.

  Available skills:
  - `contract-reconciliation.md`: resolve drift between spec, design, tests, features, and RFCs before coding
  - `vertical-slice-implementation.md`: build the missing `parler/` package in narrow, test-backed phases
  - `test-driven-delivery.md`: use the layered pytest/BDD/property/benchmark strategy correctly
  - `mistral-pipeline.md`: implement Voxtral/Mistral adapters, caches, quality gates, and parser normalization
  - `orchestrator-and-cli.md`: implement `ProcessingState`, checkpoint/resume, cost gating, and CLI commands

  Start with `_index.md` when you do not know which skill to load.
</skills>

<memory>
  <project_decisions>
    - `2026-04-09`: `SPEC.md` and `SDD.md` are the canonical contract; RFCs, README examples, and drifting tests yield to them.
    - `2026-04-09`: checkpoints serialize real stage artifacts and are sensitive local state; they are not hash-only metadata.
    - `2026-04-09`: diarization is hybrid and ordered as vendor diarization -> existing upstream IDs -> text-only fallback.
    - `2026-04-09`: transcription and extraction caches must use semantic fingerprints, not weak content-hash shortcuts.
    - `2026-04-09`: the repository is intentionally spec/test-first; grow `parler/` via vertical slices, not a full scaffold dump.
  </project_decisions>

  <lessons_learned>
    - Contract drift is the dominant project risk. Read the canonical docs before trusting an individual test import path.
    - E2E failure can mean missing synthetic fixtures, not broken application code.
    - Compatibility shims are cheaper and safer than broad rewrites while the baseline is still settling.
  </lessons_learned>
</memory>
