# Vendored components

`src/hiring_signals/shared/screen/` is an unchanged six-module copy of the
`issue_triage.shared.screen` closure from royharden/github-issue-triage commit
`419eaf97f605637a9aece2f43c25b04ccb3dabdf`, tree
`c31ea3f6b97b3385cacb9c9f679fd2f60183d1a7`.
MIT notice: `LICENSES/issue-triage-MIT.txt`.
The source contract is preserved at `docs/vendor/screen-contract.md`.
The moved owner test changes only import namespace and source-root location.
Original and adapted hashes/diff are retained in the private delivery receipts.

Rules/preparation are offline stdlib. Typed controls use injected spies; they do
not establish actual S3 replay, provider, ledger or model integration. S10 selects
the adopted rules-only profile with null hazard probabilities. This copy supplies
no live adapters, capture, data rights, human approval or model-quality evidence.

Exact committed source blobs (copied without newline normalization):

| File | Git blob | SHA256 |
|---|---|---|
| __init__.py | 0b1c299659558c561bba53118a64031020aae62e | 847da0a534d478e8be45e2de1eef47613bc3f1058ed85e6b5c5f9e99b222e42b |
| models.py | 891d6491df803b945aecd30cfe887d546ee5306c | 1d33ba786df2cdbd81bd944ad69c11108d220fa268eca4960b4c51dcf1bab252 |
| prepare.py | 0c09c41c7a235926054a953ab3062ccbf8c71b66 | 955e21a840cf00e56b7d431e3d0cf5aa2a5cd66de3e61433a054f31249bdb9dc |
| questions.py | 6259493d681c5fdfd916f7b244b2d284318c6dad | 663ad1437f6abc709caa5b0115051f6eee41debfd41a74e213895651fd47aec8 |
| rules.py | e8b158e66dbb4d1cc128a82e0dcf61b44f8747dd | c0b8920063f0eb3157d44cc76995a459e40267c78d9a5feab3c706ae85357a9b |
| typed.py | 45b83cf81f563f8963f4a3319b8fc0cbe6752d1e | 54022116c9c8bdade586f60cca058f90709a43e24fddef109bbcea2bac7d92bc |

## Rulings

Unchanged copy of receipt-field-review shared/rulings at commit 455d73c6efe283fdf3919267532de7ad5d39924b, tree 100dc262ed0bd53d52e4a508cfc22aabecbb5aaa. MIT notice: LICENSES/receipt-field-review-MIT.txt. This rulings closure is independent of Docio and owner app runtime. The separately pinned evalkit closure is listed below. The S10 adapter uses real private append/replay/fsync/CAS; source discovery and human Gold validation remain app/owner responsibilities. Bounded original conformance oracles were derived from the listed public source examples; no owner Gold/corpus was used.

| File | Git blob | SHA256 |
|---|---|---|
| __init__.py | 15bccaada7b32d1933ac59d9113a5c215de1b0d6 | cc32949ed13b7ea5d77577079441d19e3cfd9b8bfe074db87dff056de3d88a6d |
| models.py | c887635f97589fe5ed8ca761b1e69343d490e43d | 4ab1b6edf1e5009d7ffe9559dae480471df7843b8216b7deb8ab961ce47a3b4c |
| identity.py | 97205db3893fae3a52110c678c326e0dd1c73a49 | da5df25714f8bbc4b8fe7a1f2ee4d780f1259d7c593164c4bd658234262673c0 |
| interfaces.py | 176e3c01ca5984ef185e4bd8096947df156de578 | 785cd755d8f51b8bd8432d5f8b6712a2fa95f4187f610928ddcbe15e5e0ede6a |
| store.py | cee844ddfb7cd2b48e2ef1288de2e8887f3d5df7 | 8586552e099bf1eecc8bb52c5b2a51bf2ca0880a26186587034b63b910402b57 |
| projection.py | ab208c1a66af67e67352dd9ffb0ebca1c818a3e0 | b7d76d4f5b50f56a3973eb6c49fa77130b398f38461d74040d2866630a5381e7 |
| README.md | 7ec932d25a5376f65a1aa557aab8a089150ec28d | c5502679923c0da5c92f5890c7b1a9e52dc9aee45250cd67c501b365351685f0 |
| schema.json | f2df8d43127224feff49228f1178aa1d412aa8c7 | 7c2397d79846fbb3ca51e95dd50eda5174f9fe2d52b0640cd79bf356242b124e |

