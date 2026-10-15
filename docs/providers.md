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

S10 semantic request composition, all37 field question/schema mappings and CLI
workflow remain unfinished. The S6 adapter still selects only rules screening;
its optional typed port is not connected to this actual controller by this source
integration. Later posting operations must admit every conditional child/retry
before the first dispatch and preserve the adopted two-attempt/four-attempt bounds.
No source/Gold/data-rights/human-evidence or external execution grant is implied.
