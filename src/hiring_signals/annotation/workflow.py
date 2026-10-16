"""Explicit synthetic DEV keyboard-to-canonical-journal join, without Human authority.

The caller supplies an existing trusted owner-private directory. A matching marker
binds that directory to an opaque owner/actor; it does not authenticate a person or
provide hostile multi-user filesystem isolation. No source acquisition or Gold export.
"""

import hashlib
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from hiring_signals import contracts as c
from hiring_signals.adapters import rulings
from hiring_signals.resources import PACKAGE_ROOT, PRODUCT_ROOT, RUBRIC_PATH
from hiring_signals.shared.callledger.models import decode_wire_json
from hiring_signals.shared.evalkit.corpus import contained_corpus_path
from hiring_signals.shared.rulings.identity import canonical_bytes

from . import models, session

MAX_MANIFEST = 16 * 1024
MAX_JOURNAL = 1024 * 1024
DENIED = {
    ".creds",
    ".chatexports",
    ".agent-registry",
    ".thinking",
    ".thinkinglane",
    ".agent-work",
    ".git",
    "heldout",
    "private-scratch",
}


class AnnotationError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        private_effects_possible: bool = False,
        durable_acknowledgments: int = 0,
    ):
        super().__init__(code)
        self.code = code
        self.private_effects_possible = private_effects_possible
        self.durable_acknowledgments = durable_acknowledgments


class Bindings(c.ClosedModel):
    kind: Literal["synthetic-dev-annotation-bindings/1"]
    taxonomy_sha256: c.Digest
    rubric_sha256: c.Digest
    implementation_sha256: c.Digest


class Manifest(c.ClosedModel):
    kind: Literal["synthetic-dev-annotation/1"]
    origin: Literal["original_synthetic"]
    split: Literal["dev"]
    owner_ref: c.Digest
    actor: models.Actor
    bindings: Bindings
    source_file: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}\.txt$")]
    source: models.SourcePin


class Owner(c.ClosedModel):
    kind: Literal["synthetic-dev-annotation-owner/1"]
    owner_ref: c.Digest
    actor_ref: c.Digest


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bindings() -> dict:
    """Actual working bytes, not a claim of Git LF/CRLF runtime equivalence."""
    owned = [
        "cli.py",
        "contracts.py",
        "resources.py",
        "annotation/models.py",
        "annotation/session.py",
        "annotation/workflow.py",
        "adapters/rulings.py",
        "shared/callledger/models.py",
        "shared/evalkit/corpus.py",
        "shared/evalkit/models.py",
        "shared/evalkit/identity.py",
    ]
    shared = sorted((PACKAGE_ROOT / "shared/rulings").glob("*.py"))
    # Stable logical names, exact actual bytes: installation location is not an input.
    hashes = {
        "src/hiring_signals/" + name: _sha((PACKAGE_ROOT / name).read_bytes()) for name in owned
    }
    hashes.update(
        {
            "src/hiring_signals/" + p.relative_to(PACKAGE_ROOT).as_posix(): _sha(p.read_bytes())
            for p in shared
        }
    )
    return Bindings(
        kind="synthetic-dev-annotation-bindings/1",
        taxonomy_sha256=_sha(canonical_bytes({"fields": c.FIELD_IDS, "skills": c.SKILL_IDS})),
        rubric_sha256=_sha(RUBRIC_PATH.read_bytes()),
        implementation_sha256=_sha(canonical_bytes(hashes)),
    ).model_dump()


def source_pin(data: bytes, owner_ref: str) -> models.SourcePin:
    """Identity-prepared UTF8 synthetic input; no inferred original/source mapping."""
    TypeAdapter(c.Digest).validate_python(owner_ref, strict=True)
    if not 0 < len(data) <= c.MAX_INPUT_BYTES:
        raise AnnotationError("annotation_source_refused")
    data.decode("utf-8", errors="strict")
    digest = _sha(data)
    current = bindings()
    return models.SourcePin(
        item_id=_sha(canonical_bytes({"owner_ref": owner_ref, "source_sha256": digest})),
        raw_source_sha256=digest,
        input_sha256=digest,
        evidence_revision_sha256=_sha(
            canonical_bytes(
                {
                    "kind": "whole-source-review/1",
                    "input_sha256": digest,
                    "byte_length": len(data),
                }
            )
        ),
        taxonomy_sha256=current["taxonomy_sha256"],
        rubric_sha256=current["rubric_sha256"],
    )


def _path(path: Path) -> Path:
    path = Path(path).absolute()
    if any(part.casefold() in DENIED for part in path.parts):
        raise ValueError("protected_path")
    checked = contained_corpus_path(path.parent, path.name)
    if checked.stat().st_nlink != 1:
        raise ValueError("linked_file")
    return checked


