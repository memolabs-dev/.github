#!/usr/bin/env python3
"""Validate worktree provenance and record real tests without running Issue commands."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

import issue_preflight
from issue_lease import Lease, Denied

REPO = "memolabs-dev/.github"
ISSUE = 44
SPEC = "docs/star-pilot-adapter.md"
BASE = "origin/feat/star-pilot-adapter-20261013"
BRANCH = "feat/star-receipt-contract-20261013"
ALLOWED = frozenset(("scripts/star_receipt.py", "tests/test_star_receipt.py",
                     "docs/star-receipt-contract.md"))
TEST = ("python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v")
REMOTES = frozenset(("https://github.com/memolabs-dev/.github.git",
                     "https://github.com/memolabs-dev/.github",
                     "git@github.com:memolabs-dev/.github.git"))
SHA = re.compile(r"^[0-9a-f]{40}$")
WORKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
TOTAL = re.compile(r"Ran ([0-9]+) tests? in ")


class Denial(Exception):
    pass


def checked_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise Denial("Unverifiable Git object SHA")
    return value


def git(wt, *args, runner=subprocess.run):
    p = runner(["git", "-C", str(wt), *args],
               capture_output=True, text=True, check=False, timeout=30)
    if p.returncode:
        raise Denial("Git metadata operation failed")
    return p.stdout.strip()


def inspect(wt, runner=subprocess.run):
    wt = Path(wt).expanduser().resolve()
    if not wt.is_dir() or not (wt / ".git").is_file():
        raise Denial("Isolated Git worktree missing")
    if Path(git(wt, "rev-parse", "--show-toplevel", runner=runner)).resolve() != wt:
        raise Denial("Worktree root mismatch")
    if git(wt, "remote", "get-url", "origin", runner=runner) not in REMOTES:
        raise Denial("Unexpected remote")
    if git(wt, "branch", "--show-current", runner=runner) != BRANCH:
        raise Denial("Unexpected branch")
    if git(wt, "status", "--porcelain", runner=runner):
        raise Denial("Uncommitted changes; cannot attest HEAD")
    base = checked_sha(git(wt, "rev-parse", BASE, runner=runner))
    head = checked_sha(git(wt, "rev-parse", "HEAD", runner=runner))
    if base == head or checked_sha(git(wt, "merge-base", base, head, runner=runner)) != base:
        raise Denial("Branch is not an approved descendant of base")
    blob = checked_sha(git(wt, "rev-parse", base + ":" + SPEC, runner=runner))
    diff = git(wt, "diff", "--name-only", base + "...HEAD", runner=runner)
    paths = diff.splitlines()
    if not paths or len(paths) != len(set(paths)) or set(paths) - ALLOWED:
        raise Denial("Changed file paths outside approved task")
    return {"base_sha": base, "head_sha": head, "spec_path": SPEC,
            "spec_blob_sha": blob, "changed_paths": sorted(paths)}


def fixed_tests(wt, runner=subprocess.run):
    try:
        p = runner(list(TEST), cwd=str(wt), capture_output=True,
                   text=True, check=False, timeout=180)
    except subprocess.TimeoutExpired:
        return {"state": "BLOCKED", "count": None, "command": list(TEST)}
    found = TOTAL.search((p.stderr or "")[-10000:])
    count = int(found.group(1)) if found else None
    state = "PASSED" if p.returncode == 0 and count and count > 0 else "FAILED"
    return {"state": state, "count": count,
            "exit_code": p.returncode, "command": list(TEST)}


def validate(record):
    if not isinstance(record, dict) or record.get("format") != "star-code-receipt/v1":
        raise Denial("Wrong evidence format")
    if record.get("repo") != REPO or record.get("issue") != ISSUE:
        raise Denial("Unknown Issue identity")
    if record.get("url") != "https://github.com/" + REPO + "/issues/44":
        raise Denial("Issue URL mismatch")
    if record.get("branch") != BRANCH or record.get("spec_path") != SPEC:
        raise Denial("Invalid branch/spec contract")
    for name in ("base_sha", "head_sha", "spec_blob_sha", "fence"):
        checked_sha(record.get(name))
    if record["base_sha"] == record["head_sha"]:
        raise Denial("No code commit present")
    paths = record.get("changed_paths")
    if not isinstance(paths, list) or not paths or paths != sorted(set(paths)) or set(paths) - ALLOWED:
        raise Denial("Invalid touched files")
    tests = record.get("tests")
    if not isinstance(tests, dict) or tests.get("command") != list(TEST):
        raise Denial("Unknown test command")
    if tests.get("state") not in ("PASSED", "FAILED", "BLOCKED"):
        raise Denial("Unknown test status")
    if tests["state"] == "PASSED" and (tests.get("exit_code") != 0
                                       or type(tests.get("count")) is not int
                                       or tests["count"] < 1):
        raise Denial("Unsubstantiated successful test")
    if not WORKER.fullmatch(str(record.get("worker", ""))):
        raise Denial("Worker name invalid")
    if not re.fullmatch(r"[0-9a-f]{32}", str(record.get("claim_id", ""))):
        raise Denial("Claim ID invalid")
    if type(record.get("epoch")) is not int or record["epoch"] < 1:
        raise Denial("Lease epoch invalid")
    if record.get("issue_commands_executed") is not False or record.get("deployed") is not False:
        raise Denial("Prohibited side effect claim")
    return True


def generate(wt, worker, claim_id, fence, lease=None):
    if not WORKER.fullmatch(worker):
        raise Denial("Worker identity malformed")
    checked_sha(fence)
    info = inspect(wt)
    control = lease if lease is not None else Lease()
    control.verify(REPO, ISSUE, worker, claim_id, fence)
    tests = fixed_tests(Path(wt).resolve())
    control.verify(REPO, ISSUE, worker, claim_id, fence)
    _, _, current = control.current(REPO, ISSUE)
    if not current or type(current.get("epoch")) is not int:
        raise Denial("Missing verified lease epoch")
    result = {
        "format": "star-code-receipt/v1", "repo": REPO, "issue": ISSUE,
        "url": "https://github.com/" + REPO + "/issues/44",
        "branch": BRANCH, **info, "worker": worker,
        "claim_id": claim_id, "fence": fence, "epoch": current["epoch"],
        "tests": tests, "recorded_at": datetime.now(timezone.utc).isoformat(),
        "issue_commands_executed": False, "deployed": False,
    }
    validate(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--claim-id", required=True)
    parser.add_argument("--fence", required=True)
    args = parser.parse_args(argv)
    try:
        result = generate(args.worktree, args.worker, args.claim_id, args.fence)
    except (Denial, Denied, issue_preflight.PreflightDenied) as exc:
        print("STAR_RECEIPT_DENIED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["tests"]["state"] == "PASSED" else 2


if __name__ == "__main__":
    sys.exit(main())
