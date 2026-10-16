# Private synthetic DEV evaluation

This workflow evaluates deterministic rules against supplied frozen synthetic or
agent-provisional DEV references. It uses the actual canonical frozen reader,
comparison runner and private37-field metrics. It does not read heldout bodies,
acquire data, fit defaults, run bootstrap, contact models or read credentials.
Source authorization and independent-author admission happen outside the CLI;
hashes and origin strings do not establish those permissions.

With Python3.12 and locked dependencies available:

```sh
uv run hst eval --offline --show-bindings
uv run hst eval --offline --dataset synthetic --split dev \
  --manifest /owner/private/dev/manifest.json \
  --manifest-sha256 ACTUAL_MANIFEST_SHA256 \
  --sources /owner/private/dev/sources.jsonl \
  --sources-sha256 ACTUAL_SOURCE_FILE_SHA256 \
  --out /owner/private/dev/new-results
```

To also construct a local privacy-safe prediction sample report, append an
explicit four-month consecutive window:

```sh
  --sample-months 2026-07 2026-08 2026-09 2026-10
```

All supplied source months must be inside that window. Missing months remain
gaps. Conservative min-ten V1 is the default. `--sample-policy v2` is an explicit
alternative using the existing policy: zero cells can release only when the
cohort is at least ten and every positive cell is at least ten. One rare positive
cell suppresses all siblings. Policy changes break trend comparisons.

The checkout equivalent is `uv run python scripts/eval.py` with the same arguments
after `eval`. Without explicit inputs, `eval --offline` refuses without output.
To demonstrate refusal, supply a deliberately different64-character manifest hash:
the command refuses before source/Gold reading. Existing outputs are preserved.
Exit0 means complete field processing; exit3 means partial processing. Neither
means correct extraction. Exit2 means refusal, failure or cancellation. Closed
errors state whether private output effects are possible. Interrupted writes can
leave an unsealed partial directory; they are not silently deleted or overwritten.

Use the actual `shared.evalkit.models.Manifest` wire, not smaller source-author
metadata. An owner prepares a derived DEV assembly preserving original source,
label, family/order and seal bytes. It records its parent-manifest hash, actual
assembly time, partition seed, group membership, ordered IDs/digest, exact DEV Gold
bytes and source-artifact hash. The manifest's parent is the corpus root. Only
the declared DEV Gold file is opened; no implicit enrichment or resealing occurs.

`--show-bindings` emits actual config/domain/taxonomy/rubric hashes. Set available
`comparator_config` and `domain_adapter_ref` to their matching hashes, and add
available `experiment_refs.taxonomy` and `.rubric`. Use the emitted scorer version
and a private publication policy without enabled quality projections. Changed
bindings reject. The rubric is the current annotation guide and needs owner
ratification before a real benchmark. Code changes require a deliberate new DEV
assembly, preserving original data rather than silently reusing stale bindings.

Fingerprints bind the actual on-disk implementation bytes, not only a Git commit.
Checkout newline conversion can make a Windows CRLF copy and an exact Git LF copy
produce different helper and full evaluation configuration hashes at the same
commit. Capture `--show-bindings` from the actual admitted runtime edition before
preparing its manifest. A report-only fingerprint is not a full evaluator config;
report verification does not establish their equivalence. Preserve the original
edition and evidence rather than normalizing files or substituting a newer hash
to make an old manifest run. A changed edition still needs the applicable input
and execution authority; it does not reopen an already consumed run.

Sources are JSONL in exactly the frozen DEV order. Each record has only:

```json
{
  "item_id": "64-character public synthetic hex ID",
  "source_id": 1,
  "month": "2026-06",
  "group_id": "64-character declared family hex ID",
  "split": "dev",
  "text": "Original synthetic plain ASCII source text",
  "input_sha256": "SHA256 of the exact UTF8 source text"
}
```

Replace descriptive hash strings with actual values. Public synthetic IDs are not
private HMACs or privacy guarantees. Source IDs are unique; source/group/ID hashes
must match the reference. Bounds are8MiB/512 source rows and32768 ASCII bytes per
posting. Markup, CR, other control characters, surrounding whitespace, duplicate
JSON keys, nonfinite literals, missing/extra keys and heldout rows reject. Source
text remains transient and is not copied into output.

Gold uses canonical `GoldRecord`, `hiring-signals/1` and all37 explicit field labels.
Labels stay private to the scorer; methods receive only current source text. Only
synthetic/agent_provisional references are accepted, with no human-authority bypass.
See [label semantics](gold-format.md). Hashes and provenance alone do not prove
correct, representative or human labels.

Output must be a new directory outside the checkout with an existing parent.
Linked/reparse paths and credential/export/registry/heldout/scratch paths refuse.
The owner establishes access control; creation modes do not prove Windows ACLs.

