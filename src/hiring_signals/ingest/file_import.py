"""Owner-selected original-synthetic posting text to existing closed private state.

No transport envelope, network, labels, public projection or retained posting text.
Path checks assume an owner-controlled filesystem, not hostile filesystem isolation.
"""

import hashlib
import math
import os
import stat
from pathlib import Path

from hiring_signals import contracts as c
from hiring_signals import workflow
from hiring_signals.extract import rules
from hiring_signals.ingest import redaction, transport
from hiring_signals.ingest.private_state import PrivacyError, PrivateState
from hiring_signals.shared.callledger.models import canonical_digest
from hiring_signals.shared.evalkit.corpus import _is_link

PROTECTED_PARTS = workflow.PRIVATE_INPUT_PARTS | {"heldout", "private-scratch"}


class FileImportError(ValueError):
    """Closed error codes only; never a source value or filesystem exception."""

    def __init__(self, code: str, *, private_effects_possible=False):
        super().__init__(code)
        self.code, self.private_effects_possible = code, private_effects_possible


def _unlinked_path(value: Path) -> Path:
    path = Path(value).absolute()
    resolved = path.resolve()
    if any(part.casefold() in PROTECTED_PARTS for part in (*path.parts, *resolved.parts)):
        raise FileImportError("file_path_refused")
    for part in (*path.parents, path):
        if os.path.lexists(part) and _is_link(part):
            raise FileImportError("file_path_refused")
    return path


def _input_path(value: Path, suffix: str) -> Path:
    path = _unlinked_path(value)
    info = path.stat()
    if (
        path.suffix.lower() != suffix
        or not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or not 0 < info.st_size <= c.MAX_INPUT_BYTES
    ):
        raise FileImportError("file_input_refused")
    return path


def _posting_text(path: Path) -> str:
    with path.open("rb") as handle:
        raw = handle.read(c.MAX_INPUT_BYTES + 1)
    if not 0 < len(raw) <= c.MAX_INPUT_BYTES:
        raise FileImportError("file_input_refused")
    text = raw.decode("utf-8")
    if not text.strip() or len(text) > transport.MAX_POST_CHARACTERS:
        raise FileImportError("file_posting_refused")
    return text


def _private_path(value: Path, inputs: tuple[Path, ...]) -> Path:
    path = _unlinked_path(value)
    resolved, product = path.resolve(), workflow.PRODUCT_ROOT.resolve()
    if (
        resolved.is_relative_to(product)
        or product.is_relative_to(resolved)
        or any(source.resolve().is_relative_to(resolved) for source in inputs)
        or (path.exists() and not path.is_dir())
    ):
        raise FileImportError("file_private_directory_refused")
    for name in (
        "identity.key",
        "derived.sqlite3",
        "derived.sqlite3-journal",
        "derived.sqlite3-wal",
        "derived.sqlite3-shm",
    ):
        child = _unlinked_path(path / name)
        if child.exists():
            info = child.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise FileImportError("file_private_directory_refused")
    return path


def execute_file_import(
    file_path: Path,
    *,
    review_path: Path,
    month: str,
    source_id: int,
    synthetic_only: bool,
    private_directory: Path,
    lease_seconds: float,
):
    """Import exactly one reviewed synthetic posting, without a public per-item result."""
    post = prepared = state = review = None
    effects_possible = False
    try:
        if synthetic_only is not True:
            raise FileImportError("explicit_synthetic_only_required")
        if (
            type(lease_seconds) not in {int, float}
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise FileImportError("finite_explicit_lease_required")
        try:
            transport.month_title(month)
            workflow._source_id(source_id)
        except (ValueError, TypeError):
            raise FileImportError("file_source_or_month_refused") from None
        source = _input_path(file_path, ".txt")
        reviewed = _input_path(review_path, ".json")
        private = _private_path(private_directory, (source, reviewed))
        try:
            review = workflow._review(
                workflow.bounded_json_file(reviewed, maximum=c.MAX_INPUT_BYTES)
            )
            # JSON escapes can describe lone surrogates even in a UTF-8 file.
            # Reject them before organization normalization reaches HMAC/state.
            for term in review["identity_terms"]:
                term.encode("utf-8")
            if review["organization"] is not None:
                review["organization"].encode("utf-8")
        except (ValueError, TypeError, RecursionError):
            raise FileImportError("file_review_refused") from None
        if review["source_id"] != source_id:
            raise FileImportError("file_review_source_mismatch")
        post = transport.SyntheticPost(source_id, _posting_text(source))
        # Redaction must see the same LF text the caller hashed. A Windows
        # text write turns \n into \r\n before this reader sees the bytes.
        post.text = post.text.replace("\r\n", "\n").replace("\r", "\n")
        prepared = redaction.prepare_synthetic(
            post,
            identity_terms=tuple(review["identity_terms"]),
            identities_reviewed=review["identities_reviewed"],
            link_kinds=tuple(review["link_kinds"]),
        )
        if prepared.envelope is None:
            raise FileImportError("file_privacy_review_quarantined")
        taxonomy = canonical_digest(
            {
                "version": "taxonomy-v1",
                "ratification": "pending",
                "fields": list(c.FIELD_IDS),
                "skills": list(c.SKILL_IDS),
            }
        )
        config = canonical_digest(
            {
                "workflow": "original-synthetic-file-rules/1",
                "rubric": "pending",
                "models": "not_run",
            }
        )
        implementation = canonical_digest(
            {
                "rules_workflow": workflow._implementation_sha256(),
                "file_import": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
        )
        # All source/review/redaction validation precedes even state initialization.
        effects_possible = True
        state = PrivateState(private, product_root=workflow.PRODUCT_ROOT)
        lease = state.begin(lease_seconds=lease_seconds)
        if any(record.method != "rules" for record in state.read_records(lease=lease)):
            raise FileImportError(
                "other_method_state_requires_separate_run", private_effects_possible=True
            )
        # Column 3 is the sha256 of the exact posting text. A Windows text
        # write turns \n into \r\n before this reader sees the bytes.
        exact_text = post.text.replace("\r\n", "\n").replace("\r", "\n")
        item_id = state.register_source(
            source_id=source_id,
            month=month,
            raw_sha256=hashlib.sha256(exact_text.encode("utf-8")).hexdigest(),
            input_sha256=prepared.envelope.input_sha256,
            organization=review["organization"],
            lease=lease,
        )
        rules.classify_and_store(
            prepared.envelope,
            state=state,
            lease=lease,
            item_id=item_id,
            month=month,
            taxonomy_sha256=taxonomy,
            config_sha256=config,
            implementation_sha256=implementation,
        )
        return {
            "schema_version": 1,
            "status": "synthetic_file_derivation_stored",
            "complete_workflow": False,
            "source_scope": "original_synthetic",
            "quality_status": "not_measured",
            "provider_calls": 0,
        }
    except FileImportError:
        raise
    except PrivacyError as error:
        code = (
            "source_changed_requires_successor"
            if str(error) == "source_changed_requires_successor"
            else "file_private_state_refused"
        )
        raise FileImportError(code, private_effects_possible=effects_possible) from None
    except (Exception, KeyboardInterrupt):
        raise FileImportError(
            "file_import_failed_or_cancelled", private_effects_possible=effects_possible
        ) from None
    finally:
        if post is not None:
            post.text = ""
        if prepared is not None and prepared.envelope is not None:
            prepared.envelope.text = ""
        if type(review) is dict:
            review.clear()
        if state is not None:
            try:
                state.close()
            except Exception:
                raise FileImportError(
                    "file_private_state_close_failed", private_effects_possible=True
                ) from None
