import importlib.util
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "uni_receipt_export", ROOT / "scripts/export-uni-governance-receipt.py"
)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
SHA = "b" * 40
DIGEST = "a" * 64


def valid_decision():
    return {
        "decision": "Accepted", "commit": SHA, "assurance": "A2",
        "identity_assurance": "SELF-DECLARED", "independent_actor": False,
        "intent": {"id": "memolabs.governance"},
        "claims": [{"claim_id": "governance-tests", "required": True, "state": "Valid"}],
        "stale": {},
    }


def create_receipt(decision, **updates):
    kwargs = dict(
        sha=SHA, run_id="1234567", repository="memolabs-dev/.github",
        contract_digest=DIGEST, registry_digest=DIGEST
    )
    kwargs.update(updates)
    return exporter.build_receipt(decision, **kwargs)


class GovernanceReceiptTests(TestCase):
    def test_minimal_receipt_is_sha_bound_and_never_independent(self):
        receipt = create_receipt(valid_decision())
        self.assertEqual(receipt["commit_sha"], SHA)
        self.assertEqual(receipt["uni_decision"], "Accepted")
        self.assertFalse(receipt["guardian_independent_verification"])
        self.assertFalse(receipt["independent_actor"])
        self.assertFalse(receipt["certifies_code_quality"])
        self.assertFalse(receipt["can_merge"])
        self.assertEqual(len(receipt["checksum_sha256"]), 64)
        self.assertNotIn("reason", receipt)

    def test_same_evidence_produces_same_checksum(self):
        self.assertEqual(
            create_receipt(valid_decision())["checksum_sha256"],
            create_receipt(valid_decision())["checksum_sha256"]
        )

    def test_stale_commit_fails_closed(self):
        decision = valid_decision()
        decision["commit"] = "c" * 40
        with self.assertRaises(ValueError):
            create_receipt(decision)

    def test_wrong_repository_rejected(self):
        with self.assertRaises(ValueError):
            create_receipt(valid_decision(), repository="elsewhere/private")

    def test_rejected_or_incomplete_decision_rejected(self):
        for state in ("Rejected", "EvidenceRequired", "Escalated"):
            with self.subTest(state=state):
                decision = valid_decision()
                decision["decision"] = state
                with self.assertRaises(ValueError):
                    create_receipt(decision)

    def test_unverified_identity_cannot_be_elevated(self):
        for field, value in (
            ("assurance", "A3"), ("identity_assurance", "VERIFIED"),
            ("independent_actor", True),
        ):
            with self.subTest(field=field):
                decision = valid_decision()
                decision[field] = value
                with self.assertRaises(ValueError):
                    create_receipt(decision)

    def test_absent_duplicate_or_invalid_claim_rejected(self):
        for claims in (
            [], [valid_decision()["claims"][0]] * 2,
            [{"claim_id": "another", "required": True, "state": "Valid"}],
            [{"claim_id": "governance-tests", "required": True, "state": "Missing"}],
        ):
            with self.subTest(claims=claims):
                decision = valid_decision()
                decision["claims"] = claims
                with self.assertRaises(ValueError):
                    create_receipt(decision)

    def test_stale_evidence_rejected(self):
        decision = valid_decision()
        decision["stale"] = {"governance-tests": "old"}
        with self.assertRaises(ValueError):
            create_receipt(decision)

    def test_non_numeric_run_id_rejected(self):
        with self.assertRaises(ValueError):
            create_receipt(valid_decision(), run_id="run_123")