def _read(path: Path, maximum: int) -> bytes:
    path = _path(path)
    if not 0 < path.stat().st_size <= maximum:
        raise ValueError("input_size")
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    if not 0 < len(data) <= maximum:
        raise ValueError("input_size")
    return data


def _owner(directory: Path, manifest: Manifest) -> bytes:
    directory = Path(directory).absolute()
    product = PRODUCT_ROOT.resolve()
    if any(part.casefold() in DENIED for part in directory.parts):
        raise ValueError("protected_target")
    for part in (*directory.parents, directory):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("untrusted_target")
        if hasattr(os, "getuid") and info.st_uid not in {0, os.getuid()}:
            raise ValueError("unowned_target")
    resolved = directory.resolve(strict=True)
    if resolved.is_relative_to(product) or product.is_relative_to(resolved):
        raise ValueError("target_inside_product")
    raw = _read(directory / "owner.json", 1024)
    owner = Owner.model_validate_json(json.dumps(decode_wire_json(raw.decode("utf-8"))))
    if (owner.owner_ref, owner.actor_ref) != (manifest.owner_ref, manifest.actor.actor_ref):
        raise ValueError("owner_mismatch")
    return raw


def execute(
    manifest_path: Path,
    *,
    manifest_sha256: str,
    journal_directory: Path,
    reader: Callable[[str], str],
    writer: Callable[[str], None],
) -> dict:
    """No label append before all37 explicit choices. Partial writes are never rolled back."""
    effects = False
    active = None
    acknowledgments = 0
    try:
        TypeAdapter(c.Digest).validate_python(manifest_sha256, strict=True)
        raw = _read(manifest_path, MAX_MANIFEST)
        if _sha(raw) != manifest_sha256:
            raise ValueError("manifest_hash")
        manifest = Manifest.model_validate_json(json.dumps(decode_wire_json(raw.decode("utf-8"))))
        if (
            manifest.actor.origin != "agent_provisional"
            or manifest.actor.attestation_ref is not None
        ):
            raise ValueError("actor_not_provisional")
        if manifest.bindings.model_dump() != bindings():
            raise ValueError("changed_bindings")
        source_path = Path(manifest_path).absolute().parent / manifest.source_file
        data = _read(source_path, c.MAX_INPUT_BYTES)
        if source_pin(data, manifest.owner_ref) != manifest.source:
            raise ValueError("source_pin")
        owner_bytes = _owner(journal_directory, manifest)
        source = c.TransientInput(
            input_sha256=manifest.source.input_sha256, text=data.decode("utf-8")
        )
        sources = rulings.SourceAuthority()
        sources.install(manifest.source, source)
        journal = rulings.AnnotationJournal(
            journal_directory,
            product_root=PRODUCT_ROOT,
            sources=sources,
        )
        # Consumer-specific bounds; canonical producer bytes stay unchanged.
        journal.store.max_journal_bytes = MAX_JOURNAL
        journal.store.max_events = 256

        def current():
            if (
                _sha(_read(manifest_path, MAX_MANIFEST)) != manifest_sha256
                or manifest.bindings.model_dump() != bindings()
                or _owner(journal_directory, manifest) != owner_bytes
                or source_pin(_read(source_path, c.MAX_INPUT_BYTES), manifest.owner_ref)
                != manifest.source
            ):
                sources.remove(manifest.source.item_id)
                raise ValueError("annotation_context_changed")
            return manifest.source

        def head(field):
            nonlocal effects
            current()
            effects = True  # canonical replay can create its lock file
            return journal.head(manifest.source.item_id, field)

        def submit(command):
            nonlocal effects, acknowledgments
            current()
            effects = True
            receipt = journal.submit(command)
            acknowledgments += int(receipt.durable)
            return receipt

        active = session.AnnotationSession(
            source=source,
            pin=manifest.source,
            actor=manifest.actor,
            split="dev",
            current_source=current,
            head=head,
            submit=submit,
        )
        result = session.run_keyboard(active, reader, writer)
        if result.status in {"unknown", "partial", "dependency_unavailable"}:
            # One explicit retry of the unchanged cached intents in this process.
            # A fresh invocation cannot reconstruct a lost ambiguous intent.
            try:
                retry = reader("append_incomplete: retry/q: ")
            except (EOFError, KeyboardInterrupt):
                retry = "q"
            if retry == "retry":
                result = active.submit()
        return {
            "scope": "original_synthetic_dev_annotation",
            **result.model_dump(),
            "private_effects_possible": effects,
            "durable_acknowledgments_this_process": acknowledgments,
            "human_authenticated": False,
            "gold_exported": False,
        }
    except (Exception, KeyboardInterrupt):
        # No underlying exception text, path, source, actor string or rejected choice escapes.
        raise AnnotationError(
            "annotation_interrupted_or_unavailable" if effects else "annotation_input_refused",
            private_effects_possible=effects,
            durable_acknowledgments=acknowledgments,
        ) from None
    finally:
        if active is not None:
            active.cancel()
