#!/usr/bin/env python3
"""Read-only GitHub governance snapshot for Memo Labs.

A 404 on the classic protection API NEVER implies that a branch is
unprotected: repository/organization rulesets may still apply.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

REPOSITORIES = (
    ".github", "cuesheet", "uni-protocol", "problem-intelligence-engine",
    "drop", "lab-hub", "kollio-v3", "emargo", "lab-console"
)
OWNER = "memolabs-dev"


def read_api(endpoint):
    result = subprocess.run(
        ["gh", "api", endpoint],
        capture_output=True, text=True, timeout=22
    )
    if result.returncode:
        # Never print error bodies or tokens. Endpoint may be 404 or 403.
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def repository_report(name):
    prefix = f"repos/{OWNER}/{name}"
    repository = read_api(prefix)
    row = {
        "repository": f"{OWNER}/{name}",
        "visibility": "unknown",
        "default_branch": "unknown",
        "classic_protection": "unknown",
        "required_checks": None,
        "branch_rulesets": None,
        "workflow_inventory": None,
        "warnings": [],
    }
    if not isinstance(repository, dict):
        row["warnings"].append("Repository API inaccessible; no safety conclusion")
        return row
    row["visibility"] = (
        "private" if repository.get("private") is True else
        "public" if repository.get("private") is False else "unknown"
    )
    branch = repository.get("default_branch") or ""
    if not isinstance(branch, str) or not branch:
        row["warnings"].append("Unable to determine default branch")
        return row
    row["default_branch"] = branch
    protected = read_api(f"{prefix}/branches/{branch}/protection")
    if isinstance(protected, dict) and protected.get("url"):
        row["classic_protection"] = "present"
        checks = protected.get("required_status_checks")
        row["required_checks"] = (
            checks.get("contexts", []) if isinstance(checks, dict) else []
        )
        review = protected.get("required_pull_request_reviews")
        row["minimum_review_approvals"] = (
            review.get("required_approving_review_count", 0)
            if isinstance(review, dict) else 0
        )
        admins = protected.get("enforce_admins") or {}
        row["admins_enforced"] = admins.get("enabled")
    else:
        row["warnings"].append(
            "Classic branch protection not visible; this does not imply unprotected"
        )
    rulesets = read_api(f"{prefix}/rulesets")
    if isinstance(rulesets, list):
        row["branch_rulesets"] = sorted(
            [
                {"name": x.get("name"), "enforcement": x.get("enforcement"),
                 "target": x.get("target")}
                for x in rulesets if x.get("target") == "branch"
            ], key=lambda r: (r["name"] or "")
        )
        if row["branch_rulesets"]:
            row["warnings"].append(
                "Rulesets exist; inspect each rule's ref conditions before claiming "
                "protection of the default branch"
            )
    else:
        row["warnings"].append("Unable to verify effective branch rulesets")
    workflows = read_api(f"{prefix}/actions/workflows?per_page=100")
    if isinstance(workflows, dict) and isinstance(workflows.get("workflows"), list):
        row["workflow_inventory"] = sorted(
            [{"name": w.get("name"), "state": w.get("state")}
             for w in workflows["workflows"]],
            key=lambda w: w["name"] or ""
        )
    else:
        row["warnings"].append("Unable to retrieve GitHub Actions workflows")
    return row


def inventory(repos=REPOSITORIES):
    return {
        "as_of_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "read_only": True,
        "scope": OWNER,
        "repositories": [repository_report(name) for name in repos],
        "limitations": [
            "Ruleset presence alone does not prove that it targets the default branch.",
            "Absent/inaccessible classic protection does not imply absence of rulesets.",
            "Workflow existence or CI success does not prove a protected deployment.",
            "API responses depend on the calling GitHub identity's access.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo", choices=REPOSITORIES, action="append")
    args = parser.parse_args()
    result = inventory(tuple(args.repo) if args.repo else REPOSITORIES)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    for row in result["repositories"]:
        rules = row["branch_rulesets"]
        print(
            f"{row['repository']}: default={row['default_branch']}, "
            f"visibility={row['visibility']}, "
            f"classic={row['classic_protection']}, "
            f"branch_rulesets={len(rules) if rules is not None else 'unknown'}, "
            f"workflows={len(row['workflow_inventory']) if row['workflow_inventory'] is not None else 'unknown'}"
        )
    print("No governance settings were changed; unknown statuses are not passes.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"Governance audit incomplete: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
