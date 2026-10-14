# Hiring Signal Tracker

Hiring Signal Tracker is being built to measure AI-engineering and portfolio-request signals in curated job postings and publish monthly aggregates. The current package provides a keyless readiness command, publication checks, strict contracts and tested local deterministic libraries. CLI workflow integration, semantic providers, annotation, evaluation and rendered charts remain upcoming work.

## Quickstart

With Python 3.12 and uv installed:

```sh
uv sync --frozen
uv run hst status --json
```

The readiness response identifies the current `deterministic_libraries_only` stage, implemented libraries and unavailable workflows. It reads no posting data or credentials and requires no network after installation.

## Current commands

```sh
uv run hst status
uv run hst status --json
uv run python scripts/check_public_files.py
```

`scripts/demo.py --offline` and `scripts/eval.py --dataset synthetic --offline` currently return `workflow_not_implemented` with exit code 2. They create no result files. This keeps an unfinished workflow from producing a passing demo or benchmark receipt.

## Architecture

- `src/hiring_signals/cli.py`: readiness and explicit workflow availability.
- `src/hiring_signals/public_files.py`: bounded checks of staged product paths and text for private material.
- `src/hiring_signals/contracts.py`: 37 mandatory field IDs, 30 separate skill judgments, evidence/process consistency and closed private derivations. Actor references are self-attestation, not authentication.
- `src/hiring_signals/ingest/`: bounded original-synthetic transport, reviewed-term transient redaction and generation-validating private HMAC/SQLite state. No live HN acquisition is implemented.
- `src/hiring_signals/shared/aggregate_privacy/`: independent closed single-partition min-ten/all-sibling suppression and format-neutral released scalars; no rendered chart/report pipeline.
- `src/hiring_signals/shared/skill_dictionary/`: thirty original alias entries, explicit clause-local requests/exclusions/unknowns and source-bound byte references; standalone M2/M9 consumers are exercised.
- `src/hiring_signals/extract/rules.py`: narrow deterministic duty/application/category/salary/location grammar and actual private-state adapter. No calibrated confidence or empirical extraction-quality claim.
- `config/`: complete pending taxonomy/experiment inventories and generated JSON Schema. Run `uv run python scripts/generate_schemas.py` to regenerate. Python runtime validators enforce additional cross-field constraints; JSON Schema alone is insufficient.
- `docs/BOUNDARIES.proposed.md`: implemented domain boundary and remaining proposals; no shared provider implementation.
- `tests/`: command, detached-copy, no-network/no-credential, domain/privacy-boundary and publication-guard controls.

The later workflow will join these libraries to counting and rules/Jev/generative comparison. Independently authored frozen synthetic data, real human gold and the gold/report example remain required. Upstream modules will be integrated only from verified owner sources with provenance and compatibility tests.

## Results and cost

Extraction accuracy, per-field reports, model usage/cost, four-month trends and human self-agreement are **not yet measured**. No provider implementation or live call exists in this package. `results/README.md` records the present evidence scope without placeholder performance numbers.

## Verification

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_public_files.py
```

Tests exercise command entry points, unavailable-workflow failures, detached consumers, syntax controls, malformed records and privacy/cancel/crash boundaries. Syntax handoracles are not frozen Gold or measured quality. Configured CI discovers the full test tree; it does not certify a complete app or an executed hosted workflow.

## Data and limits

The planned real benchmark requires 300 human-corrected postings, a frozen grouped dev/held-out split, a labeling pilot and 20 blind repeat annotations at least seven days later. Synthetic fixtures will support offline regression and demonstrations; they will not replace those real measurements.

Live Hacker News import remains subject to a recorded current terms/data grant. API availability alone does not establish reuse rights. Third-party text will remain transient in memory; real source mappings, labels and run state will remain private, and public output will be aggregates only. Job-board scraping, company-level reporting, application tracking and public per-posting rows are outside the MVP.

Coding agents wrote this package. Local verification covers the commands, contracts and guard above; later workflow, provider, reusable-module and independent app acceptance evidence remain separate.
