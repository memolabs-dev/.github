#!/usr/bin/env python3
"""Read-only Memo Labs app installation status. Does not inspect credentials."""
import json
import subprocess
import sys

EXPECTED = ("memo-labs-automation", "memo-labs-guardian", "memo-labs-release")


def installations():
    result = subprocess.run(
        ["gh", "api", "/orgs/memolabs-dev/installations"],
        capture_output=True, text=True, timeout=20
    )
    if result.returncode:
        raise RuntimeError("GitHub organization installation inventory could not be read")
    return json.loads(result.stdout)["installations"]


def main():
    found = {item["app_slug"]: item for item in installations()}
    for slug in EXPECTED:
        row = found.get(slug)
        if not row:
            print(f"{slug}: PENDING")
        else:
            print(f"{slug}: INSTALLED / selection={row.get('repository_selection','unknown')}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ERROR:",exc,file=sys.stderr)
        sys.exit(1)
