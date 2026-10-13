#!/usr/bin/env python3
"""Read-only GitHub provenance verification of a self-declared UNI receipt.

Checks run identity, artifact association, checksum and exact source-file hashes.
This does NOT certify code quality or create an independent Guardian attestation.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

REPOSITORY = "memolabs-dev/.github"
WORKFLOW_PATH = ".github/workflows/uni-governance.yml"
CONTRACT_PATH = "uni/intents/governance.uni"
REGISTRY_PATH = ".uni/config.toml"
RECEIPT_FILE = "assurance-receipt.json"
SCHEMA = "memo-labs/uni-governance-ci-receipt/v1"

RECEIPT_FIELDS = frozenset((
    "schema", "repository", "commit_sha", "github_actions_run_id",
    "contract_sha256", "registry_sha256", "uni_decision", "claim",
    "claim_state", "assurance", "identity_assurance", "independent_actor",
    "guardian_independent_verification", "certifies_code_quality",
    "can_merge", "checksum_sha256",
))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def github_json(endpoint):
    if not endpoint.startswith("repos/" + REPOSITORY + "/"):
        raise ValueError("Unexpected GitHub API endpoint")
    result = subprocess.run(
        ["gh", "api", endpoint], capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError("Unable to read GitHub API provenance metadata")
    return json.loads(result.stdout)


def github_file_at_sha(path, sha):
    data = github_json(f"repos/{REPOSITORY}/contents/{path}?ref={sha}")
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        raise ValueError("Unable to verify GitHub source file")
    raw = data.get("content")
    if not isinstance(raw, str):
        raise ValueError("Source file has no content")
    return base64.b64decode(raw, validate=False)


def download_receipt(run_id, name):
    with TemporaryDirectory(prefix="memo-guardian-provenance-") as temp:
        cmd = [
            "gh", "run", "download", str(run_id), "-R", REPOSITORY,
            "--name", name, "--dir", temp
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=40
        )
        if result.returncode:
            raise RuntimeError("Failed to fetch UNI receipt artifact")
        path = Path(temp) / RECEIPT_FILE
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 10000:
            raise ValueError("Artifact receipt missing or malformed")
        return json.loads(path.read_text(encoding="utf-8"))


def validate_receipt(receipt, run, artifact_listing, contract_bytes, registry_bytes):
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise ValueError("Unexpected UNI receipt schema/fields")
    expected_checksum = receipt.get("checksum_sha256")
    if not isinstance(expected_checksum, str):
        raise ValueError("Invalid receipt checksum")
    without_checksum = {k: v for k, v in receipt.items() if k != "checksum_sha256"}
    actual = digest(json.dumps(
        without_checksum, sort_keys=True, separators=(",", ":")
    ).encode())
    if actual != expected_checksum:
        raise ValueError("Receipt checksum mismatch")

    sha = receipt["commit_sha"]
    run_id = receipt["github_actions_run_id"]
    if (not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha)
            or not isinstance(run_id, str) or not re.fullmatch("[0-9]{1,20}", run_id)):
        raise ValueError("Invalid run/SHA binding")

    if (receipt["schema"] != SCHEMA or receipt["repository"] != REPOSITORY
            or receipt["uni_decision"] != "Accepted"
            or receipt["claim"] != "governance-tests"
            or receipt["claim_state"] != "Valid"):
        raise ValueError("Unexpected UNI receipt claim")
    if (receipt["assurance"] != "A2"
            or receipt["identity_assurance"] != "SELF-DECLARED"
            or receipt["independent_actor"] is not False
            or receipt["guardian_independent_verification"] is not False
            or receipt["certifies_code_quality"] is not False
            or receipt["can_merge"] is not False):
        raise ValueError("Unjustified Guardian independence or quality claim")

    if (not isinstance(run, dict) or str(run.get("id")) != run_id
            or run.get("head_sha") != sha or run.get("event") != "push"
            or run.get("head_branch") != "main"
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("path") != WORKFLOW_PATH
            or (run.get("repository") or {}).get("full_name") != REPOSITORY):
        raise ValueError("The Actions run does not validate this receipt")

    name = f"uni-governance-receipt-{sha}"
    if (not isinstance(artifact_listing, dict)
            or artifact_listing.get("total_count") != len(artifact_listing.get("artifacts", []))):
        raise ValueError("Artifact list is incomplete")
    matches = [
        a for a in artifact_listing["artifacts"]
        if a.get("name") == name
    ]
    if len(matches) != 1:
        raise ValueError("Expected one unambiguous UNI receipt artifact")
    artifact = matches[0]
    source = artifact.get("workflow_run") or {}
    if (artifact.get("expired") is not False
            or not isinstance(artifact.get("size_in_bytes"), int)
            or artifact["size_in_bytes"] <= 0
            or str(source.get("id")) != run_id
            or source.get("head_sha") != sha
            or source.get("repository_id") != (run.get("repository") or {}).get("id")):
        raise ValueError("Artifact is expired or not tied to the verified run")

    if (receipt["contract_sha256"] != digest(contract_bytes)
            or receipt["registry_sha256"] != digest(registry_bytes)):
        raise ValueError("Owner contract or registry changed relative to receipt")

    return {
        "schema": "memo-labs/uni-ci-provenance-validation/v1",
        "repository": REPOSITORY,
        "head_sha": sha,
        "run_id": run_id,
        "artifact_id": artifact["id"],
        "ci_provenance_verified": True,
        "reported_uni_decision": "Accepted",
        "identity_assurance": "SELF-DECLARED",
        "guardian_independent_verification": False,
        "quality_certified": False,
        "can_merge": False,
        "note": "GitHub Actions metadata and source digests verified; not an independent quality verdict.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch("[0-9]{1,20}", args.run_id):
        parser.error("A numeric GitHub Actions run ID is required")
    base = f"repos/{REPOSITORY}"
    run = github_json(f"{base}/actions/runs/{args.run_id}")
    artifacts = github_json(f"{base}/actions/runs/{args.run_id}/artifacts?per_page=100")
    sha = run.get("head_sha") if isinstance(run, dict) else None
    if not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("Run does not include a valid SHA")
    name = f"uni-governance-receipt-{sha}"
    receipt = download_receipt(args.run_id, name)
    verified = validate_receipt(
        receipt, run, artifacts,
        github_file_at_sha(CONTRACT_PATH, sha),
        github_file_at_sha(REGISTRY_PATH, sha)
    )
    print(json.dumps(verified, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        print("UNI provenance verification failed:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