## Offline providers and callledger

Unchanged complete shared root/provider/callledger closure from llm-router-eval commit c7a03a8a5aa91a3881782621d8a5f09c6b82520d, tree e0aa5796fa163fcbcb5ade87e6a33ed2e645c2e3. MIT notice: LICENSES/llm-router-eval-MIT.txt. Published schemas, tests, docs and three supplemental helpers/assets live under tests/shared_contracts/s3 at their relative source layout. Test/helper imports use hiring_signals.shared; source runtime, fixtures, schemas and synthetic prices remain unchanged. No SDK/live account/model/pricing/quality authority is established.

All source comparisons use exact committed LF Git blobs. Upstream working CRLF variants are not used or labelled committed content. Consumer original/adapted SHA/diffs are private delivery records. S10 semantic composition and optional typed screening are separate unfinished joins.

| File within shared | Git blob | SHA256 |
|---|---|---|
| __init__.py | d54c1da1c6df701267a3ccc931aca3852992f333 | 60913c6d12caa4ba9139d870ad493d4a68738580c996662d7ad7b8d71622e1b8 |
| callledger/README.md | 4eb6cce7d1bc853da62db8ce048247375caf0916 | bdc63ddb26832750654cdbffc09fca33d46b9e5ef2e0b7b1a34cac4e1cea0c50 |
| callledger/__init__.py | 6bb50990aee74ddaffdfd45933d87eb53d040be8 | 0fe1e2b6e2b49e170e5e483d1406b8c36d1ce8e2b446845aad2bb741b7806571 |
| callledger/ledger.py | 595fc556e62adef5bef529b632445a152e718fbc | 207ccd4effe633f44863080957bafa4ca80752397e7aca4eafd541ff50eb2a1d |
| callledger/models.py | ad215ff2bbe06472295b06b66487f526cde59eb9 | 7274d1eebed5370460d83af6e4187cc74037d0ab600889219423dbcdd81277e7 |
| callledger/pricing.py | f8d63558e6238f3cabaf2c52611ab3e632dd29c9 | daf38f487eeb70b48cc4025c54a19eea581a2d5d00084f534d9f2b9a55056c74 |
| callledger/projection.py | 7d20500102b07471caec6362f3b71099ff92df10 | 5c0194e299b2c58f85e745ac093063dcb89689ea162ba378a37afc48a0f4dc69 |
| providers/__init__.py | 67b42aa73e0e5cfa72f83c0669198f354ca4ed4a | 5294e9e9a55d6f645ba1fae741f467accdf3aae0caf9e9094a46784bff57421f |
| providers/adapters.py | 6baa3035f8bd7a04e54281833ff2fd144ed3f02b | 0f04a7f3231c2a22c36541b9cdaeb53214899d4da111f264eab73278847a3023 |
| providers/captures.py | a632ff56ae51d0a416c0d08bf3a2090aeddfcbe8 | 0c91934a090d5f1481fd1116c4ee74a073e0cc8b6ee9c1c8d19cacdce2ebde00 |
| providers/controller.py | a82937f5c363b5b069b918c490e8f385e5e65c52 | 7e607e319bafe93354d04571f82e7fae35365e21fec8d5ce393843f4d41366ac |
| providers/images.py | 9ff512f336a219cb7b4dedad400b523b4de1447e | d847124ef8dc76461f3257df2586075f7ca9602bebe4a15009c6a48aefa6aa13 |
| providers/models.py | a2c2f478b881e1d172085355f9ee347bba919f9f | 7d00a646f583aec1b77abd8c956f1b0c830726be3c17ce37737ac05841060ea2 |
| providers/schema.py | 0d84ca157fa6bbd1fac3b7cbc0aba75751f552c3 | a0c4a84b14a95d2834a150e8fa16224ccec03e1a84325b359b92868a61613391 |

