# Bolt handoff inventory

Current status: local Python contracts-only stage. Readiness, staged product-text checks and app-owned domain/config contracts with generated schemas exist; ingestion, model execution, evaluation and static aggregate reports are not implemented.

Database path: **No hosted database**. No migrations, functions, auth, buckets, provider bindings or cloud resources are implemented or provisioned. A later static aggregate viewer can be prepared independently after real report outputs and its portable build are verified.

The Python core requires a Python runtime and local private state when those workflows exist. Importing this repo does not supply that runtime, model credentials, human labels, live data rights or evaluation results. The current commands and locally checked scope are documented in README.md.

Future GitHub/Bolt import, publication and any supported backend provisioning require actual owner instructions and a completed inventory. No provisioning prompt or hosted-readiness claim is supplied at this contracts-only stage.
