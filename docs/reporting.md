# Population accounting and public reports

The reporting library accepts an explicitly admitted private monthly cohort:
expected pseudonymous IDs, method/config-version fingerprint, source coverage,
scope and closed derived records. IDs must be unique; records must belong to the
same month/method/config version and expected cohort. Missing predictions stay in
every field denominator as declared unavailable/error or blocked outcomes. An
explicitly not-run method emits no fabricated field predictions or zero rates.
Caller-supplied scope/coverage/version metadata is not authenticated acquisition,
sampling, frozen Gold or configuration provenance; the authorized workflow must
bind those inputs before a real run.

Every run field produces an exhaustive partition over all expected IDs, including
not_stated, conflicts, uncertainty, failures and blocks. Salary distinguishes
stated normalized ranges from stated unknown units and explicit none. Only the
actual aggregate_privacy released projection crosses the public boundary. No
source IDs, organization tokens, locations, names, links, snippets or arbitrary
marginal/cohort cuts are accepted by the public report models.

JSON, Markdown tables, HTML and an accessible headless SVG use the same released
values. The chart has four explicit consecutive month slots. Missing, failed,
partial, not-run and suppressed points are gaps, never invented zero observations.
Percentage-point changes/line segments require adjacent complete released points
with the same method/config fingerprint and source scope. Gold-sample predictions
are explicitly labelled sample estimates, not population trends. Prediction quality,
accuracy, human agreement, measured cost and uncertainty remain unprovided.

Current policy is the exact conservative V1: any cell below ten, including zero,
suppresses every sibling count/share/interval. An unused error class can therefore
withhold an otherwise supported field. A bounded zero-cell successor is under
separate semantic review; the renderer does not silently alter the policy. The
policy does not solve all cross-field or cross-release correlations or establish
anonymity. Additional overlapping cuts require an addressed successor policy.

`export_report` writes a new explicit destination only, with fixed public asset
names and a manifest written last. Existing directories/files are preserved.
An interrupted write can leave an unsealed directory; `verify_report` refuses a
missing manifest, changed hashes, extra/unsafe asset closure or renderings that do
not reproduce the closed JSON projection. Updating a manifest's own hashes alone
cannot legitimize arbitrary HTML. Verification proves this bounded local artifact
closure, not recipient delivery, source authenticity or external publication.

SVG generation uses stdlib XML for a portable, dependency-free headless renderer.
This is the current MVP implementation choice rather than a new plotting-runtime
install. Geometry/markup/export tests are not browser visual QA. No independent
four-month posting corpus/Gold, live data or empirical benchmark was authored or
run for this slice; tests use small original numeric and boundary controls.
CLI workflow integration and any required independent data/evaluation remain
separate unfinished work.