## Evalkit

Unchanged eleven-file canonical evalkit closure from receipt-field-review commit `249262839c4247ff37cc5a75c6a89a422738c759`, tree `e60e8ba5efef185a6706c5d266ce3a1ccad5c553`. MIT notice: `LICENSES/receipt-field-review-MIT.txt`. Nine public synthetic conformance files are mapped under `tests/shared_contracts/evalkit`; only import namespaces and source/test root mappings change. Original and adapted hashes and diffs remain in private delivery receipts.

The library provides typed corpus admission, injected comparison, generic statistics and paired 2,000 whole-group resampling. It supplies no hiring domain scorer, independent Gold, rights verification, durable heldout history or measured app quality. The authored heldout protocol controls are synthetic tests.

| File within evalkit | Git blob | SHA256 |
|---|---|---|
| README.md | e1c3b2ab26460a5245708feba9d011f6ea35ed60 | 1308c679caa5413229ba41de0e6fc4f9cdfd8d76fcb66c0cb1aa4597d2dade94 |
| __init__.py | c0401907d6b0cb0491051cb4732385a1e78aaf3c | 3017cebcf1f80d410a61712cd8207c1803e09954936ce33238d886760683843e |
| corpus.py | a6aea0bbbed151bc550200183d675d63d1aeed04 | 427ade409f4fb83b59a2d9952c890cb830096af948e1dc9d393a8aef47c23fa0 |
| identity.py | d4ed3a66d9f39ce948cc4d992617282c68a16484 | 5897c07d4b0f5d55dd8fee8cb74a325caaebc03b9e70bbf9c426c431d968f1b2 |
| interfaces.py | b90636c575f743eb5e93e13697effa40e0a858fb | d23bc8be5188a968388272580b259ad4af4b1a4cbf393be52d7933514235ed9d |
| models.py | 43bcb7314dc6085a532765ff68725165f44dbc56 | b18613383987a24569e7a9a133b2c212d858c2cf9ee147720b350c06126596c4 |
| reporting.py | e6c46c9226cd4b80a732d0ec16a04e0a1e5b56f9 | 96d439870fe13d5c2ff5064d34eeb66fd5a96cf86fa5e5983ba243a6279aa283 |
| resampling.py | e22ebf62aebac01a02e3a9be842a8584c68caa20 | 005c21b6d9f113db22132f0a660c3a2713e5aeaffb4dbb3c4c5349d66c194619 |
| runner.py | 3a4871fed7ac5a5fe81b0bf6a5f3fe45fb27967c | b3a9078cf3265d750296907572dfeb66de780c01028b715cfdafb39dbad7bccb |
| schema.json | cf5c8740da190f5a603eb4187b382ebb05f3e2f2 | b44b9f4cea1b90d6524ddf9aa56327667a92340810b19000bb8d47702695ffb7 |
| statistics.py | 529b70140f40af2ae60a115a8903e68827258efe | 9e9ec5e9ba86489c8938a87bd064debbedc143126952959729ab46fd624784dc |

## Offline purpose successor

The provider/callledger runtime closure advances to llm-router-eval commit `2671816d4f4fc46b9a650fc4c05ae4389dada326`, tree `2887e018acff384fc1a872080f399c2aeb44c5e0`. Only `callledger/ledger.py` differs from the original c7 closure above: Git blob `e3760ba9efbb6cf140a03c412d66b7ff888c7f1c`, SHA256 `ca38e0776e8b13d95e6ac31087431d45b8c984a40a33f8f8212d7c7bcf16eecb`. All thirteen remaining runtime files and MIT notice are verified unchanged. Prior pins describe prior execution and remain separate.

