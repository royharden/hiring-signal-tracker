"""Development-only reference baseline fitting through the canonical frozen reader.

This does not generate a Prediction, extraction candidate, quality score or public
report. Its private fitted choices are guesses learned from development labels.
"""

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hiring_signals.contracts import FIELD_IDS
from hiring_signals.shared.evalkit.corpus import load_corpus
from hiring_signals.shared.evalkit.identity import canonical_bytes
from hiring_signals.shared.evalkit.models import GoldRecord, Manifest

from .labels import project_reference

TIE_POLICY = "canonical-json-lexicographic-v1"
_FORBIDDEN = {".creds", ".chatexports", ".agent-registry", ".thinking", ".agent-work", ".git"}


class MajorityFitError(ValueError):
    """Closed failure code without private paths or labels."""


@dataclass(frozen=True)
class MajorityChoice:
    field_id: str
    label_json: bytes | None
    eligible_N: int
    chosen_N: int | None

    @property
    def status(self) -> str:
        return "trained" if self.label_json is not None else "unsupported"

    def value(self) -> object:
        # Each caller gets a detached value, not a mutable reference into the fit.
        return json.loads(self.label_json) if self.label_json is not None else None


@dataclass(frozen=True)
class MajorityFit:
    manifest_sha256: str
    dev_items_sha256: str
    dev_order_sha256: str
    implementation_sha256: str
    model_sha256: str
    min_support: int
    tie_policy: str
    dev_N: int
    label_version: str | None
    label_sources: tuple[str, ...]
    choices: tuple[MajorityChoice, ...]


class _ReferenceValidation:
    """Only the public validate_gold capability used by canonical load_corpus.

    This is not an experiment runner/domain scorer and cannot dispatch a method.
    """

    def __init__(self, authority):
        self.authority = authority
        self.rows = {}

    def validate_gold(self, record):
        self.rows[record.item_id] = project_reference(record, human_authority=self.authority)


def fit_dev_majority(
    root: Path,
    manifest: Manifest,
    *,
    min_support: int,
    human_authority: Callable[[GoldRecord], bool] | None = None,
) -> MajorityFit:
    """Load only frozen dev bytes; never open a heldout body or select method defaults.

    min_support is an explicit baseline fit policy, not the separate per-class
    calibration/default-selection requirement. Freeze/rights/history authorities
    remain external; matching hashes and synthetic controls do not establish them.
    """
    try:
        if type(min_support) is not int or min_support < 1 or type(manifest) is not Manifest:
            raise ValueError()
        manifest = Manifest.model_validate_json(manifest.model_dump_json(warnings="error"))
        root = Path(root).absolute()
        if any(part.casefold() in _FORBIDDEN for part in root.parts):
            raise ValueError()
        dev = [entry for entry in manifest.splits if entry.split == "dev"]
        if len(dev) != 1 or Path(dev[0].items_file).suffix.lower() != ".jsonl":
            raise ValueError()
        if any(part.casefold() in _FORBIDDEN for part in Path(dev[0].items_file).parts):
            raise ValueError()
        validator = _ReferenceValidation(human_authority)
        records = load_corpus(root, manifest, "dev", validator)
        versions = {record.label_version for record in records}
        if len(versions) > 1:
            raise MajorityFitError("majority_label_version_mismatch")
        fields = {field: Counter() for field in FIELD_IDS}
        for record in records:
            for row in validator.rows[record.item_id]:
                if row.eligible:
                    fields[row.field_id][canonical_bytes(row.value)] += 1
        choices = []
        for field, counts in fields.items():
            eligible = sum(counts.values())
            chosen = max(counts.values(), default=0)
            value = (
                min(value for value, count in counts.items() if count == chosen)
                if eligible >= min_support
                else None
            )
            choices.append(
                MajorityChoice(field, value, eligible, chosen if value is not None else None)
            )
        manifest_sha = hashlib.sha256(canonical_bytes(manifest.model_dump(mode="json"))).hexdigest()
        implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        version = next(iter(versions), None)
        origins = tuple(sorted({record.label_source for record in records}))
        payload = {
            "version": "dev-majority-fit/1",
            "manifest_sha256": manifest_sha,
            "dev_items_sha256": dev[0].items_sha256,
            "dev_order_sha256": dev[0].ordered_ids_sha256,
            "implementation_sha256": implementation,
            "min_support": min_support,
            "tie_policy": TIE_POLICY,
            "dev_N": len(records),
            "label_version": version,
            "label_sources": origins,
            "choices": [
                {
                    "field": row.field_id,
                    "value": row.value(),
                    "eligible_N": row.eligible_N,
                    "chosen_N": row.chosen_N,
                }
                for row in choices
            ],
        }
        return MajorityFit(
            manifest_sha,
            dev[0].items_sha256,
            dev[0].ordered_ids_sha256,
            implementation,
            hashlib.sha256(canonical_bytes(payload)).hexdigest(),
            min_support,
            TIE_POLICY,
            len(records),
            version,
            origins,
            tuple(choices),
        )
    except MajorityFitError:
        raise
    except Exception:
        raise MajorityFitError("majority_invalid_or_unavailable_dev") from None
