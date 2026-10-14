# Original skill dictionary, v1

This folder is a portable Python 3.12/Pydantic v2 library. Copy it as a package
with the product's MIT license and actual source provenance. It imports no owner
app/contracts, ingest, privacy, provider or evaluation module. Moving a package
is not proof of another app's runtime adoption or measured extraction quality.

`CATALOG` holds thirty separate required skill IDs with original literal aliases.
Aliases are escaped, use Unicode word boundaries, and have explicit case rules.
Short tokens Go, C, JAX, RAG, MCP, AWS/GCP and JS/TS are case sensitive. Go-to-market,
Series C/C-level/C++/C#, JavaScript-versus-Java and word-substring traps have controls.
Plain real-estate agents are not AI agents. Unsupported aliases remain unobserved.

`scan(text)` accepts at most 32,768 UTF-8 bytes and returns exactly one closed
`SkillSignal` per ID: requested, excluded, not_stated, conflicting or uncertain.
Explicit `Skills:`, `Requirements:`, `Tech stack:`/`Stack:` headings, request/experience
cues or `required`/`preferred` suffixes establish a narrow positive grammar.
Direct no/without/not-required exclusions are clause local. Optional/maybe evidence
and unresolved conjunction-negation scope stay uncertain. Positive and negative
evidence for the same skill is conflicting. Absence never means explicit exclusion.
Incidental mentions outside this declared grammar remain not_stated.

Repeated mentions count once per posting. Up to eight byte-coordinate references
are retained, preserving at least one of each observed polarity before clipping.
Signals bind the actual input SHA256. References contain alias index, byte start/end
and polarity, with no source text,
quotation, organization/person name or URL. The catalog phrases are public static
technology aliases, not retained input quotations. Per-source signals/digests are
private derivations, not public per-posting exports. All results require runtime
validation; `schemas.json` describes shape and marks additional runtime rules.

These are small handwritten syntax controls, not frozen Gold, a fixture generator,
human annotations, calibration or empirical precision/recall. Later independently
authored data and evaluation are still required. No fuzzy/semantic inference,
skill synonym completeness or general-language negation accuracy is promised.