Offline reuse permits the declared child purpose to differ from the root operation purpose, while checking the stored child purpose unconditionally even when optional caller limits are omitted. Four named purpose test/helper assets use only namespace mappings. This successor adds no generation repair, SDK or live authority.

## Opt-in generation repair successor

Canonical provider/callledger closure advances to llm-router-eval commit `3e7fcdaeb82fff8f84cef6e575d265ae8b08493b`, tree `e30158aa39213847ec10c32d4113153bbbde22b7`. All fifteen runtime/docs files are copied from exact committed Git bytes. Existing c7 and purpose-successor pins remain historical execution views. MIT notice remains `LICENSES/llm-router-eval-MIT.txt`.

This opt-in path supports fixed regeneration from the original facts/schema on a fresh injected-simulation child: two total attempts including transport retries, at most one content repair, both physical request proofs registered before first dispatch, actual ledger settlement/liability and read-only child counters. Final capture metadata identifies the final physical request. No failed-response-specific editing, automatic interrupted continuation or logical repaired capture/reuse is provided. Opt-in mock/strict replay/capture modes are unsupported; their default behavior remains unchanged. There is no SDK/live/key/resource or model-quality authority from this copy. App-domain generation joins remain separate.

| File within shared | Git blob | SHA256 |
|---|---|---|
| callledger/__init__.py | c3157a894fc46d727cdd73d29a1b285b9eee77c0 | c02724ab9a21cfb0387e5d87183634e33a40e8953bd73f443b7489496e260349 |
| callledger/ledger.py | 09e24f876c2ce5f8b5b485e46c12bcd3f7a98ea8 | 3957431f57e8ecbe3147b37aa19487e68331ccd20e357ee20639e09c0f568e31 |
| callledger/models.py | ad215ff2bbe06472295b06b66487f526cde59eb9 | 7274d1eebed5370460d83af6e4187cc74037d0ab600889219423dbcdd81277e7 |
| callledger/pricing.py | f8d63558e6238f3cabaf2c52611ab3e632dd29c9 | daf38f487eeb70b48cc4025c54a19eea581a2d5d00084f534d9f2b9a55056c74 |
| callledger/projection.py | 7d20500102b07471caec6362f3b71099ff92df10 | 5c0194e299b2c58f85e745ac093063dcb89689ea162ba378a37afc48a0f4dc69 |
| providers/__init__.py | 3048ad0a2ea9630d2eb79b6c989069b1beac3964 | 636a5e5451aeec4e30f446efa25d326a52523efc1f53ff2e550903f175600f14 |
| providers/adapters.py | 6baa3035f8bd7a04e54281833ff2fd144ed3f02b | 0f04a7f3231c2a22c36541b9cdaeb53214899d4da111f264eab73278847a3023 |
| providers/captures.py | a632ff56ae51d0a416c0d08bf3a2090aeddfcbe8 | 0c91934a090d5f1481fd1116c4ee74a073e0cc8b6ee9c1c8d19cacdce2ebde00 |
| providers/controller.py | 454ca12991c23354bbe723e47cc5b4f2eb621448 | bcf8e49b038552d07fa4e20b11999019de492ffb6ac3a3db8720eb9d9f56049b |
| providers/images.py | 9ff512f336a219cb7b4dedad400b523b4de1447e | d847124ef8dc76461f3257df2586075f7ca9602bebe4a15009c6a48aefa6aa13 |
| providers/models.py | a2c2f478b881e1d172085355f9ee347bba919f9f | 7d00a646f583aec1b77abd8c956f1b0c830726be3c17ce37737ac05841060ea2 |
| providers/repair.py | 0fb88a8e1481b9d82125ff7b7c2f42131ab3d23d | 0908fd8a8905b49376520eb63e4cd7cd697dc8bdfd0b895f8632819952f96c7d |
| providers/schema.py | 0d84ca157fa6bbd1fac3b7cbc0aba75751f552c3 | a0c4a84b14a95d2834a150e8fa16224ccec03e1a84325b359b92868a61613391 |
| __init__.py | d54c1da1c6df701267a3ccc931aca3852992f333 | 60913c6d12caa4ba9139d870ad493d4a68738580c996662d7ad7b8d71622e1b8 |
| callledger/README.md | 4eb6cce7d1bc853da62db8ce048247375caf0916 | bdc63ddb26832750654cdbffc09fca33d46b9e5ef2e0b7b1a34cac4e1cea0c50 |

