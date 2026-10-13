#!/usr/bin/env python3
"""Read-only GitHub issue queue for explicitly triaged STAR work.

Never executes an Issue's content. Not an autonomous agent scheduler.
"""
import argparse
import json
import subprocess
import sys

BLOCKERS = {"agent:working", "needs:human", "status:blocked", "type:epic"}
RANK = {"priority:p0": 0, "priority:p1": 1, "priority:p2": 2}


def get_queue(org="memolabs-dev", repo=None, limit=30, runner=subprocess.run):
    """Return safe-to-offer task candidates, never permission to execute them."""
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    scope = "repo:" + repo if repo else "org:" + org
    search = (
        'is:issue is:open label:"agent:ready" '
        '-label:"agent:working" -label:"needs:human" '
        '-label:"status:blocked" -label:"type:epic" ' + scope
    )
    args = ["gh", "api", "-X", "GET", "search/issues", "-f", "q=" + search, "-f", "per_page=" + str(limit)]
    result = runner(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError((result.stderr or "GitHub query failed").strip())
    payload = json.loads(result.stdout)
    found = []
    for issue in payload.get("items", []):
        if "pull_request" in issue:
            continue
        labels = {value["name"] if isinstance(value, dict) else value for value in issue.get("labels", [])}
        if "agent:ready" not in labels or labels.intersection(BLOCKERS):
            continue
        target = issue.get("repository_url", "").split("/repos/", 1)[-1]
        if "/" not in target:
            continue
        rank = next((value for label, value in RANK.items() if label in labels), 3)
        found.append({
            "repo": target, "number": issue["number"], "title": issue["title"],
            "url": issue["html_url"], "priority": "P" + str(rank) if rank != 3 else "Untriaged",
            "_rank": rank,
        })
    found.sort(key=lambda x: (x["_rank"], x["repo"], x["number"]))
    for item in found:
        item.pop("_rank")
    return found[:limit]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="memolabs-dev", help="Organization to scan (ignored when --repo is provided)")
    parser.add_argument("--repo", help="Only one repository, including personal repositories")
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--json", action="store_true", help="Print structured JSON")
    args = parser.parse_args(argv)
    try:
        issues = get_queue(org=args.org, repo=args.repo, limit=args.limit)
    except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print("Queue unavailable: " + str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(issues, indent=2, ensure_ascii=False))
    elif not issues:
        print("No eligible agent:ready Issues. This does not imply the backlog is empty.")
    else:
        for item in issues:
            print(f"{item['priority']}  {item['repo']}#{item['number']} — {item['title']}\n  {item['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