- `private-summary.json`: class counts/P/R/F1, coverage, skill positive/set scores,
  salary coverage and explicit missing-confidence calibration state.
- `private-metrics.md`: per-field accuracy/coverage with NA values.
- `run.json`: actual execution/input/config/order/provenance hashes and method scope.
- `artifact-manifest.json`: the three files' hashes/byte counts, written last.

With a sample window, `sample-report/` contains canonical closed aggregates,
Markdown, HTML, SVG and its own manifest. `sample-limitations.md` reproduces from
the released report JSON alone. The top artifact manifest also binds those exact
files. `hst report verify --directory /owner/private/dev/new-results/sample-report`
checks the nested report's bounded closure. The limitations file reports only
released denominators; a suppressed small cohort stays withheld there too.
To reproduce that Markdown without opening sibling evaluator files:

```sh
uv run hst report limitations --directory /owner/private/dev/new-results/sample-report
```

The command prints to stdout and writes no files. It verifies the exact nested
report closure before producing text, and accepts only the rules/sample scope.
It does not run extraction, scoring, models or data acquisition. Keep the report
directory separate from private siblings; local closure is not source authority.
Exact older wording requires the frozen helper/config version that produced it;
the current command reports limitations supported by the released schema alone.
An interrupted nested write may leave either an unsealed sample report or a
complete sample report without the outer artifact manifest. In both cases the
combined evaluator output is incomplete. Retrying the same destination refuses
without altering retained files; inspect the partial directory and choose a new
destination for an authorized retry.

These optional assets describe **sample predictions**, not population trends or
extraction quality. Expected IDs still contribute when predictions are missing;
failures mark processing partial. Only actual current source-bound machine
issuance is admitted. No Gold values, private accuracy statistics, source IDs,
posting text or named geography enter the released projection. Keep private
statistics/source data separate from the report folder. Creating local safe
artifacts does not authorize external publication or establish anonymity.

All expected IDs remain in all37 field denominators. Jev, generation and dev-majority
remain not_run without fabricated predictions or zero scores. Rule confidence is
missing, not calibrated. Human agreement, cost and heldout quality remain unmeasured.
The private metric artifacts do not pass through the aggregate privacy projection.
Only the optional sample-report assets use that closed release boundary. Hash
closure does not authorize publication or certify a finished app.
The separate `run-synthetic` command produces population reports; a DEV Gold sample
is not a population and is not converted to monthly population trends here.

## Explicit DEV-majority reference baseline

The default remains rules only. To also fit and execute the reference baseline,
select the same explicit support policy when obtaining bindings and evaluating:

```sh
uv run hst eval --offline --show-bindings --dev-majority-min-support 2
```

Prepare a newly admitted manifest with those actual bindings, then append
`--dev-majority-min-support 2` to the explicit-input evaluation command. A manifest
bound to the rules-only configuration refuses. Support must be an explicit positive
integer; this is a baseline training policy, not the per-class support required for
threshold calibration or production method selection.

The existing canonical frozen reader fits only DEV references. Only a live fit
issued by that fitter is admitted; copies, changed training bytes or changed fitter
code refuse. Learned constant guesses have their own tagged prediction profile.
They never fabricate extraction candidate references or claim to observe a value
in the current posting. Unsupported fields abstain, unlabelled training cells do
not train, false stays distinct from absence, and certainty stays unmeasured.

The private summary and Markdown include actual rules and baseline outcomes. The
run record binds the fit/model hash, support, DEV population and baseline field
count. This command fits and scores the same synthetic DEV set: **resubstitution**,
not independent or heldout quality. Baseline salary candidate recall/normalization
are not applicable, rather than borrowed from a rules extraction. Jev/generation
stay not run. The optional sample report still describes rules predictions only.
No Human authority, source rights, controller admission or consumed-run access is
created by this opt-in. All actual input/execution grants remain necessary.

## Installed wheel

The installed `hst eval --offline --show-bindings` command resolves the exact
wheel-shipped rubric through the same product-asset resolver as annotation.
It works from an unrelated directory without reading a source checkout. This
applies to both default rules bindings and the explicit majority support option.

Prepare a new manifest from the actual installed runtime bindings, then use the
same explicit-input command above with private inputs and a new private output
directory outside the installed product package. Resource or implementation
changes invalidate existing bindings; package version equality does not permit
reusing an old manifest or consumed evaluation grant.

Installed regression controls run fresh original synthetic syntax through rules,
the private artifact seal, a suppressed sample report, verification and reproduced
limitations. Wrong manifest hashes and malformed source rows refuse before output.
They block network, subprocess and source-checkout reads inside the command.
This verifies that narrow installed path on the tested host, not human/heldout
quality, prior admitted data, live providers or cross-platform application readiness.
