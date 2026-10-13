#!/usr/bin/env python3
"""Publish only a minimal, self-declared UNI CI receipt for the checked commit.

This does not establish an independent verifier or a signed attestation.
Used only by the trusted main-only UNI governance workflow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

REPOSITORY = "memolabs-dev/.github"
CLAIM = "governance-tests"
INTENT = "memolabs.governance"
ASSURANCE = "A2"
IDENTITY = "SELF-DECLARED"


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_receipt(decision, *, sha, run_id, repository, contract_digest, registry_digest):
    if repository != REPOSITORY:
        raise ValueError("Unexpected repository")
    if not isinstance(sha, str) or not re.fullmatch("[0-9a-fA-F]{40}", sha):
        raise ValueError("Full Git commit SHA required")
    if not isinstance(run_id, str) or not re.fullmatch("[0-9]{1,20}", run_id):
        raise ValueError("Positive numeric Actions run ID required")
    for digest in (contract_digest, registry_digest):
        if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid source digest")
    if not isinstance(decision, dict):
        raise ValueError("Invalid UNI decision object")
    if not isinstance(decision.get("commit"), str) or decision["commit"].lower() != sha.lower():
        raise ValueError("UNI evidence is not bound to the requested commit")
    if decision.get("decision") != "Accepted":
        raise ValueError("UNI decision is not Accepted")
    if decision.get("assurance") != ASSURANCE:
        raise ValueError("Unexpected assurance level; policy review required")
    if decision.get("identity_assurance") != IDENTITY or decision.get("independent_actor") is not False:
        raise ValueError("Receipt may only describe explicitly self-declared assurance")
    intent = decision.get("intent")
    if not isinstance(intent, dict) or intent.get("id") != INTENT:
        raise ValueError("Wrong UNI intent")
    claims = decision.get("claims")
    if (not isinstance(claims, list) or len(claims) != 1 or
            not isinstance(claims[0], dict) or
            claims[0].get("claim_id") != CLAIM or
            claims[0].get("required") is not True or
            claims[0].get("state") != "Valid"):
        raise ValueError("Required governance claim was not verified")
    if decision.get("stale") not in ({}, None):
        raise ValueError("Stale evidence cannot be published")
    receipt = {
        "schema": "memo-labs/uni-governance-ci-receipt/v1",
        "repository": repository,
        "commit_sha": sha.lower(),
        "github_actions_run_id": run_id,
        "contract_sha256": contract_digest,
        "registry_sha256": registry_digest,
        "uni_decision": "Accepted",
        "claim": CLAIM,
        "claim_state": "Valid",
        "assurance": ASSURANCE,
        "identity_assurance": IDENTITY,
        "independent_actor": False,
        "guardian_independent_verification": False,
        "certifies_code_quality": False,
        "can_merge": False,
    }
    receipt["checksum_sha256"] = hashlib.sha256(
        json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--decision", type=Path, default=Path(".uni/decisions/last.json"))
    parser.add_argument("--contract", type=Path, default=Path("uni/intents/governance.uni"))
    parser.add_argument("--registry", type=Path, default=Path(".uni/config.toml"))
    parser.add_argument("--output", type=Path, default=Path(".uni/artifacts/assurance-receipt.json"))
    args = parser.parse_args()
    expected_sha = os.environ.get("GITHUB_SHA", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_REF", "")
    if branch != "refs/heads/main":
        raise ValueError("Refusing to export a governance receipt outside trusted main")
    decision = json.loads(args.decision.read_text(encoding="utf-8"))
    receipt = build_receipt(
        decision, sha=expected_sha, run_id=run_id,
        repository=repository,
        contract_digest=file_digest(args.contract),
        registry_digest=file_digest(args.registry)
    )
    if args.output.is_symlink():
        raise ValueError("Refusing to overwrite symlinked receipt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("UNI CI receipt created for", expected_sha[:12], "(A2, self-declared; NOT a Guardian verdict)")
    print("Receipt checksum:", receipt["checksum_sha256"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print("UNI receipt export refused:", type(exc).__name__, file=sys.stderr)
        sys.exit(1)
