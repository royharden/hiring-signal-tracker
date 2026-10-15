# Aggregate privacy core

Copy this whole directory into a consumer package. It uses only Python 3.12,
stdlib and Pydantic v2; it imports no owner app, contracts, ingest, provider or
storage module. The enclosing product MIT license applies; include that license
and actual source provenance when reusing it. This source is not a vendor receipt.

`Partition.model_validate_json` requires one exhaustive ordered, disjoint field
partition. Counts include absent/conflicting/uncertain/error/blocked classes and
sum to the denominator. There is no arbitrary company/cohort/marginal-cut input.
By default, `release_partition` uses `single-partition-all-siblings-min10-v1` and
withholds **all** sibling counts, shares and intervals when
any cell is below ten, including zero cells. This intentionally limits utility;
a supported cohort with any rare class is still suppressed. A cohort below ten
also loses its denominator. Partial/failed coverage never becomes a complete trend.

An explicit `policy=POLICY_V2` selects
`single-partition-all-siblings-nonzero-min10-v2`: a cohort at least ten with all
cells zero or at least ten may release true zero counts/shares. Any positive cell
one through nine hides every sibling and interval, including zeros. V1 defaults
and vectors are preserved. Consumers must bind exact policy/version/scope and
refuse trend comparisons across policies. No positive support threshold is lowered.

`format_projection` gives JSON/table/chart/HTML consumers the same closed released
scalars, after revalidation. It does not render tables, charts or a report pipeline.
Renderers must never recover private counts from the input partition. Only this
released projection is a public boundary. `schemas.json` describes shape; runtime
validators also enforce exhaustive classes, sums, shares and suppression.

This is a bounded single-partition policy, **not** proof of anonymity or protection
against every correlation, repeated release or reconstructed overlapping cohort.
No API supports arbitrary overlapping cuts. A later integrated reporter must
preserve this restriction and avoid assembling additional marginals without a
reviewed successor policy. Self-attested human evidence does not authenticate labels.
