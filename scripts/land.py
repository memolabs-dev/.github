#!/usr/bin/env python3
"""Memo Labs landing contract: merge a pull request once its exact head commit is verified.

One contract for every repository, public or private, with or without branch protection.
It is called by `.github/workflows/land.yml` after a CI workflow completes, and decides from
GitHub API metadata only. It never checks out or executes code from the pull request.

A pull request lands only when all of these hold on the exact tested SHA:
- it is open, not a draft, from the same repository, targets the default branch;
- its author is a trusted identity and it carries no `hold-merge` label;
- it touches no protected path (workflows, deployment, infrastructure): those need a human;
- every check run and commit status on that SHA is complete and green, at least one exists,
  and every required check (for example a UNI or Guardian receipt) is present and green.

Agents never merge. This gate does, with --match-head-commit so a newer untested push
can never be merged in place of the verified one.
"""
import argparse
import json
import os
import re
import subprocess
import sys

CONTRACT = "memo-labs/landing@0.1.0"
TRUSTED_AUTHORS = ("guillaume-flambard", "memo-labs-automation[bot]", "drop-agent-bot")
HOLD_LABEL = "hold-merge"
PROTECTED_PATHS = (
    r"^\.github/",
    r"(^|/)Dockerfile[^/]*$",
    r"^docker/",
    r"^deploy(ment)?/",
    r"^scripts/deploy",
    r"^ansible/",
    r"^stacks/",
    r"^infra(structure)?/",
)
OK_CONCLUSIONS = {"success", "neutral", "skipped"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_FILES = 100
MAX_CHECKS = 100


def _verdict(land, reason, **extra):
    return {"contract": CONTRACT, "land": land, "reason": reason, **extra}


def protected(paths, extra_patterns=()):
    patterns = [re.compile(p) for p in (*PROTECTED_PATHS, *extra_patterns)]
    return sorted({p for p in paths if any(rx.search(p) for rx in patterns)})


def decide(pr, files, check_runs, check_total, status, sha, policy):
    """Pure decision. Returns a verdict; `wait` reasons mean a later CI completion may land it."""
    repo = policy["repository"]
    if not SHA_RE.match(sha or ""):
        return _verdict(False, "invalid_sha")
    if pr.get("state") != "open":
        return _verdict(False, "not_open")
    if pr["head"]["sha"] != sha:
        return _verdict(False, "head_moved")
    if (pr["head"].get("repo") or {}).get("full_name") != repo:
        return _verdict(False, "external_branch")
    if pr["base"]["ref"] != pr["base"]["repo"]["default_branch"]:
        return _verdict(False, "not_default_branch")
    if pr.get("draft"):
        return _verdict(False, "draft")
    if pr["user"]["login"] not in policy.get("trusted_authors", TRUSTED_AUTHORS):
        return _verdict(False, "untrusted_author")
    if HOLD_LABEL in {label["name"] for label in pr.get("labels", [])}:
        return _verdict(False, "hold_label")

    if pr.get("changed_files", 0) > MAX_FILES or len(files) != pr.get("changed_files", len(files)):
        return _verdict(False, "files_not_exhaustive")
    paths = [f["filename"] for f in files] + [f["previous_filename"] for f in files if f.get("previous_filename")]
    hits = protected(paths, policy.get("extra_protected", ()))
    if hits:
        return _verdict(False, "protected_paths", paths=hits[:10])

    if check_total > len(check_runs) or check_total > MAX_CHECKS:
        return _verdict(False, "checks_not_exhaustive")
    if not check_runs and not status.get("statuses"):
        return _verdict(False, "wait_no_checks")
    if any(run["head_sha"] != sha for run in check_runs):
        return _verdict(False, "check_for_other_sha")
    pending = sorted(run["name"] for run in check_runs if run["status"] != "completed")
    if pending:
        return _verdict(False, "wait_checks_running", checks=pending[:10])
    failed = sorted(run["name"] for run in check_runs if run["conclusion"] not in OK_CONCLUSIONS)
    if failed:
        return _verdict(False, "checks_failed", checks=failed[:10])
    if status.get("statuses"):
        if status.get("state") == "pending":
            return _verdict(False, "wait_status_pending")
        if status.get("state") != "success":
            return _verdict(False, "status_failed")

    green = {run["name"] for run in check_runs if run["conclusion"] in OK_CONCLUSIONS - {"skipped"}}
    green |= {s["context"] for s in status.get("statuses", []) if s.get("state") == "success"}
    missing = sorted(set(policy.get("required_checks", ())) - green)
    if missing:
        return _verdict(False, "wait_required_checks", checks=missing)
    return _verdict(True, "verified", pr=pr["number"])


def gh(args, *, as_json=True):
    result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        # Never echo response bodies: they may contain tokens or private content.
        raise RuntimeError(f"gh {' '.join(args[:2])} failed ({result.returncode})")
    return json.loads(result.stdout) if as_json else result.stdout


def gather(repo, sha, number):
    pr = gh(["api", f"repos/{repo}/pulls/{number}"])
    files = gh(["api", f"repos/{repo}/pulls/{number}/files?per_page={MAX_FILES}"])
    checks = gh(["api", f"repos/{repo}/commits/{sha}/check-runs?per_page={MAX_CHECKS}"])
    status = gh(["api", f"repos/{repo}/commits/{sha}/status"])
    return pr, files, checks.get("check_runs", []), checks.get("total_count", 0), status


def report(verdict):
    line = json.dumps(verdict, sort_keys=True)
    print(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(f"- `{line}`\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--method", choices=("squash", "merge"), default="squash")
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument("--extra-protected", action="append", default=[])
    parser.add_argument("--dispatch", action="append", default=[], help="workflow file to run on the base branch after landing")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not SHA_RE.match(args.sha):
        report(_verdict(False, "invalid_sha"))
        return 1

    policy = {"repository": args.repo, "required_checks": args.required_check,
              "extra_protected": args.extra_protected}
    numbers = [p["number"] for p in gh(["api", f"repos/{args.repo}/commits/{args.sha}/pulls"]) if p.get("state") == "open"]
    if not numbers:
        report(_verdict(False, "no_open_pr", sha=args.sha))
        return 0
    exit_code = 0
    for number in numbers:
        pr, files, runs, total, status = gather(args.repo, args.sha, number)
        verdict = decide(pr, files, runs, total, status, args.sha, policy)
        verdict["pr"] = number
        if verdict["land"] and not args.dry_run:
            try:
                gh(["pr", "merge", str(number), "--repo", args.repo, f"--{args.method}",
                    "--match-head-commit", args.sha, "--delete-branch"], as_json=False)
                verdict["merged"] = True
                # Merges made with GITHUB_TOKEN do not trigger push workflows: run them explicitly.
                for workflow in args.dispatch:
                    gh(["workflow", "run", workflow, "--repo", args.repo, "--ref", pr["base"]["ref"]], as_json=False)
                verdict["dispatched"] = args.dispatch
            except RuntimeError as error:
                verdict.update(merged=False, reason="merge_refused", detail=str(error))
                exit_code = 1
        report(verdict)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
