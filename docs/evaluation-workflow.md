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

All expected IDs remain in all37 field denominators. Jev, generation and dev-majority
remain not_run without fabricated predictions or zero scores. Rule confidence is
missing, not calibrated. Human agreement, cost and heldout quality remain unmeasured.
These artifacts stay private and do not pass through the public aggregate privacy
projection. Hash closure does not authorize publication or certify a finished app.
The separate `run-synthetic` command produces population reports; a DEV Gold sample
is not a population and is not converted to monthly population trends here.
