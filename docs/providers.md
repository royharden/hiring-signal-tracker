# Current offline provider and ledger boundary

The canonical S3 `shared/providers` and `shared/callledger` closures are copied
unchanged from the published source, with their MIT notice and source hashes in
`VENDORED.md`. They use Python 3.12, Pydantic and stdlib SQLite. No SDK, HTTP client,
credential loader, model download or live mode is installed by this integration.

The actual controller supports `mock`, `strict_replay` and `injected_simulation`.
The moved tests exercise real Ledger admission, reservations, settlement,
cumulative caller ceilings, retry bounds, source/context binding, atomic crash
boundaries, exact lookup and safe metadata projection. Injected transport replies
and capture bodies are synthetic controls. They do not establish supported live
models, account access, model performance, current prices or actual paid billing.

An offline lookup requires actual `Provider.admit_operation` over the complete
operation with an explicit zero outbound limit. The returned allocation and
`validate_replay_allocation` are real ledger APIs. A strict miss has no fallback,
attempt, invented response or current charge. Authored captures remain synthetic;
their result origin is mock, and historical source usage/cost remains separate
from the current lookup cost. No application source captures are enabled here.

The public moved conformance tree at `tests/shared_contracts/s3/` preserves all
listed fixtures, generated schemas and synthetic prices. Python test/helper
imports change only to the actual consumer namespace; private receipts retain
original/adapted hashes and diffs. The supplied synthetic price snapshot is not a
current-price file. Its utility copies only a caller-supplied validated snapshot
to a new destination; it does not fetch prices.

S10 now composes all37 fields into an exhaustive69-question native inventory:
two presence/decision Nouls for each headline, three category Choices, salary and
location Choices, and requested Noul plus requested/excluded/absent/conflicting/
uncertain Choice for each of30 skills. Packed mode submits69 questions once;
fixed split A/B submits9 and60 with the same complete source state. The partition
is chosen before admission; no primary call plus unfunded fallback is performed.
Neither format establishes a live token/capacity bound from byte length alone.

`SemanticInput` creates original/normalized DATA wrappers once, after the actual
rules gate, before provider preparation/admission. Source text and request bundles
remain transient, omit payloads from their repr and refuse pickle. A private
whole-source review coordinate is used for selected semantic labels; this is not
localized evidence accuracy. Source/config generations and every fixed child are
validated before the first exact lookup. Removed/stale sources block all fields;
missing groups remain explicit errors alongside valid other-group outcomes.
The actual synthetic-only Jev runner uses the canonical zero-outbound operation
and same ledger/budget/limits/allocation objects. Its source lock covers private
reuse writes. A miss has no fallback or invented prediction. Admission failures
retain not_attempted/admitted/unknown status instead of claiming no durable effect.

Choice distributions are validated unchanged by the native owner wire. Each
skill's requested Noul must agree with its selected class. Explicit false, absence,
multiple levels, conflicts and uncertainty remain distinct. Probability cutoffs
require an explicit policy with provenance/evidence reference; there is no
calibrated production default. The current runner accepts only synthetic-control
policies. A dev_calibrated string/ref alone would not prove calibration.

Generation composition uses the same37-field inventory, a strict supported JSON
schema and finite per-field uncalibrated self-confidence. Missing/extra fields,
invented candidates or malformed confidence reject as errors without defaults.
Salary selection in both methods uses at most one source-bound candidate from the
existing narrow deterministic salary grammar; unsupported range/currency/period
syntax limits candidate recall. Explicit unknown units remain a stated range with
normalization abstained. This bounded candidate choice reduces coverage and is not
a measured-quality claim. Location returns presence only; no location names.

Generation now uses the exact canonical fixed-repair successor through
`adapters/generation.py`. Only injected simulation with capture disabled is
accepted. A source/code/schema-bound pure validator checks all37 fields; valid
uncertainty stays an abstention and never buys another answer. Both original and
fixed-regeneration physical request proofs must be registered before the first
send. The canonical controller makes at most two total attempts including
transport retries, at most one counted content repair, with SDK retries disabled.
The app calls that controller once and does not supply another retry loop.

Closed private results retain actual child counters, returned attempt IDs and
final physical-request capture identity. Simulation authority totals are cumulative
synthetic ledger observations, not measured provider bills. An admitted preflight
failure can retain an outstanding hold; unknown first-call usage stays liability.
Removed/changed sources block predictions and stop a further repair; already spent
amounts are retained. Used children cannot automatically resume or invent replay.

Opt-in mock/strict-replay/capture modes remain unsupported. Default keyless Jev
lookups are unchanged. There is no SDK/authentication/live model or empirical
quality evidence from these authored controls. Semantic CLI, independent
60-post/four-month fixtures/Gold and empirical evaluation remain unfinished.
The S6 adapter still selects only rules screening;
its optional typed port is not connected to this actual controller by this source
integration. Later posting operations must admit every conditional child/retry
before the first dispatch and preserve the adopted two-attempt/four-attempt bounds.
No source/Gold/data-rights/human-evidence or external execution grant is implied.
