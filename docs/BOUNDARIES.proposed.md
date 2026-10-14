# Proposed app boundaries

Status: specification only. No extraction, annotation, generic shared schema, provider, persistence or aggregate module is implemented by this scaffold.

| Boundary | Intended input/output and invariant |
|---|---|
| Transient source envelope | Owner-selected posting text, source identity and month; no application-written text persistence. |
| Safe private record | Opaque stable item identity, source fingerprint/revision, month, complete labels/predictions, evidence/process status and versioned provenance; no posting snippets or links. |
| Field prediction | Explicit stated/negative/not_stated/multiple/conflicting evidence, separate uncertainty/invalid/provider error; no default false/full_time/onsite. |
| Skill dictionary | Thirty separate original taxonomy entries with scored alias/ambiguity rules; once per posting. |
| Salary/location candidates | Generated in code, selected from candidates; unknown units remain stated/abstained, never guessed annual or invented location. |
| Gold/experiment | Human-corrected labels, immutable source/label/group/split/rubric hashes, disclosed assistance and blind repeat evidence. |
| Evaluation/report | Fixed expected IDs and all method outcomes; per-class supports and metrics, paired group intervals, stale/unavailable and error denominators; no synthetic-as-real accuracy. |
| Public aggregates | Closed allowlisted metrics, denominators, method/evidence status and coherent complementary suppression across formats; no identities or per-item rows. |

The general evalkit/rulings and providers/callledger are owned upstream. Their exact adopted contracts, actual source commits, licenses and detached-consumer tests are prerequisites for implementation/vendoring. Local proposals do not create a competing canonical library. Full tagged pointers and image geometry are unnecessary for the basic local text scaffold.
