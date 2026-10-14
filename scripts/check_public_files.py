"""Check the current Git candidate without printing sensitive content."""

import json
import subprocess
import sys
from pathlib import Path

from _bootstrap import load


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        capture_output=True,
        check=False,
    )
    if result.returncode:
        print(json.dumps({"code": "git_candidate_unavailable"}), file=sys.stderr)
        return 2
    entries = [item for item in result.stdout.split(b"\0") if item]
    if not entries:
        print(json.dumps({"code": "empty_candidate"}), file=sys.stderr)
        return 2
    guard = load("public_files")
    failures = []
    for item in entries:
        try:
            header, name = item.decode("utf-8").split("\t", 1)
            mode, object_id, stage = header.split()
        except (UnicodeError, ValueError):
            print(json.dumps({"code": "invalid_candidate_metadata"}), file=sys.stderr)
            return 2
        issue = guard.path_violation(name)
        if issue:
            failures.append(issue)
            continue
        if mode not in {"100644", "100755"} or stage != "0":
            failures.append(guard.Violation("unsupported_candidate_entry", name))
            continue
        blob = subprocess.run(
            ["git", "-C", str(root), "cat-file", "blob", object_id],
            capture_output=True,
            check=False,
        )
        if blob.returncode:
            failures.append(guard.Violation("candidate_blob_unavailable", name))
            continue
        failures.extend(guard.check_blob(name, blob.stdout))
    final_index = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "-z"],
        capture_output=True,
        check=False,
    )
    if final_index.returncode or final_index.stdout != result.stdout:
        print(json.dumps({"code": "candidate_changed_during_check"}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {"checked_files": len(entries), "violations": len(failures), "source": "git_index"}
        )
    )
    for failure in failures:
        print(json.dumps({"code": failure.code, "path": failure.relative_path}), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
