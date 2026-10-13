#!/usr/bin/env python3
"""Controlled STAR pilot for a synthetic GitHub draft PR. No code executor."""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from issue_lease import Lease, Denied
import issue_preflight as preflight

REPO = "memolabs-dev/.github"
SOURCE = "docs/automation-architecture.md"
MARKER = "STAR_PILOT_FIXTURE_V1"
BRANCH_PREFIX = "pilot/star-fixture-"
FILE_PREFIX = "docs/automation/pilot-fixtures/"
SHA = re.compile(r"^[a-f0-9]{40}$")
WORKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")

class PilotDenied(Exception):
    pass

class Github:
    def request(self, verb, path, body=None, optional=False):
        cmd = ["gh", "api", "-X", verb, path]
        if body is not None:
            cmd += ["--input", "-"]
        p = subprocess.run(cmd, input=json.dumps(body) if body is not None else None,
                           capture_output=True, text=True, timeout=35)
        if p.returncode:
            if optional and "HTTP 404" in p.stderr:
                return None
            raise PilotDenied("GitHub API failure; manual reconciliation required")
        try:
            obj = json.loads(p.stdout)
            if not isinstance(obj, dict):
                raise ValueError("not an object")
            return obj
        except ValueError:
            raise PilotDenied("Invalid GitHub response") from None

    def issue(self, n):
        return self.request("GET", "repos/" + REPO + "/issues/" + str(n))

    def main(self):
        return self.request("GET", "repos/" + REPO + "/git/ref/heads/main")["object"]["sha"]

    def source(self, sha):
        return self.request("GET", "repos/" + REPO + "/contents/" + SOURCE + "?ref=" + sha)

    def exists(self, branch):
        return self.request("GET", "repos/" + REPO + "/git/ref/heads/" + branch, optional=True) is not None

    def branch(self, branch, main_sha):
        return self.request("POST", "repos/" + REPO + "/git/refs",
                            {"ref": "refs/heads/" + branch, "sha": main_sha})

    def file(self, path, branch, data):
        return self.request("PUT", "repos/" + REPO + "/contents/" + path,
                            {"message": "test(star): synthetic pilot evidence",
                             "branch": branch, "content": base64.b64encode(data.encode()).decode()})

    def draft(self, branch, num, base, fence):
        body = ("Synthetic STAR fixture from issue #" + str(num) +
                ". Base SHA " + base + "; lease fence " + fence +
                ". No source code executed; DO NOT MERGE or deploy.")
        return self.request("POST", "repos/" + REPO + "/pulls",
                            {"title": "test(star): Issue #" + str(num) + " pilot receipt",
                             "head": branch, "base": "main", "draft": True, "body": body})

def stage(data):
    with tempfile.TemporaryDirectory(prefix="star-pilot-") as folder:
        path = Path(folder) / "receipt.json"
        data_string = json.dumps(data, indent=2, sort_keys=True) + "\n"
        path.write_text(data_string, encoding="utf-8")
        if json.loads(path.read_text(encoding="utf-8")) != data:
            raise PilotDenied("Staging JSON validation failed")
        return data_string, hashlib.sha256(path.read_bytes()).hexdigest()

class Pilot:
    def __init__(self, api=None, lease=None):
        self.api = api if api is not None else Github()
        self.lease = lease if lease is not None else Lease()

    def guard(self, number, worker, claim):
        return self.lease.verify(REPO, number, worker, claim["claim_id"], claim["fence_sha"])

    def run(self, number, worker, publish=False):
        number = preflight.checked_number(number)
        if not WORKER.fullmatch(worker):
            raise PilotDenied("Invalid worker name")
        issue = self.api.issue(number)
        expected = "https://github.com/" + REPO + "/issues/" + str(number)
        if issue.get("html_url") != expected or issue.get("state") != "open" or "pull_request" in issue:
            raise PilotDenied("Not the expected open fixture Issue")
        # Only the standalone opt-in marker is parsed; raw Issue text is never executed.
        body = issue.get("body")
        if not isinstance(body, str) or MARKER not in body.splitlines():
            raise PilotDenied("Explicit synthetic fixture marker missing")
        branch = BRANCH_PREFIX + str(number)
        filename = FILE_PREFIX + "issue-" + str(number) + ".json"
        if self.api.exists(branch):
            raise PilotDenied("Existing pilot branch; manual reconciliation required")
        claim = self.lease.claim(REPO, number, worker, 300)
        outcome = "blocked"
        try:
            self.guard(number, worker, claim)
            main_sha = self.api.main()
            source = self.api.source(main_sha)
            if not SHA.fullmatch(main_sha) or source.get("type") != "file" or not SHA.fullmatch(source.get("sha", "")):
                raise PilotDenied("Pinned source not verified")
            receipt = {
                "kind": "MEMO_STAR_PILOT_FIXTURE_V1", "issue": expected,
                "source_path": SOURCE, "source_blob_sha": source["sha"],
                "base_sha": main_sha, "lease_ref": claim["reference"],
                "epoch": claim["epoch"], "claim_id": claim["claim_id"],
                "fence_sha": claim["fence_sha"],
                "test_result": "PASS: disposable JSON round-trip",
                "task_code_executed": False, "product_modified": False,
                "deployment_performed": False
            }
            content, digest = stage(receipt)
            result = {
                "issue": expected, "branch": branch, "file": filename,
                "receipt_sha256": digest, "base_sha": main_sha,
                "source_sha": source["sha"], "epoch": claim["epoch"],
                "published": False, "draft_pr": None, "task_code_executed": False
            }
            self.guard(number, worker, claim)
            if publish:
                # Cooperative guards: external operations are not atomic with the lease.
                self.api.branch(branch, main_sha)
                self.guard(number, worker, claim)
                self.api.file(filename, branch, content)
                self.guard(number, worker, claim)
                pr = self.api.draft(branch, number, main_sha, claim["fence_sha"])
                url = pr.get("html_url", "")
                if pr.get("draft") is not True or not isinstance(url, str) or not url.startswith(
                        "https://github.com/" + REPO + "/pull/"):
                    raise PilotDenied("Draft PR publication uncertain")
                result.update({"published": True, "draft_pr": url})
            outcome = "completed"
            return result
        finally:
            # If the release cannot be confirmed, do not report success.
            try:
                self.lease.release(REPO, number, worker, claim["claim_id"], claim["fence_sha"], outcome)
            except (Denied, preflight.PreflightDenied) as exc:
                raise PilotDenied("Lease release cannot be confirmed") from exc

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--publish-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = Pilot().run(args.issue, args.worker, args.publish_fixture)
    except (Denied, PilotDenied, preflight.PreflightDenied) as exc:
        print("STAR_PILOT_DENIED: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
