# Annotation guide and current controller boundary

The memory-only annotation/controller library and an actual canonical S2 journal
adapter are implemented. Owner-authorized data and validated human provenance
remain required for real labels and Gold eligibility. Agent/staging examples are
not human annotations or agreement evidence. Ratify this rubric/taxonomy and run
the ten-item timing pilot before a real300-item workload; measured effort remains
unknown. Twenty preselected blind repeats require the same operator and at least
seven days; their actual dates/provenance must come from the owner history.

Read an owner-selected original in place or use the transient memory view.
Keyboard output deliberately never prints source text. Every one of37 fields
needs an explicit choice; no absent labels are implicitly confirmed. `y`/`n`
mean explicit positive/negative, `a` means genuinely unstated, and `?` remains
unlabelled and ineligible. `u` is an explicitly selected not_stated class, not
an unanswered field. Skip/q/EOF/cancel never appends a decision. Do not enter
names, links, credentials or free-text reasons into label choices.

- **AI engineering role:** core duties build/evaluate ML or LLM systems. An AI
  employer's sales role or merely using an assistant is not automatically AI
  engineering. Missing role evidence is unstated; do not infer from branding.
- **Portfolio requested:** applicant GitHub/work samples/something built must be
  requested. Employer/apply links alone do not qualify. Explicit absence and a
  complete application instruction without a request differ from no instructions.
- **Seniority:** use junior/mid/senior/staff_or_lead or a genuine role-attached
  `multiple:junior,senior` combination. Incidental mentors/tool-specific years
  do not establish a role level. Unsupported/ambiguous evidence stays unlabelled
  until the owner rubric resolves it; do not manufacture a confident level.
- **Work mode/employment:** use the exact category IDs. Absence never defaults
  to onsite/full_time. Conflicts need actual resolution, not an automatic class.
- **Thirty skills:** score each independently as requested/excluded/unstated.
  Beware Go/go-to-market, C/Series C/C-level/C++ and Java/JavaScript traps.
- **Salary:** `none` is explicit none. Otherwise enter four exact tokens such
  as `USD 100000 120000 year`; use `unknown` for a missing/unsupported currency
  or period. Preserve decimal order/units; never guess annualization. Unknown
  units remain a stated range, separate from normalization. No names/free text.
- **Location:** presence only; do not retain named geography. Choose a, y or n
  from actual source evidence, not inferred work mode.

The compact human-review parser uses a whole-source byte range for present
labels; this is a review scope, not a claim of localized extraction accuracy.
All stored command values are closed booleans/categories/decimals and safe
IDs/digests/coordinates. No source quotes/identity strings belong in a journal.

Dev suggestions must bind the full current source pin and an actual private raw
machine record; naked classifications, reference labels and human-effective
predictions are refused as prefill. Suggestions are visibly unconfirmed, need explicit `=` per field and record
assistance. Heldout and blind-repeat sessions refuse prefill/assisted labels.
The repeat guard enforces the seven-day/item/operator check but does not prove
human identity, prior evidence or actual human agreement. Actor self-attestation
is attribution, not authentication or a dataset/data-rights grant.

The app emits neutral scalar commands to `adapters/rulings.py`, using the unchanged
published S2 journal/reducer. It validates the current raw/evidence generation and
stable CAS head, recognizes exact retries before obsolete source/head checks and
acknowledges only after actual journal fsync. A first UI confirmation introduces
a label and maps to canonical `correct`; canonical `confirm` preserves the exact
existing typed value. Absence and reopen remain null. Evidence generation binds
input, evidence revision, taxonomy and rubric digests separately from raw source.
This controller
performs early source checks and caches an ambiguous intent unchanged. A conflict
needs owner resolution/new review; do not silently edit a pending intent.

Reopen clears the current draft label rather than searching for an older approval.
A batch can be partial: already acknowledged owner events are not fictitiously
rolled back on cancel/crash. This memory-only controller is not restart recovery
or a durable outbox. Recover actual history/intents through the owner backend.
Missing backends are unavailable; mocks are explicitly test_staging/non-durable.
Even complete owner receipts require separate owner human/Gold validation.

