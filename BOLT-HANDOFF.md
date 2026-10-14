# Bolt handoff inventory

Current status: local Python deterministic-libraries-only stage. Readiness, product-text checks, domain/schema contracts, supplied-synthetic ingest/privacy, a portable skill dictionary and narrow deterministic extraction libraries exist. CLI workflow integration, live/model execution, evaluation and rendered aggregate reports are not implemented.

Database path: **No hosted database**. The local privacy library uses owner-private SQLite and a separate generated HMAC secret outside the product checkout. No cloud migrations, functions, auth, buckets, provider bindings or resources are implemented or provisioned. A later static aggregate viewer needs actual report outputs and portable-build verification.

The Python core requires a Python runtime and local private state when those workflows exist. Importing this repo does not supply that runtime, model credentials, human labels, live data rights or evaluation results. The current commands and locally checked scope are documented in README.md.

Future GitHub/Bolt import, publication and any supported backend provisioning require actual owner instructions and a completed inventory. No provisioning prompt or hosted-readiness claim is supplied at this deterministic-libraries-only stage.
