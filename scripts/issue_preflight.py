#!/usr/bin/env python3
"""Fail-closed, READ-ONLY preflight for manually selected GitHub Issues.

This is not an autonomous executor and does not acquire a distributed lease.
The GitHub Actions workflow serializes *its own* dry-run invocations only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys

# Explicitly public, active repositories for the first pilot. Any expansion
# requires a reviewed policy update (especially for private repos).
PUBLIC_ALLOWLIST = frozenset({
    "memolabs-dev/.github",
    "memolabs-dev/cuesheet",
    "memolabs-dev/uni-protocol",
    "memolabs-dev/problem-intelligence-engine",
    "memolabs-dev/drop",
    "memolabs-dev/lab-hub",
    "memolabs-dev/memo-bridge",
})
BLOCKED_LABELS = frozenset({
    "status:blocked", "needs:human", "type:epic", "agent:working",
})
PRIORITIES = frozenset({"priority:p0", "priority:p1", "priority:p2"})
ISSUE_NUMBER = re.compile(r"^[1-9][0-9]{0,7}$")


class PreflightDenied(Exception):
    """Expected negative decision; never fall back to execution."""


def checked_repo(value):
    if not isinstance(value, str) or value not in PUBLIC_ALLOWLIST:
        raise PreflightDenied("Repository not in the explicit public pilot allowlist")
    return value


def checked_number(value):
    if not ISSUE_NUMBER.fullmatch(str(value)):
        raise PreflightDenied("Invalid issue number")
    return int(value)


def get_json(path, runner=subprocess.run):
    # No user-provided command line flags or shell interpolations.
    result = runner(
        ["gh", "api", "-X", "GET", path],
        capture_output=True, text=True, check=False, timeout=25,
    )
    if result.returncode != 0:
        raise PreflightDenied("Cannot verify GitHub source metadata; fail closed")
    try:
        payload = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise PreflightDenied("GitHub API returned invalid JSON") from None
    if not isinstance(payload, dict):
        raise PreflightDenied("GitHub API returned an invalid object")
    return payload


def assess(repo, number, runner=subprocess.run, holding=False):
    """Eligibility of an Issue. holding=True is the check made by the current lease holder:
    the agent:working label it is expected to set no longer blocks it."""
    repo = checked_repo(repo)
    number = checked_number(number)
    metadata = get_json("repos/" + repo, runner)
    if metadata.get("full_name") != repo:
        raise PreflightDenied("Repository identity mismatch")
    if metadata.get("private") is not False or metadata.get("archived") is not False:
        raise PreflightDenied("Repository must be confirmed public and active")

    issue = get_json("repos/" + repo + "/issues/" + str(number), runner)
    if "pull_request" in issue or issue.get("number") != number:
        raise PreflightDenied("Selected item is not the expected Issue")
    if issue.get("state") != "open" or issue.get("state_reason") == "completed":
        raise PreflightDenied("Issue is not open")

    labels = issue.get("labels")
    if not isinstance(labels, list):
        raise PreflightDenied("Cannot verify issue labels")
    label_names = {label.get("name") if isinstance(label, dict) else label for label in labels}
    if any(not isinstance(label, str) for label in label_names):
        raise PreflightDenied("Invalid issue label data")
    if "agent:ready" not in label_names:
        raise PreflightDenied("Issue is not explicitly agent:ready")
    blockers = BLOCKED_LABELS - {"agent:working"} if holding else BLOCKED_LABELS
    blocked = sorted(label_names.intersection(blockers))
    if blocked:
        raise PreflightDenied("Issue has blocking labels: " + ", ".join(blocked))
    selected_priorities = sorted(label_names.intersection(PRIORITIES))
    if len(selected_priorities) != 1:
        raise PreflightDenied("Issue must have exactly one explicit priority label")

    source_url = "https://github.com/" + repo + "/issues/" + str(number)
    if issue.get("html_url") != source_url:
        raise PreflightDenied("Issue URL identity mismatch")
    if not isinstance(issue.get("updated_at"), str) or not issue.get("updated_at"):
        raise PreflightDenied("Missing change-tracking timestamp")

    # Receipt intentionally does not copy raw Issue body/title, private data,
    # commands, or arbitrary instructions into another execution context.
    return {
        "decision": "DRY_RUN_ELIGIBLE_NOT_CLAIMED",
        "repository": repo,
        "issue_number": number,
        "issue_url": source_url,
        "priority": selected_priorities[0],
        "issue_updated_at": issue["updated_at"],
        "issue_body_sha256": hashlib.sha256(
            (issue.get("body") or "").encode("utf-8")
        ).hexdigest(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "runner": "manual_preflight_only",
        "execution_performed": False,
        "lease_acquired": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = assess(args.repo, args.issue)
    except PreflightDenied as exc:
        # Don't reveal entire API response, Issue body, secrets or token.
        print("PREFLIGHT_DENIED: " + str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(receipt, sort_keys=True, indent=2))
    else:
        print(f"Eligible for review (NOT claimed): {receipt['issue_url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
