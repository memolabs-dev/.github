#!/usr/bin/env python3
"""Memo Steward v0: read-only stale pull request candidates; no mutation."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import subprocess

REPOS = (
    "drop", "cuesheet", "uni-protocol", "problem-intelligence-engine",
    "kollio-v3", "emargo", "lab-hub", "lab-console", ".github"
)

def candidates(repo, cutoff):
    result = subprocess.run(
        ["gh", "pr", "list", "-R", f"memolabs-dev/{repo}", "--state", "open",
         "--limit", "100", "--json", "number,title,url,updatedAt,isDraft"],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode:
        return None
    found = []
    for item in json.loads(result.stdout):
        last = datetime.fromisoformat(item["updatedAt"].replace("Z", "+00:00"))
        if last < cutoff:
            found.append({
                "repo": repo, "number": item["number"],
                "days_idle": (datetime.now(timezone.utc)-last).days,
                "draft": item["isDraft"], "url": item["url"]
            })
    return found

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days",type=int,default=14)
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days must be between 1 and 365")
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    print("Memo Steward: candidates for review only. No PR or branch will be changed.")
    count = 0
    for repo in REPOS:
        try:
            rows = candidates(repo, cutoff)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            rows = None
        if rows is None:
            print(f"{repo}: unable to verify")
            continue
        for row in rows:
            count += 1
            print(f"{repo} PR #{row['number']}: {row['days_idle']} idle days; "
                  f"draft={row['draft']}; {row['url']}")
    print(f"Total review candidates: {count}")

if __name__ == "__main__":
    main()
