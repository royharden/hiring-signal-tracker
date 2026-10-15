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

Any admitted record field with a processing error or block makes the method
partial, even when every expected ID has a record. Every denominator and error/
blocked count remains accounted. Factual acquisition coverage stays separate;
the effective released partition coverage is partial, so charts use a gap and
percentage-point changes are unavailable. This conservative whole-method rule
can also withhold otherwise usable fields when another field fails. Uncertain/
conflicting abstentions and stated salaries with unknown units remain distinct;
they are not automatically processing failures. A supported valid zero still
releases as zero under explicit V2.

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
with the same method/config fingerprint, exact release policy and source scope.
Every exported format includes monthly policy/version/method/scope bindings.
Gold-sample predictions
are explicitly labelled sample estimates, not population trends. Prediction quality,
accuracy, human agreement, measured cost and uncertainty remain unprovided.

The default remains exact conservative V1 (`single-partition-all-siblings-min10-v1`):
any cell below ten, including zero, suppresses every sibling count/share/interval.
An unused error class can therefore withhold an otherwise supported field.
Explicit opt-in V2 (`single-partition-all-siblings-nonzero-min10-v2`) releases a
whole cohort of at least ten only when each cell is zero or at least ten. True
zero is count/share zero. Any positive cell from one through nine suppresses all
siblings, including zeros and intervals. Cohorts below ten withhold their
denominator under either policy. Monthly cohorts default to V1; callers must
select V2 explicitly. Policy changes break percentage-point comparisons and chart
segments even when all other versions match. Neither
policy solves all cross-field or cross-release correlations or establishes
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
The original-synthetic rules CLI and public report commands join these libraries.
Semantic CLI and required independent data/evaluation remain unfinished work.
