# Hiring Signal Tracker

Hiring Signal Tracker is being built to measure AI-engineering and portfolio-request signals in curated job postings and publish monthly aggregates. This initial package provides a keyless readiness command and publication checks; extraction, annotation, evaluation and charts are upcoming work.

## Quickstart

With Python 3.12 and uv installed:

```sh
uv sync --frozen
uv run hst status --json
```

The readiness response identifies the current `scaffold` stage, implemented commands and unavailable workflows. It reads no posting data or credentials and requires no network after installation.

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
- `docs/BOUNDARIES.proposed.md`: proposed app boundaries; no shared schema or provider implementation.
- `tests/`: command, detached-copy, no-network/no-credential and publication-guard controls.

The future Python core will perform bounded ingestion, code-based counting and rules/Jev/generative comparison. Its reusable dictionary, aggregate privacy policy and gold/report example remain required deliverables. Shared modules will be integrated only from verified owning-project sources with provenance and compatibility tests.

## Results and cost

Extraction accuracy, per-field reports, model usage/cost, four-month trends and human self-agreement are **not yet measured**. No provider implementation or live call exists in this scaffold. `results/README.md` records the present evidence scope without placeholder performance numbers.

## Verification

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_public_files.py
```

Tests exercise actual command entry points, unavailable-workflow failures, movement to a standalone directory and sensitive-material controls. The configured CI checks this scaffold; it does not certify a complete app or an executed hosted workflow.

## Data and limits

The planned real benchmark requires 300 human-corrected postings, a frozen grouped dev/held-out split, a labeling pilot and 20 blind repeat annotations at least seven days later. Synthetic fixtures will support offline regression and demonstrations; they will not replace those real measurements.

Live Hacker News import remains subject to a recorded current terms/data grant. API availability alone does not establish reuse rights. Third-party text will remain transient in memory; real source mappings, labels and run state will remain private, and public output will be aggregates only. Job-board scraping, company-level reporting, application tracking and public per-posting rows are outside the MVP.

Coding agents wrote this initial scaffold. Local verification covers the commands and guard above; later workflow, provider, reusable-module and independent app acceptance evidence remain separate.
