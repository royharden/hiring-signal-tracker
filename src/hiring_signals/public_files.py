"""Small staged-text guard, separate from future aggregate privacy enforcement."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_BYTES = 4 * 1024 * 1024
PRIVATE_PARTS = frozenset(
    {".git", ".creds", ".agent-work", ".agent-registry", ".chatexports", ".thinking", "data"}
)
PRIVATE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".pem"})
KEY_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{24,}"),
    re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
)


@dataclass(frozen=True)
class Violation:
    code: str
    relative_path: str


def path_violation(name: str) -> Violation | None:
    """Apply private-path policy before any file or Git blob is opened."""
    relative = Path(name)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        return Violation("invalid_relative_path", "<invalid>")
    private_name = relative.name.casefold().startswith(".env") and relative.name != ".env.example"
    if (
        any(part.casefold() in PRIVATE_PARTS for part in relative.parts)
        or private_name
        or relative.suffix.lower() in PRIVATE_SUFFIXES
    ):
        return Violation("private_path", name)
    return None


def check_blob(name: str, content: bytes) -> list[Violation]:
    """Check immutable candidate bytes, reporting codes rather than matched values."""
    issue = path_violation(name)
    if issue:
        return [issue]
    if len(content) > MAX_TEXT_BYTES:
        return [Violation("text_bound_exceeded", name)]
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        return [Violation("unscannable_or_escaped_file", name)]
    if any(pattern.search(text) for pattern in KEY_PATTERNS):
        return [Violation("sensitive_content", name)]
    return []


def check_files(root: Path, relative_paths: Iterable[str]) -> list[Violation]:
    """Refuse private/escaped inputs before opening; never report matched content."""
    resolved_root = root.resolve()
    failures: list[Violation] = []
    for name in sorted(set(relative_paths)):
        relative = Path(name)
        issue = path_violation(name)
        if issue:
            failures.append(issue)
            continue
        path = resolved_root / relative
        try:
            path.resolve().relative_to(resolved_root)
            if any(parent.is_symlink() for parent in (path, *path.parents)):
                raise ValueError("symlink")
            if not path.is_file():
                failures.append(Violation("missing_product_file", name))
                continue
            if path.stat().st_size > MAX_TEXT_BYTES:
                failures.append(Violation("text_bound_exceeded", name))
                continue
            content = path.read_bytes()
        except (OSError, UnicodeError, ValueError):
            failures.append(Violation("unscannable_or_escaped_file", name))
            continue
        failures.extend(check_blob(name, content))
    return failures
