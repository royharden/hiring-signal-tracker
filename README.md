# Hiring Signal Tracker

Hiring Signal Tracker is being built to measure AI-engineering and portfolio-request signals in curated job postings and publish monthly aggregates. The current package provides a keyless original-synthetic rules workflow, public reports, private synthetic DEV rules evaluation with an optional reference baseline, and a synthetic DEV annotation CLI. Semantic CLI, live execution, heldout evaluation and human measurements remain unfinished.

## Quickstart

With Python 3.12 and uv installed:

```sh
uv sync --frozen
uv run hst status --json
```

The readiness response identifies the current `original_synthetic_cli_and_libraries` stage, implemented capabilities and unavailable workflows. Readiness reads no posting data or credentials and requires no network after installation. Its compatible `evaluation_status` describes the default rules profile; `evaluation_status_scope` and `reference_baseline_status` distinguish the explicit optional synthetic DEV baseline.

## Current commands

```sh
uv run hst status
uv run hst status --json
uv run hst run-synthetic --input original-source.json --private-dir /owner/private/hst --out /owner/reports/new-report --lease-seconds 120 --policy v2
uv run hst report verify --directory /owner/reports/new-report
uv run hst report limitations --directory /owner/private/dev/new-results/sample-report
uv run hst eval --offline --show-bindings
uv run hst annotate --show-bindings
uv run python scripts/check_public_files.py
```

`scripts/demo.py --offline` and evaluation without explicit inputs return `workflow_not_implemented` with exit code2 and create no results. Explicit evaluation accepts an owner-admitted canonical DEV manifest, original-synthetic source JSONL, exact file hashes and a new private output directory. By default it runs rules/comparison/statistics with Jev/generation/dev-majority not_run; the explicit support option below adds actual DEV-majority fitting. Read [the runnable input, normal and refusal guide](docs/evaluation-workflow.md). No implicit dataset, heldout, model call or human-quality claim is supplied.

`run-synthetic` requires an explicitly supplied original manifest and owner-private state outside the checkout. It preserves unreviewed/blocked rows in denominators and exports only closed released aggregates. Read [the input and state guide](docs/synthetic-workflow.md) before running it. Exit3 denotes partial/no-eligible processing; even exit0 does not establish quality or full workflow acceptance. Report export/verification accepts only bounded closed public JSON and new destinations.

The DEV evaluator optionally takes `--sample-months YYYY-MM YYYY-MM YYYY-MM YYYY-MM`
to produce privacy-safe sample-prediction JSON/Markdown/HTML/SVG and a reproducible
limitations report. It uses the existing suppression policy, preserves missing
months as gaps and keeps private reference/accuracy artifacts outside the nested
report. Sample predictions are not population trends; local artifacts grant no
external publication or measured-quality authority.

An explicit `--dev-majority-min-support N` option adds the DEV-majority reference
baseline to private evaluation. Obtain matching bindings with that option before
preparing the admitted manifest. Unsupported fields abstain; learned guesses do
not fabricate extraction evidence. The same-DEV comparison is resubstitution,
not heldout quality or a production default. See the evaluation guide for the
exact opt-in and remaining data/Human requirements.

`report limitations` prints reproducible Markdown from a verified closed rules
sample report alone. It does not reopen private evaluator inputs or write files.
Tampered, unsealed, population-scope or other-method reports refuse. Verification
proves local artifact consistency, not source authenticity or rights.

