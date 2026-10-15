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
`demo --offline` and `eval --dataset synthetic --offline` still return an explicit
unavailable result until their required inputs and evaluation are implemented.
Small integration controls do not substitute for that corpus or measure quality.
