# Local ingest and privacy boundaries

This slice implements library boundaries and original synthetic controls. CLI
ingestion/extraction, HN acquisition, annotation, evaluation and rendered reports
remain unavailable. No third-party data, API credential or provider was accessed.

Local transport fixtures validate exact allowed HTTPS origin/root, hiring title
and requested calendar month. Bounds are four unique months, 600 top-level posts,
10 MiB decompressed bytes shared across attempts, 10,000 nodes including root,
depth eight with root at zero, and 20,000 characters per post. A size/node/depth/
top-level overrun refuses the whole month as partial, never a complete prefix.
Deleted/dead/empty/invalid/oversized posts remain in accounting. Root failure and
malformed/duplicate-key JSON stay failed. Simulated transport admits at most two
attempts, cumulative 30 seconds, sequential one request per second and Retry-After.
It executes no requests, waits or redirects and proves no actual TLS/API readiness.

Author/by fields do not enter `SyntheticPost`. Reviewed supplied identity terms
and HTTP(S)/email links are replaced only in memory. Link kinds are caller-declared
booleans, not extracted portfolio judgments. Unsupported markup/link schemes,
unreviewed inventories and UTF-8 overflow quarantine the input. Supplied-term
knowledge is limited; this is not universal de-identification. The redacted input
hash and byte coordinates differ from the private raw fingerprint/redaction spans.
S6's original screen identity will refer to the supplied redacted text. No shared
screen implementation is installed in this slice.

`PrivateState` requires an explicit owner-local directory outside (and not an
ancestor of) the actual product root, such as an outer-shell `.owner-state/`.
It generates a separate 32-byte identity secret, never an API key, in `identity.key`.
Full domain-separated HMAC IDs/group digests and numeric source mappings are
**pseudonymous private data**, not anonymous data. SQLite stores only validated
private derived records and allowlisted numeric IDs/months/digests; never text,
company/person terms, URLs or arbitrary errors. Restrict owner access to this
directory using Windows ACLs; POSIX creation modes alone do not prove Windows ACLs.
Do not print keys, place values in argv, copy into product files or publish mappings.

Back up the identity key plus a consistent SQLite backup together while closed,
or use SQLite's consistent backup mechanism before archiving it. Restore into a
separate private directory, then verify HMAC/source equivalence and safe records.
Missing keys refuse regeneration when a database exists. A changed source hash
requires an explicit successor rather than silently rewriting frozen identity.
Backup equivalence does not authenticate the input or make cancelled work valid.

Each processing lease has an explicit positive lifetime and injected monotonic
clock, with no adopted default. Cancellation advances a durable epoch; queued
writes and another handle's old generation are rejected. Writes recheck active
lease/generation after SQL and before commit under the same lock/transaction.
Expiry clears its in-memory mappings when observed; there is no background timer.
Close invalidates all handle leases and drops key references. Python references
may outlive the caller; this is not guaranteed erasure or process isolation.
Tests terminate an actual subprocess between SQL and commit and verify rollback,
then scan private files/journals for original synthetic plaintext canaries.

The reusable `shared/aggregate_privacy` package owns independent closed models.
It accepts one exhaustive disjoint partition per field/month/method, minimum ten,
and conservatively suppresses all siblings if any cell is below ten. Every future
format receives the same validated released scalars. Incomplete/suppressed inputs
cannot be complete trends. Cross-release correlations and additional overlapping
marginals are not solved; a later reporter needs an addressed policy for changes.

Only explicitly original synthetic transport fixtures and planted test controls
are committed. Those examples are not retained third-party text or human gold.
Never log `ValidationError.errors()` or rejected input payloads. Real input rights,
human labels, population accuracy, independent review and product acceptance remain
separate gates. Existing schema contracts were not changed by this slice.
