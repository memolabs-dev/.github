#!/usr/bin/env python3
"""Evidence-bound read-only CI preflight for the future Memo Guardian.

This reports GitHub Actions CI provenance, not independent code quality.
It never publishes Checks, merges PRs, or changes repository settings.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
POLICY_FILE = ROOT / "github-apps/guardian-cuesheet-policy.json"


def read_github(path):
    result = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, timeout=25
    )
    if result.returncode:
        raise RuntimeError("GitHub data unavailable")
    return json.loads(result.stdout)


def load_policy():
    obj = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    if (
        obj.get("contract") != "memo-guardian/ci-provenance"
        or obj.get("repository") != "memolabs-dev/cuesheet"
        or obj.get("version") != "0.1.0"
        or obj.get("trusted_check_publisher") != "github-actions"
        or obj.get("required_checks") != ["Core and integration tests"]
    ):
        raise RuntimeError("Unexpected Guardian CI evidence policy")
    return obj


def evaluate(policy, sha, check_runs, *, pr_draft=False):
    """Fail closed on missing, duplicated, untrusted or stale CI results."""
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise ValueError("A full 40-character commit SHA is required")
    findings = []
    decisions = []
    for name in policy["required_checks"]:
        matching_name = [
            run for run in check_runs
            if run.get("name") == name
        ]
        exact = [
            run for run in matching_name
            if run.get("head_sha", "").lower() == sha.lower()
        ]
        finding = {"required_check": name, "matching_runs_on_sha": len(exact)}
        if len(exact) != 1:
            finding["reason"] = (
                "missing_check_for_exact_sha" if not exact
                else "ambiguous_multiple_checks_for_exact_sha"
            )
            finding["result"] = "incomplete"
            decisions.append("incomplete")
        else:
            check = exact[0]
            finding["check_id"] = check.get("id")
            finding["check_url"] = check.get("html_url")
            finding["publisher"] = (check.get("app") or {}).get("slug")
            finding["status"] = check.get("status")
            finding["conclusion"] = check.get("conclusion")
            if (finding["publisher"] != policy["trusted_check_publisher"]
                or not isinstance(finding["check_id"], int)
                or finding["check_id"] <= 0):
                finding["result"] = "incomplete"
                finding["reason"] = "untrusted_or_unidentifiable_check"
                decisions.append("incomplete")
            elif finding["status"] != "completed":
                finding["result"] = "incomplete"
                finding["reason"] = "check_not_completed"
                decisions.append("incomplete")
            elif finding["conclusion"] != "success":
                finding["result"] = "blocked"
                finding["reason"] = "required_check_not_successful"
                decisions.append("blocked")
            else:
                finding["result"] = "ci_success"
                findings.append(finding)
                decisions.append("ci_success")
                continue
        findings.append(finding)
    final = (
        "incomplete" if "incomplete" in decisions
        else "blocked" if "blocked" in decisions
        else "ci_success"
    )
    receipt = {
        "contract": policy["contract"],
        "policy_version": policy["version"],
        "repository": policy["repository"],
        "commit_sha": sha.lower(),
        "ci_gate": final,
        "pull_request_is_draft": bool(pr_draft),
        "can_merge": False,  # Never infer merge eligibility from CI alone.
        "quality_certified": False,
        "checks": findings,
        "explanation": (
            "CI provenance preflight only; this receipt is not a code-quality "
            "review, a Guardian Checks API attestation, or permission to merge."
        ),
    }
    # Checksum is useful for comparison, NOT a cryptographic signature.
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    receipt["receipt_checksum_sha256"] = hashlib.sha256(canonical).hexdigest()
    return receipt


def run(pr_number):
    policy = load_policy()
    repo = policy["repository"]
    pull = read_github(f"repos/{repo}/pulls/{pr_number}")
    if (not isinstance(pull, dict) or pull.get("base", {}).get("repo", {}).get("full_name") != repo):
        raise RuntimeError("PR does not belong to the approved repository")
    sha = pull.get("head", {}).get("sha")
    if not isinstance(sha, str) or not re.fullmatch("[0-9a-fA-F]{40}", sha):
        raise RuntimeError("PR has no valid immutable head SHA")
    check_result = read_github(f"repos/{repo}/commits/{sha}/check-runs?per_page=100")
    if not isinstance(check_result, dict) or not isinstance(check_result.get("check_runs"), list):
        raise RuntimeError("GitHub Checks response missing or invalid")
    if check_result.get("total_count", 0) > len(check_result["check_runs"]):
        raise RuntimeError("GitHub Checks response paginated; refusing partial evidence")
    receipt = evaluate(policy, sha, check_result["check_runs"], pr_draft=pull.get("draft", True))
    receipt["pull_request"] = pr_number
    receipt["collected_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, required=True)
    args = parser.parse_args()
    if args.pr < 1:
        parser.error("PR number must be positive")
    receipt = run(args.pr)
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt["ci_gate"] == "ci_success" else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"Guardian CI provenance unavailable: {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
