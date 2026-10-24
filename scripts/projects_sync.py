#!/usr/bin/env python3
"""Idempotently attach existing open Issues to a private GitHub Project V2."""
import argparse
import json
import re
import subprocess
import sys

class Blocked(RuntimeError):
    pass

def gh(*args, runner=subprocess.run):
    try:
        p = runner(["gh", "api", *args], capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("GitHub CLI unavailable") from None
    if p.returncode:
        raise Blocked("GitHub API denied request (access or rate limit)")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        raise Blocked("GitHub returned invalid JSON") from None
    if isinstance(data, dict) and data.get("errors"):
        raise Blocked("GitHub GraphQL error: " + ",".join(
            sorted({e.get("type", "unknown") for e in data["errors"]})))
    return data

def pages(path, api=gh):
    rows = []
    for page in range(1, 101):
        current = api("-X", "GET", path + ("&" if "?" in path else "?")
                      + "per_page=100&page=" + str(page))
        if not isinstance(current, list):
            raise Blocked("GitHub pagination returned an unexpected response")
        rows.extend(current)
        if len(current) < 100:
            return rows
    raise Blocked("Incomplete GitHub pagination")

def repositories(org=None, names=None, api=gh):
    if org:
        if not re.fullmatch(r"[A-Za-z0-9-]+", org):
            raise Blocked("Invalid organization")
        src = [r for r in pages("orgs/" + org + "/repos?type=all", api)
               if r.get("owner", {}).get("login", "").lower() == org.lower()]
    else:
        if not names:
            raise Blocked("No repository selected")
        src = []
        for name in sorted(set(names)):
            if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name) or ".." in name:
                raise Blocked("Invalid repository selector")
            src.append(api("-X", "GET", "repos/" + name))
    active = []
    for repo in src:
        if repo.get("archived") or repo.get("disabled"):
            continue
        if not isinstance(repo.get("private"), bool) or not repo.get("full_name"):
            raise Blocked("Repository identity/visibility unavailable")
        active.append(repo["full_name"])
    return sorted(set(active))

def issues_for(repos, api=gh):
    items = {}
    for repo in repos:
        for issue in pages("repos/" + repo + "/issues?state=open", api):
            if issue.get("state") != "open" or "pull_request" in issue:
                continue
            node = issue.get("node_id")
            if not isinstance(node, str) or not node:
                raise Blocked("Issue without GitHub node ID")
            items[node] = (repo, issue.get("number"))
    return items

PROJECT_QUERY = """
query($project:ID!, $after:String) {
  node(id:$project) {
    ... on ProjectV2 {
      id title public closed
      owner { ... on Organization {login} ... on User {login} }
      items(first:100,after:$after) {
        nodes {content {... on Issue {id}}}
        pageInfo {hasNextPage endCursor}
      }
    }
  }
}
"""
ADD_QUERY = """
mutation($project:ID!, $issue:ID!) {
  addProjectV2ItemById(input:{projectId:$project,contentId:$issue}) {
    item {id}
  }
}
"""

def gql(query, variables, api=gh):
    params = ["graphql", "-f", "query=" + query]
    for k,v in variables.items():
        if v is not None:
            params.extend(["-f", k + "=" + str(v)])
    result = api(*params)
    if not isinstance(result.get("data"), dict):
        raise Blocked("GraphQL returned no data")
    return result["data"]

def snapshot(project_id, owner, api=gh):
    existing, cursor = set(), None
    for _ in range(100):
        node = gql(PROJECT_QUERY, {"project":project_id, "after":cursor}, api).get("node")
        if not isinstance(node, dict) or node.get("id") != project_id:
            raise Blocked("Project is inaccessible")
        if node.get("public") is not False or node.get("closed") is not False:
            raise Blocked("Project must be private and open")
        if (node.get("owner") or {}).get("login", "").lower() != owner.lower():
            raise Blocked("Project owner mismatch")
        listing = node.get("items")
        if not isinstance(listing, dict):
            raise Blocked("Project items are inaccessible")
        existing.update(item["content"]["id"] for item in (listing.get("nodes") or [])
                        if item and item.get("content") and item["content"].get("id"))
        page = listing.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return node.get("title"), existing
        cursor = page.get("endCursor")
        if not cursor:
            raise Blocked("Project pagination is incomplete")
    raise Blocked("Project items exceed safety bound")

def pending(found, existing):
    return [(node, repo, number)
            for node,(repo,number) in sorted(found.items(),
                 key=lambda item:(item[1][0].lower(),item[1][1]))
            if node not in existing]

def sync(project_id, owner, repos, apply=False, max_add=100, api=gh):
    if not repos:
        raise Blocked("No active repositories")
    title, existing = snapshot(project_id, owner, api)
    issues = issues_for(repos, api)
    missing = pending(issues, existing)
    added = 0
    if apply:
        for node,_,_ in missing[:max_add]:
            data = gql(ADD_QUERY, {"project":project_id, "issue":node}, api)
            if not ((data.get("addProjectV2ItemById") or {}).get("item") or {}).get("id"):
                raise Blocked("Project write did not confirm the new item")
            added += 1
    return {"project":title, "repositories":len(repos), "open_issues":len(issues),
            "linked":len(issues)-len(missing), "missing_before_run":len(missing),
            "added":added, "remaining":len(missing)-added, "applied":apply}

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project-id", required=True)
    s = p.add_mutually_exclusive_group(required=True)
    s.add_argument("--org")
    s.add_argument("--repo", action="append")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--max-add", type=int, default=100)
    a = p.parse_args(argv)
    try:
        if not re.fullmatch(r"PVT_[A-Za-z0-9_-]+", a.project_id):
            raise Blocked("Invalid project ID")
        if not 1 <= a.max_add <= 500:
            raise Blocked("max-add must be within 1..500")
        if a.repo:
            owners = {x.split("/")[0].lower() for x in a.repo}
            if len(owners) != 1:
                raise Blocked("Personal Project must have one repository owner")
            owner = owners.pop()
        else:
            owner = a.org
        receipt = sync(a.project_id, owner, repositories(a.org, a.repo),
                       a.apply, a.max_add)
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except Blocked as exc:
        print("PROJECT_SYNC_BLOCKED: " + str(exc), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
