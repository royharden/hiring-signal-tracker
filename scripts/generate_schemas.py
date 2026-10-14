"""Generate app-owned JSON Schema; accepts no input data or provider credentials."""

import importlib.util
import json
from pathlib import Path

bootstrap_path = Path(__file__).resolve().with_name("_bootstrap.py")
spec = importlib.util.spec_from_file_location("schema_bootstrap", bootstrap_path)
assert spec is not None and spec.loader is not None
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)
contracts = bootstrap.load("contracts")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    destination = root / "config" / "schemas"
    destination.mkdir(parents=True, exist_ok=True)
    for name, schema in contracts.schema_documents().items():
        (destination / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