`AnnotationJournal` requires an existing trusted owner-private directory outside
the product checkout. `SourceAuthority` installs a pin only from an actually
matching transient input and stores digests/byte lengths, never source text. Its
process lock covers validation through append/fsync and every install/remove.
The current source must be reinstalled after restart. This registry is not a
multi-process source-discovery/deletion service or a durable outbox. The full
canonical `append()` receipt exposes historical exact retries with no current
generation authority. Controller receipt counts acknowledge recorded writes;
they do not assert that those labels are still effective. Actor strings/ref syntax
remain unverified without actual human evidence. Local journal tests do not prove
power-loss recovery, hostile multi-user filesystem safety or real human agreement.

## Synthetic DEV annotation CLI

This command is limited to caller-admitted original synthetic DEV data with an
`agent_provisional` actor. It rejects Human actors, heldout, repeats and prefill.
It uses identity preparation: the original UTF8 file bytes are also the prepared
bytes (at most32768 bytes); raw/input digests must match. `source_pin` derives the
item identity from owner/source digests, whole-source review revision from actual
byte length/hash, and current taxonomy/rubric. It is a binding, not source rights.

Obtain actual working bindings with `hst annotate --show-bindings`. Prepare a
closed JSON manifest outside the checkout with these exact keys:

```text
kind: synthetic-dev-annotation/1
origin: original_synthetic
split: dev
owner_ref: <opaque lowercase SHA256>
actor: {origin: agent_provisional, actor_ref: <opaque SHA256>, attestation_ref: null}
bindings: <exact show-bindings object>
source_file: <simple sibling leaf ending .txt>
source: <complete SourcePin from source_pin(actual_file_bytes, owner_ref)>
```

`source` contains item_id, raw_source_sha256, input_sha256,
evidence_revision_sha256, taxonomy_sha256 and rubric_sha256. A preparation script
may call `hiring_signals.annotation.workflow.source_pin` and `bindings`; that
operation reads current code/rubric and returns closed digest metadata, without
persisting text or authenticating a person. Hash the final manifest's actual
bytes after writing it; duplicate keys and undeclared fields refuse.

The operator supplies an existing trusted owner-private directory outside the
checkout, with an `owner.json` marker containing exactly kind
`synthetic-dev-annotation-owner/1`, owner_ref and actor_ref matching the manifest.
The command creates no missing directory or owner marker. Links/reparse paths,
hard-linked input/marker files, protected directories and targets inside or above
the checkout refuse. On POSIX, ancestor owners must be the current UID or root;
Windows uses the trusted-directory precondition and canonical local-path checks,
not an invented ACL/authentication proof. Keep private directories owner-controlled.

```sh
uv run hst annotate --manifest /owner/synthetic/manifest.json --manifest-sha256 <exact-byte-sha256> --journal-dir /owner/private/annotation
```

View the admitted original separately. Field prompts and fixed diagnostics go to
stderr; stdout is one closed result JSON. Every field needs an explicit choice.
`?` stays unlabelled and prompts again; `q`, skip, EOF or Ctrl-C before submission
writes no labels. Invalid/rejected choices never appear in output. No prefill or
free-text reasoning is accepted. Input is rechecked during the draft and before
writes; source, manifest, ownership or current binding drift refuses.

Exit0 means37 real durable receipts, never Human/Gold validity. Exit3 denotes
cancel/skip/incomplete/partial/conflict/unknown/dependency-unavailable; inspect
status and acknowledged counts. Exit2 denotes refused/failed operation and
reports whether private effects are possible plus acknowledged receipts when
known. Canonical replay can create a lock file before an append; refusal after
that point does not claim zero filesystem effects. A real acknowledged prefix
is never fictitiously rolled back. Existing torn/corrupt state is preserved,
not automatically repaired.

After an unknown/partial/unavailable append, one explicit `retry` response retries
unchanged cached intents in the same process; `q` or EOF preserves the result.
CAS conflicts need owner resolution. Historical exact retries are receipts of
past writes, not current-generation authority. A fresh invocation reads current
heads and constructs new intents; it cannot recover a lost ambiguous intent.
The journal is bounded to1MiB/256 events for this entry point; full journals refuse
rather than rotate/delete history. Separate owner history/retention decisions
are required for a larger workload. No raw posting, names or source mapping belongs
in a journal. No public aggregate or label/Gold export is produced here.
