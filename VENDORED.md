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

Unchanged copy of receipt-field-review shared/rulings at commit 455d73c6efe283fdf3919267532de7ad5d39924b, tree 100dc262ed0bd53d52e4a508cfc22aabecbb5aaa. MIT notice: LICENSES/receipt-field-review-MIT.txt. Only this closure is imported; no Docio/evalkit/runtime app is included. The S10 adapter uses real private append/replay/fsync/CAS; source discovery and human Gold validation remain app/owner responsibilities. Bounded original conformance oracles were derived from the listed public source examples; no owner Gold/corpus was used.

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
