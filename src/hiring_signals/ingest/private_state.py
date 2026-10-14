"""Owner-local generated HMAC identity and closed derived SQLite state.

All SQL payloads are allowlisted scalars or validated PrivateDerivedRecord JSON.
No source text, identity term, URL or API credential belongs in this store.
"""

import hashlib
import hmac
import math
import os
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from hiring_signals.contracts import CandidateReference, PrivateDerivedRecord

from .transport import month_title


class PrivacyError(ValueError):
    pass


class Lease:
    __slots__ = ("generation", "expires_at", "active", "mappings")

    def __init__(self, generation: int, expires_at: float):
        self.generation, self.expires_at, self.active = generation, expires_at, True
        self.mappings: dict[int, str] = {}

    def __repr__(self):
        return "Lease(<private session omitted>)"

    def invalidate(self):
        self.active = False
        self.mappings.clear()


def _digest(value: str) -> None:
    try:
        CandidateReference(input_sha256=value, start_byte=0, end_byte=1)
    except ValidationError:
        raise PrivacyError("invalid_digest") from None


class PrivateState:
    """One owner state handle, explicit leases and serialized transactional writes.

    Directory must be outside and not contain product_root. Owner must restrict
    its Windows ACLs; POSIX creation modes alone do not establish Windows privacy.
    Back up identity.key plus a consistent closed SQLite backup together.
    """

    def __init__(
        self, directory: Path, *, product_root: Path, clock: Callable[[], float] = time.monotonic
    ):
        self.directory, product = Path(directory).resolve(), Path(product_root).resolve()
        if self.directory.is_relative_to(product) or product.is_relative_to(self.directory):
            raise PrivacyError("state_must_be_outside_product")
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        key_path, db_path = self.directory / "identity.key", self.directory / "derived.sqlite3"
        if key_path.is_symlink() or db_path.is_symlink():
            raise PrivacyError("state_symlink_forbidden")
        if not key_path.exists():
            if db_path.exists():
                raise PrivacyError("identity_key_recovery_required")
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
            descriptor = os.open(key_path, flags, 0o600)
            try:
                pending = secrets.token_bytes(32)
                while pending:
                    written = os.write(descriptor, pending)
                    if written <= 0:
                        raise PrivacyError("identity_key_write_failed")
                    pending = pending[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        self._key = key_path.read_bytes()
        if len(self._key) != 32:
            raise PrivacyError("invalid_identity_key")
        self._clock, self._lock = clock, threading.RLock()
        self._leases: set[Lease] = set()
        self._connection = sqlite3.connect(
            db_path, isolation_level=None, check_same_thread=False, timeout=5
        )
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(
            "CREATE TABLE IF NOT EXISTS epoch (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
            "generation INTEGER NOT NULL); INSERT OR IGNORE INTO epoch VALUES(1,0);"
            "CREATE TABLE IF NOT EXISTS sources (source_id INTEGER PRIMARY KEY, "
            "item_id TEXT NOT NULL UNIQUE, month TEXT NOT NULL, raw_sha256 TEXT NOT NULL, "
            "input_sha256 TEXT NOT NULL, group_digest TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS records (item_id TEXT PRIMARY KEY, payload TEXT NOT NULL);"
        )
        try:
            for row in self._connection.execute("SELECT * FROM sources"):
                source_id, item_id, month, raw_digest, input_digest, group_digest = row
                if type(source_id) is not int or source_id <= 0:
                    raise PrivacyError("invalid_private_mapping")
                month_title(month)
                for digest in (item_id, raw_digest, input_digest, group_digest):
                    _digest(digest)
                if not hmac.compare_digest(self.item_id(source_id), item_id):
                    raise PrivacyError("identity_key_mapping_mismatch")
            for (payload,) in self._connection.execute("SELECT payload FROM records"):
                validated = PrivateDerivedRecord.model_validate_json(payload)
                row = self._connection.execute(
                    "SELECT month,input_sha256 FROM sources WHERE item_id=?", (validated.item_id,)
                ).fetchone()
                if row != (validated.month, validated.input_sha256):
                    raise PrivacyError("record_source_binding_mismatch")
        except (ValueError, TypeError):
            self._connection.close()
            raise PrivacyError("invalid_private_state") from None

    def item_id(self, source_id: int) -> str:
        if type(source_id) is not int or not 0 < source_id <= 2**63 - 1:
            raise PrivacyError("invalid_source_id")
        return hmac.new(self._key, f"hst:item:v1:{source_id}".encode(), hashlib.sha256).hexdigest()

    def _generation(self) -> int:
        return self._connection.execute(
            "SELECT generation FROM epoch WHERE singleton=1"
        ).fetchone()[0]

    def begin(self, *, lease_seconds: float) -> Lease:
        if (
            type(lease_seconds) not in {int, float}
            or not math.isfinite(lease_seconds)
            or lease_seconds <= 0
        ):
            raise PrivacyError("invalid_explicit_lease")
        with self._lock:
            lease = Lease(self._generation(), self._clock() + lease_seconds)
            self._leases.add(lease)
            return lease

    def _active(self, lease: Lease) -> None:
        if lease not in self._leases or not lease.active or self._clock() >= lease.expires_at:
            lease.invalidate()
            self._leases.discard(lease)
            raise PrivacyError("inactive_or_expired_lease")
        if lease.generation != self._generation():
            lease.invalidate()
            self._leases.discard(lease)
            raise PrivacyError("stale_generation")

    def _write(self, lease: Lease, operation):
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._active(lease)
                result = operation()
                # Check expiry and generation again after SQL, before durable commit.
                self._active(lease)
                self._connection.execute("COMMIT")
                return result
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def register_source(
        self,
        *,
        source_id: int,
        month: str,
        raw_sha256: str,
        input_sha256: str,
        organization: str | None,
        lease: Lease,
    ) -> str:
        month_title(month)
        _digest(raw_sha256)
        _digest(input_sha256)
        item_id = self.item_id(source_id)
        if organization is not None and (
            not isinstance(organization, str) or not organization.strip()
        ):
            raise PrivacyError("invalid_transient_organization")
        group_key = " ".join(organization.casefold().split()) if organization else item_id
        group = hmac.new(
            self._key, b"hst:group:v1:" + group_key.encode(), hashlib.sha256
        ).hexdigest()
        row = (source_id, item_id, month, raw_sha256, input_sha256, group)

        def operation():
            existing = self._connection.execute(
                "SELECT * FROM sources WHERE source_id=?", (source_id,)
            ).fetchone()
            if existing is not None and existing != row:
                raise PrivacyError("source_changed_requires_successor")
            self._connection.execute("INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?)", row)
            return item_id

        result = self._write(lease, operation)
        with self._lock:
            self._active(lease)
            lease.mappings[source_id] = item_id
        return result

    def write_record(self, record: PrivateDerivedRecord, *, lease: Lease) -> None:
        try:
            validated = PrivateDerivedRecord.model_validate(record)
            payload = validated.model_dump_json()
        except (ValidationError, TypeError):
            raise PrivacyError("invalid_derived_record") from None

        def operation():
            row = self._connection.execute(
                "SELECT month,input_sha256 FROM sources WHERE item_id=?", (validated.item_id,)
            ).fetchone()
            if row != (validated.month, validated.input_sha256):
                raise PrivacyError("record_source_binding_mismatch")
            self._connection.execute(
                "INSERT INTO records VALUES(?,?) ON CONFLICT(item_id) "
                "DO UPDATE SET payload=excluded.payload",
                (validated.item_id, payload),
            )

        self._write(lease, operation)

    def read_records(self, *, lease: Lease) -> tuple[PrivateDerivedRecord, ...]:
        with self._lock:
            self._active(lease)
            return tuple(
                PrivateDerivedRecord.model_validate_json(row[0])
                for row in self._connection.execute("SELECT payload FROM records ORDER BY item_id")
            )

    def lookup_source(self, item_id: str, *, lease: Lease) -> int | None:
        _digest(item_id)
        with self._lock:
            self._active(lease)
            row = self._connection.execute(
                "SELECT source_id FROM sources WHERE item_id=?", (item_id,)
            ).fetchone()
            return row[0] if row else None

    def cancel(self, lease: Lease) -> None:
        with self._lock:
            lease.invalidate()
            self._leases.discard(lease)
            # Persist cancellation epoch, so another handle's earlier work cannot commit later.
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute(
                    "UPDATE epoch SET generation=generation+1 WHERE singleton=1"
                )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            for lease in self._leases:
                lease.invalidate()
            self._leases.clear()
            self._key = b""
            self._connection.close()
