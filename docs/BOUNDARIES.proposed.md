# Proposed app boundaries

Status: app-owned classification/config contracts are implemented in `contracts.py`, with generated schema under `config/schemas`. Other rows remain proposals. No extraction, annotation, generic shared schema, provider, persistence or aggregate module is implemented.

The 37 field IDs include all 30 separately required skills. Absent booleans are null/ok/absent; explicit negatives are false/ok/explicit_negative with safe candidate coordinates. Failed/abstained categorical outputs are null, never default onsite/full_time. Multiple seniority requires two distinct levels; unresolved conflicting evidence abstains. Salary normalization preserves explicit decimal amounts/currency/period; unknown units remain stated with normalization abstained.

`TransientInput` omits text from repr and rejects JSON/dict/dataclass/pickle serialization. This is an ordinary Python boundary, not process isolation or guaranteed erasure. It validates the UTF-8 input hash and byte limit; candidate references validate coordinates and source-digest binding, not actual extraction or recall. `PrivateDerivedRecord` allows only finite domain fields and safe hashes; it is private pseudonymous data, not a public per-posting export. Public config/schema inventories contain no posting data. HMAC generation/mapping recovery, storage and public aggregate suppression remain unimplemented.

Every model field is mandatory and nested extras are forbidden. Cross-field rules require `model_validate_json`; generated JSON Schema alone describes only part of validation. Do not log rejected inputs or `ValidationError.errors()` payloads. Human provenance remains unprovided in the experiment config; self-attested actor references never authenticate a human or establish corrected gold. `ClassifierProposal` is an app-owned signature, not an implemented extractor or competing shared driver.

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
