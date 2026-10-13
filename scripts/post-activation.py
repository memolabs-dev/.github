#!/usr/bin/env python3
"""Prepare or explicitly dispatch read-only repository verification workflows."""
import argparse
import subprocess
import sys

ALLOWED = (
    ".github", "cuesheet", "uni-protocol", "problem-intelligence-engine",
    "drop", "lab-hub", "kollio-v3", "emargo", "lab-console"
)


def command(repo):
    if repo not in ALLOWED:
        raise ValueError("Repository is outside the approved Memo Labs inventory")
    return [
        "gh", "workflow", "run", "app-repo-access-smoke.yml",
        "-R", "memolabs-dev/.github", "--ref", "main", "-f", "repository=" + repo
    ]


def main():
    parser = argparse.ArgumentParser(description="Read-only installation probes")
    parser.add_argument("--repos", nargs="+", choices=ALLOWED, default=[".github", "cuesheet"])
    parser.add_argument("--execute", action="store_true", help="Dispatch workflows; without this flag, dry-run")
    args = parser.parse_args()
    errors = 0
    for repo in args.repos:
        cmd = command(repo)
        if not args.execute:
            print("PENDING:", repo, "- manual read-only workflow, no dispatch")
            continue
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=25)
        if result.returncode:
            errors += 1
            print("FAILED:", repo, "(not installed or workflow unavailable)")
        else:
            print("DISPATCHED:", repo, "(check result in GitHub Actions)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
