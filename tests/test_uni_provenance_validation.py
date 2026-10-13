import importlib.util
import json
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uni_provenance_validation", ROOT / "scripts/verify-uni-ci-provenance.py"
)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)

SHA = "b" * 40
RUN = "1234567"
REPO_ID = 1416749183
CONTRACT = b"owner-contract-v1\n"
REGISTRY = b"owner-registry-v1\n"


def fixtures():
    receipt = {
        "schema": validator.SCHEMA,
        "repository": validator.REPOSITORY,
        "commit_sha": SHA,
        "github_actions_run_id": RUN,
        "contract_sha256": validator.digest(CONTRACT),
        "registry_sha256": validator.digest(REGISTRY),
        "uni_decision": "Accepted",
        "claim": "governance-tests",
        "claim_state": "Valid",
        "assurance": "A2",
        "identity_assurance": "SELF-DECLARED",
        "independent_actor": False,
        "guardian_independent_verification": False,
        "certifies_code_quality": False,
        "can_merge": False,
    }
    receipt["checksum_sha256"] = validator.digest(json.dumps(
        receipt, sort_keys=True, separators=(",", ":")
    ).encode())
    run = {
        "id": int(RUN),
        "head_sha": SHA,
        "event": "push",
        "head_branch": "main",
        "path": validator.WORKFLOW_PATH,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": validator.REPOSITORY, "id": REPO_ID},
    }
    artifacts = {
        "total_count": 1,
        "artifacts": [{
            "id": 42,
            "name": "uni-governance-receipt-" + SHA,
            "expired": False,
            "size_in_bytes": 600,
            "workflow_run": {
                "id": int(RUN),
                "head_sha": SHA,
                "repository_id": REPO_ID,
            },
        }]
    }
    return receipt, run, artifacts


def verify(receipt=None, run=None, artifacts=None, contract=CONTRACT, registry=REGISTRY):
    valid_receipt, valid_run, valid_artifacts = fixtures()
    return validator.validate_receipt(
        valid_receipt if receipt is None else receipt,
        valid_run if run is None else run,
        valid_artifacts if artifacts is None else artifacts,
        contract, registry
    )


class CiProvenanceValidationTests(TestCase):
    def test_valid_ci_provenance_does_not_claim_independent_quality(self):
        proof = verify()
        self.assertTrue(proof["ci_provenance_verified"])
        self.assertFalse(proof["guardian_independent_verification"])
        self.assertFalse(proof["quality_certified"])
        self.assertFalse(proof["can_merge"])

    def test_tampered_receipt_checksum_is_rejected(self):
        receipt, _, _ = fixtures()
        receipt["uni_decision"] = "Rejected"
        with self.assertRaises(ValueError):
            verify(receipt=receipt)

    def test_even_consistently_rehashed_independence_claim_is_rejected(self):
        receipt, _, _ = fixtures()
        receipt["guardian_independent_verification"] = True
        payload = {k: v for k, v in receipt.items() if k != "checksum_sha256"}
        receipt["checksum_sha256"] = validator.digest(json.dumps(
            payload, sort_keys=True, separators=(",", ":")
        ).encode())
        with self.assertRaises(ValueError):
            verify(receipt=receipt)

    def test_unknown_receipt_field_is_rejected(self):
        receipt, _, _ = fixtures()
        receipt["raw_logs"] = "not allowed"
        with self.assertRaises(ValueError):
            verify(receipt=receipt)

    def test_replayed_receipt_from_other_sha_is_rejected(self):
        receipt, _, _ = fixtures()
        _, run, _ = fixtures()
        run["head_sha"] = "a" * 40
        with self.assertRaises(ValueError):
            verify(receipt=receipt, run=run)

    def test_untrusted_event_branch_or_workflow_is_rejected(self):
        for key, value in (
            ("event", "pull_request_target"),
            ("head_branch", "feature/untrusted"),
            ("path", ".github/workflows/untrusted.yml"),
            ("conclusion", "failure"),
            ("status", "queued"),
        ):
            with self.subTest(key=key):
                _, run, _ = fixtures()
                run[key] = value
                with self.assertRaises(ValueError):
                    verify(run=run)

    def test_missing_duplicate_or_expired_artifact_rejected(self):
        _, _, originals = fixtures()
        for artifacts in (
            {"total_count": 0, "artifacts": []},
            {"total_count": 2, "artifacts": originals["artifacts"] * 2},
            {"total_count": 2, "artifacts": originals["artifacts"]},
        ):
            with self.subTest(artifacts=artifacts), self.assertRaises(ValueError):
                verify(artifacts=artifacts)
        _, _, expired = fixtures()
        expired["artifacts"][0]["expired"] = True
        with self.assertRaises(ValueError):
            verify(artifacts=expired)

    def test_artifact_not_linked_to_run_is_rejected(self):
        _, _, art = fixtures()
        art["artifacts"][0]["workflow_run"]["id"] = 999
        with self.assertRaises(ValueError):
            verify(artifacts=art)

    def test_source_digest_must_match_git_commit_contents(self):
        with self.assertRaises(ValueError):
            verify(contract=b"modified")
        with self.assertRaises(ValueError):
            verify(registry=b"modified")

    def test_receipt_run_id_must_match_action_run(self):
        receipt, _, _ = fixtures()
        receipt["github_actions_run_id"] = "42"
        with self.assertRaises(ValueError):
            verify(receipt=receipt)
