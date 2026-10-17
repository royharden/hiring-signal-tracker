# Original synthetic CLI workflow

With the source checkout installed by `uv sync --frozen`, process an explicitly
selected original-synthetic manifest:

```sh
uv run hst run-synthetic --input original-source.json --private-dir /owner/private/hst --out /owner/reports/new-report --lease-seconds 120 --policy v2
uv run hst report verify --directory /owner/reports/new-report
uv run hst report export --input /owner/reports/new-report/aggregates.json --out /owner/reports/another-new-report
```

Paths above are caller-selected examples. On Windows, use quoted absolute paths
for your directories. The private directory must be outside the product checkout,
separate from the public output, with owner-restricted access. It contains a
generated HMAC identity secret and closed SQLite source mappings/derived records.
This secret is unrelated to provider credentials. Preserve it with a consistent
private backup to preserve identities. The command does not print it.

The input is a UTF-8 `.json` file, at most 48 MiB overall, with exactly these keys:

| Object | Required keys and meaning |
|---|---|
| Manifest | `schema_version: 1`, `origin: "original_synthetic"`, `months`: four entries |
| Month | `month` YYYY-MM, positive `root_id`, exact Algolia item `origin`, `response`, `reviews` |
| Response | Local Algolia-shaped story with the exact Who is hiring month title and comment children |
| Review | `source_id`, boolean `identities_reviewed`, `identity_terms` array, `organization` string/null, `link_kinds` array |

Months must be consecutive and ordered, with distinct root/post IDs. Review
entries belong to accepted comments in that month. Every organization token must
also appear in its reviewed identity-term inventory. Link kinds are portfolio,
github, application or other, one per link detected by the limited redactor. The
review flag is a caller declaration, not proof of universal anonymization or data
rights. Missing/unreviewed/unsupported privacy inputs are quarantined and remain
in every expected monthly denominator as blocked outcomes; they are not dropped.

Each supplied response retains the transport library's 10 MiB, 600 top-level,
10,000-node, depth-eight and 20,000-character-per-post bounds. Simulated request
timing is local fixture protocol, never measured HTTP timing or API compatibility.
There is no fetch, provider dispatch or implicit sample corpus. The original input
file stays in place; the workflow does not copy raw text, author fields, identities
or links to state or reports. It keeps only validated derived records, opaque IDs,
group HMACs, source/config fingerprints and source mappings in private state.

The present state store has one current record per item. This rules-only command
refuses a directory containing another method's records before overwriting them.
Changed raw/input sources require a deliberate successor instead of replacing an
existing source mapping. Multi-method durable run history is still unfinished.
Normal reruns reuse stable private IDs and require a new public output directory.

V1 suppression is the default. `--policy v2` explicitly selects the approved
zero-cell policy; positive cells below ten still hide every sibling. The CLI
prints no per-posting rows or small private cohort counts. Public JSON, Markdown,
HTML and SVG use the same validated released projection. Processing errors/blocks
make the method partial and break trends; true supported zeros remain zero.

Exit 0 means the requested bounded operation completed, with quality still not
measured. Exit 3 means partial acquisition/processing or no eligible input; no
complete trend or successful empty benchmark is asserted. Exit 2 is a safe error.
A failure after state initialization can leave committed private partial effects;
the error explicitly reports that possibility. Existing output directories are
refused. A report interrupted before its manifest is unsealed and verification
fails; no automatic repair or deletion occurs. Verification requires the exact
five-file flat bundle and hashes/reproduced renderings, not recipient delivery or
source authenticity. Keep private state separate from the public artifact folder.

This is an original-synthetic rules workflow. The required independently authored
60-post/four-month fixtures/Gold, semantic CLI, evaluation, real data rights,
300 human-corrected labels, timing pilot and blind repeats remain separate gates.
`eval --dataset synthetic --offline` without explicit frozen inputs still returns
an explicit unavailable result. The separate tiny demo below needs no input data.

## Input-free offline demo

```sh
uv run hst demo --offline
uv run python scripts/demo.py --offline --out "/owner/reports/new-demo"
```

The module and script run the same bounded operation. With no `--out`, a unique
`hst-demo-...` directory under the OS temporary directory holds the report. The
JSON response gives its full `report_directory` and `report_entry` (`report.html`).
Temporary directories can be removed by the OS; choose a new durable `--out`
directory to keep the report. Its parent must already exist. Output inside the
product, credential/export/registry/heldout/scratch paths, linked/reparse ancestors
and existing destinations refuse before processing. No live demo mode is supplied;
`--offline` is required.

Four original authored records, one per consecutive month, exercise the existing
transport/privacy/rules/private-state/report join. Their exact fixture hash and
demo/rules implementation hashes are returned with the report manifest hash.
The synthetic origin URLs describe local transport envelopes; they are never
fetched and do not identify actual source postings. These records contain no
reference labels and are not the independent required fixture corpus or Gold.
They establish no measured extraction accuracy, Human agreement or model access.

Own synthetic input and private SQLite/HMAC state exist only in a temporary
processing directory, closed and removed before success. The retained output is
exactly the canonical five-file report: JSON, Markdown, HTML, SVG and manifest.
No raw text, author/organization tokens, source IDs, private keys or per-item
predictions belong in that output. The optional destination is the report itself,
so `hst report verify --directory "REPORT_DIRECTORY"` verifies it directly.

Conservative min-ten suppression remains active. All four tiny monthly cohorts
and complementary cells are withheld consistently in the table and chart. The
SVG is real but contains no observed points or trend segments; suppressed states
are labelled. Filling the graph with synthetic percentages would defeat this
privacy demonstration. This command does not change the rules-only evaluation
default or mark the complete app ready.

Exit0 means this narrow offline demo completed and its report verified. Exit2
means refusal, failure or cancellation, with a closed code and `effects_possible`
flag. A later failure can retain a partial/unsealed report; it is never silently
deleted or overwritten. Inspect it and use a fresh destination for a retry.
Successful cleanup of the temporary state is part of completion. Creation modes
and link checks do not certify hostile filesystem isolation or Windows ACLs.
Small integration controls do not substitute for that corpus or measure quality.