## Trusted evaluation axis status successor

Evalkit advances to receipt-field-review commit `f0484fe5b1db3eca842ad7fd691264b61f94a1f8`, tree `e620f22a87043c64e20d2d68f43aa962131c51a5`. Exact twelve-file closure plus the existing MIT notice and ten public synthetic conformance files; no Docio source is included. Wire/schema/identity/interface files remain unchanged. Earlier249 source and execution pins remain historical records.

The explicit trusted axis-status port binds a defensive canonical Prediction and its raw machine envelope to complete predeclared field/class axes. Default whole-status equality remains. Only a validated whole-ok domain envelope can use the port; whole failed/stale/blocked/unavailable/invalid/not-run branches cannot promote field success. The consumer must validate actual raw/controller outcomes, retain a partial operation and its child statuses/accounting, and report the method partial. Matching digests do not supply source/status authority. App-specific37-axis source/controller validation remains a separate join. There is no independent data/Gold/human/calibration or app-quality acceptance from source conformance.

| File within evalkit | Git blob | SHA256 |
|---|---|---|
| README.md | 691b8feb13c3b87cd23c4612084fa398d1384767 | 9d205106651184ba1d3057bc985da7fa0900424926cf0fbe69b9e8836f38b4f4 |
| __init__.py | c0401907d6b0cb0491051cb4732385a1e78aaf3c | 3017cebcf1f80d410a61712cd8207c1803e09954936ce33238d886760683843e |
| axis_status.py | c83c09000eaa65ec64ce5486d5cf74be86c64c37 | a63f1df40e7c4a939f518cddd41f96c7a7a663be1f91aebc54f0f67cbedd789a |
| corpus.py | a6aea0bbbed151bc550200183d675d63d1aeed04 | 427ade409f4fb83b59a2d9952c890cb830096af948e1dc9d393a8aef47c23fa0 |
| identity.py | d4ed3a66d9f39ce948cc4d992617282c68a16484 | 5897c07d4b0f5d55dd8fee8cb74a325caaebc03b9e70bbf9c426c431d968f1b2 |
| interfaces.py | b90636c575f743eb5e93e13697effa40e0a858fb | d23bc8be5188a968388272580b259ad4af4b1a4cbf393be52d7933514235ed9d |
| models.py | 43bcb7314dc6085a532765ff68725165f44dbc56 | b18613383987a24569e7a9a133b2c212d858c2cf9ee147720b350c06126596c4 |
| reporting.py | e6c46c9226cd4b80a732d0ec16a04e0a1e5b56f9 | 96d439870fe13d5c2ff5064d34eeb66fd5a96cf86fa5e5983ba243a6279aa283 |
| resampling.py | e22ebf62aebac01a02e3a9be842a8584c68caa20 | 005c21b6d9f113db22132f0a660c3a2713e5aeaffb4dbb3c4c5349d66c194619 |
| runner.py | 23543cae945b98a864e85aaef856c0b4ce301074 | 0cc2b8e655db84d90a665a3f97ce1a9416a6bff182a6aa460e53686055c404c9 |
| schema.json | cf5c8740da190f5a603eb4187b382ebb05f3e2f2 | b44b9f4cea1b90d6524ddf9aa56327667a92340810b19000bb8d47702695ffb7 |
| statistics.py | 529b70140f40af2ae60a115a8903e68827258efe | 9e9ec5e9ba86489c8938a87bd064debbedc143126952959729ab46fd624784dc |
