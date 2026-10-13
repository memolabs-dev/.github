#!/usr/bin/env python3
"""Memo Radar v0: last GitHub CI run per repository, read-only."""
import json
import subprocess
import sys

REPOSITORIES = (
    "drop", "cuesheet", "uni-protocol", "problem-intelligence-engine",
    "kollio-v3", "emargo", "lab-hub", "lab-console", ".github"
)

def recent_run(name):
    result = subprocess.run(
        ["gh", "run", "list", "-R", f"memolabs-dev/{name}", "--limit", "1",
         "--json", "workflowName,status,conclusion,url,headSha,createdAt"],
        text=True, capture_output=True, timeout=20,
    )
    if result.returncode:
        return {"status": "unknown", "workflow": "-", "url": ""}
    entries = json.loads(result.stdout)
    if not entries:
        return {"status": "none", "workflow": "-", "url": ""}
    run = entries[0]
    outcome = run.get("conclusion") if run.get("status") == "completed" else run.get("status")
    return {
        "status": outcome or "unknown",
        "workflow": run.get("workflowName") or "unnamed",
        "url": run.get("url") or "",
        "sha": (run.get("headSha") or "")[:10],
    }

def main():
    print("| Repository | Last workflow | Last run | Deployment |")
    print("| --- | --- | --- | --- |")
    for repo in REPOSITORIES:
        try:
            run = recent_run(repo)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            run = {"status":"unknown","workflow":"-","url":""}
        name = run.get("workflow", "-").replace("|", "/")
        status = run.get("status", "unknown")
        url = run.get("url")
        linked = f"[{status}]({url})" if url else status
        print(f"| `{repo}` | {name} | {linked} | Unknown; independent runtime proof required |")
    print("\nBuild/CI is NOT proof of production deployment.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Radar unavailable:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
