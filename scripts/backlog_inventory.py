#!/usr/bin/env python3
"""Read-only public GitHub backlog reconciliation. No Issue mutations.

Links references to existing issues as *mentions*, not proof of ownership.
Never imports archived changes or scans private repositories.
"""
import argparse
import base64
from collections import Counter
import hashlib
import json
import re
import subprocess
import sys

PUBLIC_SOURCES = {
    "memolabs-dev/drop": ["docs/TASKS.md"],
    "memolabs-dev/cuesheet": ["docs/harness/TODO.md"],
    "memolabs-dev/uni-protocol": ["docs/roadmap.md", "specs/003-assurance-model/tasks.md"],
    "memolabs-dev/problem-intelligence-engine": ["docs/ROADMAP.md"],
    "guillaume-flambard/kollio-mac": [],  # dynamic active l0-l9/tasks.md below
}
CHECKBOX = re.compile(r"^\s*-\s*\[([xX ])\]\s*(.*)$")
TASK_ID = re.compile(r"^([A-Z]{1,4}[0-9]+(?:\.[0-9]+[a-z]?)?)\b", re.I)
DROP_START = re.compile(r"^\|\s*(T[0-9]+(?:\.[0-9]+[a-z]?)?)\s*\|", re.I)
DROP_STATE = re.compile(r"\|\s*(todo|doing|done|blocked|superseded|deferred)\s*\|\s*$", re.I)
LOT_TASK = re.compile(r"^openspec/changes/l[0-9]+-[^/]+/tasks\.md$")


class InventoryError(Exception):
    pass


def api_json(endpoint, runner=subprocess.run):
    p = runner(["gh", "api", "-X", "GET", endpoint], capture_output=True, text=True,
               check=False, timeout=45)
    if p.returncode:
        raise InventoryError("GitHub API not available for an audited public source")
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise InventoryError("Invalid GitHub API response") from None


def source_text(repo, path, runner=subprocess.run):
    payload = api_json("repos/" + repo + "/contents/" + path, runner)
    if payload.get("type") != "file" or payload.get("encoding") != "base64":
        raise InventoryError("Unexpected source representation")
    try:
        return base64.b64decode(payload["content"], validate=False).decode("utf-8")
    except (ValueError, KeyError, UnicodeDecodeError):
        raise InventoryError("Source is not decodable UTF-8") from None


def parse_checkboxes(content, prefix=""):
    found = []
    for number, line in enumerate(content.splitlines(), 1):
        match = CHECKBOX.match(line)
        if not match:
            continue
        detail = match.group(2).strip()
        id_match = TASK_ID.match(detail)
        found.append({
            "id": id_match.group(1).upper() if id_match else prefix + str(number),
            "line": number, "status": "done" if match.group(1).lower() == "x" else "todo",
        })
    return found


def parse_drop_index(content):
    """A table row may span multiple lines, so finish at the next task ID."""
    rows = []
    start, current = None, []
    def flush():
        if start is None:
            return
        combined = "\n".join(current).strip()
        last = DROP_STATE.search(combined)
        rows.append({"id": start[0], "line": start[1],
                     "status": last.group(1).lower() if last else "unparsed"})
    for number, line in enumerate(content.splitlines(), 1):
        match = DROP_START.match(line)
        if match:
            flush()
            start, current = (match.group(1), number), [line]
        elif start is not None:
            current.append(line)
    flush()
    return rows


def explicit_mentions(task_id, issues):
    # Delimiters prevent H01.1 matching H01.10. A mention is *not* proof
    # that the Issue is the canonical owner of the task.
    regex = re.compile(r"(?<![\w.])" + re.escape(task_id) + r"(?![\w.])", re.I)
    return sorted({
        issue["number"] for issue in issues
        if regex.search((issue.get("title") or "") + "\n" + (issue.get("body") or ""))
    })


def scan(repo, runner=subprocess.run):
    if repo not in PUBLIC_SOURCES:
        raise InventoryError("Repository absent from public allowlist")
    meta = api_json("repos/" + repo, runner)
    if meta.get("full_name") != repo or meta.get("private") is not False or meta.get("archived") is not False:
        raise InventoryError("Source repository must be verified public and active")
    files = list(PUBLIC_SOURCES[repo])
    if repo == "guillaume-flambard/kollio-mac":
        tree = api_json("repos/" + repo + "/git/trees/" + meta.get("default_branch", "main") + "?recursive=1", runner)
        if tree.get("truncated"):
            raise InventoryError("Source tree truncated")
        files = sorted(e["path"] for e in tree.get("tree", [])
                       if e.get("type") == "blob" and LOT_TASK.match(e.get("path", "")))
        if not files:
            raise InventoryError("Active lot task files missing")
    issue_payload = api_json("repos/" + repo + "/issues?state=open&per_page=100", runner)
    if not isinstance(issue_payload, list):
        raise InventoryError("Cannot retrieve existing Issues")
    # GitHub /issues also returns PRs. Explicitly ignore these.
    issues = [obj for obj in issue_payload if "pull_request" not in obj]
    if len(issue_payload) >= 100:
        raise InventoryError("Issue response pagination incomplete; no report emitted")
    summary = []
    task_examples = []
    for path in files:
        content = source_text(repo, path, runner)
        if repo == "memolabs-dev/drop":
            tasks = parse_drop_index(content)
        else:
            prefix = path.split("/")[-2].upper() + "-L"
            tasks = parse_checkboxes(content, prefix=prefix)
        for task in tasks:
            task["mentions"] = explicit_mentions(task["id"], issues) if not task["id"].endswith("-L" + str(task["line"])) else []
            task["source_url"] = (
                "https://github.com/" + repo + "/blob/"
                + meta.get("default_branch", "main") + "/" + path + "#L" + str(task["line"])
            )
        counts = Counter(task["status"] for task in tasks)
        summary.append({
            "source": path, "source_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "task_count": len(tasks), "states": dict(sorted(counts.items())),
            "mentioned": sum(bool(t["mentions"]) for t in tasks),
        })
        for task in tasks:
            if task["status"] in ("todo", "doing", "blocked", "unparsed"):
                if len(task_examples) < 12:
                    task_examples.append(task)
    return {
        "repo": repo, "open_issues": len(issues), "sources": summary,
        "totals": dict(sorted(Counter(
            status for record in summary for status, count in record["states"].items()
            for _ in range(count)
        ).items())),
        "examples": task_examples,
        "warning": "Mentions indicate possible Issue links, not verified task ownership. Read-only.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", choices=sorted(PUBLIC_SOURCES), help="Scan one public repository")
    parser.add_argument("--all", action="store_true", help="Scan every allowlisted public repository")
    args = parser.parse_args(argv)
    if not args.all and not args.repo:
        parser.error("use --repo or --all")
    results = []
    try:
        for repo in (sorted(PUBLIC_SOURCES) if args.all else [args.repo]):
            results.append(scan(repo))
    except InventoryError as e:
        print("INVENTORY_DENIED: " + str(e), file=sys.stderr)
        return 2
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
