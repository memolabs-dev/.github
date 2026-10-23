#!/usr/bin/env python3
"""Fail-closed, READ-ONLY preflight for manually selected GitHub Issues.

This is not an autonomous executor and does not acquire a distributed lease.
The GitHub Actions workflow serializes *its own* dry-run invocations only.
"""
import argparse
import private_owner_allowlist as owner_private
from datetime import datetime, timezone
import hashlib
import json
import re
import subprocess
import sys

# Scope (owner decisions of 2026-10-17 and 2026-10-22, memo-bridge owner-console spec T-A1 and
# memo-bridge#257): any repository of the owner's namespaces, the memolabs-dev organization and
# his own account guillaume-flambard, that GitHub confirms public and not archived. Private
# repositories still need the owner's Mac-only enrollment (private_owner_allowlist).
OWNER_NAMESPACES = ("memolabs-dev", "guillaume-flambard")
ORG_REPO = re.compile(r"^(?:memolabs-dev|guillaume-flambard)/(?!\.\.?$)[A-Za-z0-9._-]{1,100}$")

# Compatibility literal, NOT used by this script. The deployed Memo Bridge coordinator reads this
# exact `PUBLIC_ALLOWLIST = frozenset({...})` text from this file as its pre-filter
# (memo-bridge server/coordinator/index.mjs parsePublicAllowlist); without it every claim fails
# with ledger_unavailable (incident of 2026-10-18, memo-bridge owner-console spec). Keep it equal
# to the public projects of lab-infra memo_runner_pilot_repos plus this repository, until Memo
# Bridge understands ORG_REPO; then delete it. tests/test_issue_preflight.py checks its shape.
PUBLIC_ALLOWLIST = frozenset({
    "memolabs-dev/.github",
    "memolabs-dev/memo-bridge",
    "memolabs-dev/cuesheet",
    "memolabs-dev/uni-protocol",
    "memolabs-dev/problem-intelligence-engine",
    "memolabs-dev/drop",
    "memolabs-dev/lab-hub",
    "memolabs-dev/agent-reality-bench",
    "memolabs-dev/aidd-guard",
    "memolabs-dev/intentlane",
    "memolabs-dev/kollio-mac",
    "memolabs-dev/life-os",
    "memolabs-dev/memo-cc",
    "memolabs-dev/navirox",
    "memolabs-dev/stasis",
    "memolabs-dev/trufflo",
    "memolabs-dev/valve",
    "memolabs-dev/world-kernel",
})
BLOCKED_LABELS = frozenset({
    "status:blocked", "needs:human", "type:epic", "agent:working",
})
PRIORITIES = frozenset({"priority:p0", "priority:p1", "priority:p2"})
ISSUE_NUMBER = re.compile(r"^[1-9][0-9]{0,7}$")


class PreflightDenied(Exception):
    """Expected negative decision; never fall back to execution."""


def checked_repo(value):
    # A repository name in the owner's namespaces; whether it is public is confirmed against
    # GitHub in assess() before any Issue is read. A VPS, a discovery snapshot, or a
    # caller-provided repo name never grants access to a private repository.
    # The message keeps "allowlist": memo-bridge maps it to repo_not_allowed.
    if not isinstance(value, str) or not ORG_REPO.fullmatch(value):
        raise PreflightDenied("Repository not in the owner namespaces allowlist")
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
    # GitHub decides public or private. Public and not archived: allowed. Private: only with
    # the owner's Mac-only opt-in policy. Anything else (unknown, archived) fails closed.
    if metadata.get("archived") is not False or metadata.get("private") not in (True, False):
        raise PreflightDenied("Repository privacy or enrollment mismatch")
    # A new lease also needs the owner's per-call marker; the holder's own checks do not
    # (private_owner_allowlist.allowed, fix pass of memo-bridge#258).
    if metadata.get("private") is True and not owner_private.allowed(repo, holding=holding):
        raise PreflightDenied("Repository privacy or enrollment mismatch")

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
        # GitHub's answer above; the lease keeps a private repository's identity out of the
        # public ledger (issue_lease.py).
        "repository_private": metadata["private"],
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