`annotate` accepts a hashed original-synthetic DEV manifest and an existing owner-matched private journal directory. It requires all37 explicit keyboard choices and returns real durable receipt counts; it cannot authenticate a Human or export Gold. Cancel/skip/EOF before submission writes no labels. Read [the manifest, ownership and error guide](docs/annotation-guide.md#synthetic-dev-annotation-cli) before use.

## Architecture

- `src/hiring_signals/cli.py`: readiness and explicit workflow availability.
- `src/hiring_signals/workflow.py`: supplied-original-synthetic transport/privacy/rules/private-state/population/report joins and bounded public report IO; no network/model calls or implicit corpus.
- `src/hiring_signals/evaluation/`: canonical label codecs, concrete execution bindings, full37-field comparison and private class/skill/salary/calibration/paired statistics. The synthetic DEV CLI joins rules to supplied frozen references and private artifact hashes, without heldout reading or model access. Optional DEV-majority fitting is explicit; bootstrap is not run by this CLI.
- `src/hiring_signals/public_files.py`: bounded checks of staged product paths and text for private material.
- `src/hiring_signals/contracts.py`: 37 mandatory field IDs, 30 separate skill judgments, evidence/process consistency and closed private derivations. Actor references are self-attestation, not authentication.
- `src/hiring_signals/ingest/`: bounded original-synthetic transport, reviewed-term transient redaction and generation-validating private HMAC/SQLite state. No live HN acquisition is implemented.
- `src/hiring_signals/shared/aggregate_privacy/`: independent closed single-partition min-ten/all-sibling suppression and format-neutral released scalars. Conservative V1 remains default; explicit V2 allows true zeros only when every positive cell has support of at least ten.
- `src/hiring_signals/shared/skill_dictionary/`: thirty original alias entries, explicit clause-local requests/exclusions/unknowns and source-bound byte references; standalone M2/M9 consumers are exercised.
- `src/hiring_signals/extract/rules.py`: narrow deterministic duty/application/category/salary/location grammar and actual private-state adapter. No calibrated confidence or empirical extraction-quality claim.
- `src/hiring_signals/reporting/`: expected-ID monthly accounting and closed JSON/Markdown/HTML/four-month SVG exports. Missing/suppressed/partial points are gaps; no measured-quality rows. See `docs/reporting.md` for scope, version, denominator and current conservative suppression limits.
- `src/hiring_signals/annotation/` and `adapters/rulings.py`: transient37-field keyboard/session controls and safe intents mapped to the actual canonical private journal, with fsync acknowledgements, current-source checks and head conflicts. No implicit absence, blind prefill or mock-as-human Gold. The explicit synthetic DEV CLI joins these to a real private journal; Human/Gold validation remains pending; see `docs/annotation-guide.md` and `docs/gold-format.md`.
- `src/hiring_signals/shared/screen/` and `adapters/screen.py`: unchanged canonical offline rules/preparation plus an S10 gate over complete reviewed privacy-redacted input. Actual holds block semantic input; deterministic outcomes remain separate. Model probabilities stay null. See `VENDORED.md`; S6 typed-screen integration remains pending.
- `src/hiring_signals/shared/providers/` and `shared/callledger/`: unchanged canonical offline controller and actual SQLite accounting, with moved allocation/replay/error/cumulative-limit controls. Synthetic replies/prices remain synthetic. Live adapters remain pending; see `docs/providers.md`.
- `extract/jev.py`, `extract/generative.py`, `extract/semantic.py` and `adapters/providers.py`: all69 native questions/all37 field mappings, closed generation schema and actual zero-outbound synthetic Jev lookup orchestration. Absence, explicit negatives, unknown units and partial failures remain distinct. `adapters/generation.py` runs the full37 generation decoder with actual canonical counted fixed repair in injected simulation: two total transport/content attempts, at most one repair, actual counters/ledger liability and final physical-request provenance. It supplies no SDK/live-model evidence. Semantic CLI joins and quality/data gates remain pending; see `docs/providers.md`.
- `config/`: complete pending taxonomy/experiment inventories and generated JSON Schema. Run `uv run python scripts/generate_schemas.py` to regenerate. Python runtime validators enforce additional cross-field constraints; JSON Schema alone is insufficient.
- `docs/BOUNDARIES.proposed.md`: implemented domain boundary and remaining proposals. `docs/providers.md` records the actual offline provider scope and unfinished joins.
- `tests/`: command, detached-copy, no-network/no-credential, domain/privacy-boundary and publication-guard controls.

Local rules workflows join supplied synthetic inputs to population reporting or frozen DEV evaluation. Independent source/Gold admission remains outside the checkout. Semantic CLI comparisons, heldout execution, human Gold and agreement remain required. Upstream modules are integrated from verified owner sources with provenance and compatibility controls.

## Results and cost

Real extraction accuracy, model usage/cost, population trends and human self-agreement are **not yet measured**. The DEV evaluator computes private rules statistics against supplied synthetic/agent-provisional references; those values are not heldout or human-quality evidence. No live call or completed semantic CLI exists. `results/README.md` records the evidence scope without placeholder performance numbers.

## Verification

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_public_files.py
```

Tests exercise actual keyless CLI/state/report joins, unavailable-workflow failures, detached consumers, syntax controls, malformed records and privacy/cancel/crash boundaries. Small original wiring and numeric controls are not the independent required fixture corpus, frozen Gold or measured quality. Configured CI discovers the full test tree; it does not certify a complete app or a hosted workflow. Current limits are recorded in [LIMITATIONS](docs/LIMITATIONS.md).

## Data and limits

The planned real benchmark requires 300 human-corrected postings, a frozen grouped dev/held-out split, a labeling pilot and 20 blind repeat annotations at least seven days later. Synthetic fixtures will support offline regression and demonstrations; they will not replace those real measurements.

Live Hacker News import remains subject to a recorded current terms/data grant. API availability alone does not establish reuse rights. Third-party text will remain transient in memory; real source mappings, labels and run state will remain private, and public output will be aggregates only. Job-board scraping, company-level reporting, application tracking and public per-posting rows are outside the MVP.

Coding agents wrote this package. Local verification covers the commands, contracts and guard above; later workflow, provider, reusable-module and independent app acceptance evidence remain separate.

## Installed runtime assets

A built wheel includes the exact annotation rubric, VENDORED record and
third-party LICENSES notices. `annotate --show-bindings` and
`eval --offline --show-bindings` share package asset resolution; they do not
require a checkout or a particular cwd.
The source rubric remains `docs/annotation-guide.md`; wheel construction copies
that file directly, without maintaining a second committed rubric.

Obtain fresh bindings from the actual runtime before preparing a new manifest.
Code/asset changes invalidate older bindings even at the same package version.
Installed-wheel checks also exercise rules evaluation on fresh original synthetic
syntax controls, the suppressed sample report and reproducible limitations, plus
wrong-hash/malformed-source refusal before output. These are regression controls,
not the prior admitted DEV inputs or a measured benchmark. Installed annotation
with source inputs, other commands, other operating systems and hosted Bolt
operation remain unqualified.
