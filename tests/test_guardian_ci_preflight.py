import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

P = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("guardian_ci_preflight", P / "scripts/guardian-ci-preflight.py")
guardian = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guardian)

SHA = "b" * 40
POLICY = {
    "contract": "memo-guardian/ci-provenance",
    "version": "0.1.0",
    "repository": "memolabs-dev/cuesheet",
    "trusted_check_publisher": "github-actions",
    "required_checks": ["Core and integration tests"],
}


def check(**overrides):
    data = {
        "id": 42,
        "name": "Core and integration tests",
        "head_sha": SHA,
        "status": "completed",
        "conclusion": "success",
        "app": {"slug": "github-actions"},
        "html_url": "https://github.com/memolabs-dev/cuesheet/actions/runs/100/job/42",
    }
    data.update(overrides)
    return data


class GuardianCiGateTests(TestCase):
    def test_exact_trusted_ci_passes_but_is_not_quality_certification(self):
        receipt = guardian.evaluate(POLICY, SHA, [check()], pr_draft=True)
        self.assertEqual(receipt["ci_gate"], "ci_success")
        self.assertFalse(receipt["can_merge"])
        self.assertFalse(receipt["quality_certified"])
        self.assertTrue(receipt["pull_request_is_draft"])
        self.assertEqual(receipt["checks"][0]["check_id"], 42)
        self.assertEqual(len(receipt["receipt_checksum_sha256"]), 64)

    def test_missing_ci_fails_closed(self):
        receipt = guardian.evaluate(POLICY, SHA, [])
        self.assertEqual(receipt["ci_gate"], "incomplete")
        self.assertEqual(receipt["checks"][0]["reason"], "missing_check_for_exact_sha")

    def test_stale_sha_fails_closed(self):
        receipt = guardian.evaluate(POLICY, SHA, [check(head_sha="c" * 40)])
        self.assertEqual(receipt["ci_gate"], "incomplete")

    def test_duplicate_ci_fails_closed(self):
        receipt = guardian.evaluate(POLICY, SHA, [check(), check(id=99)])
        self.assertEqual(receipt["ci_gate"], "incomplete")

    def test_other_app_not_accepted(self):
        receipt = guardian.evaluate(
            POLICY, SHA, [check(app={"slug": "memo-labs-automation"})]
        )
        self.assertEqual(receipt["ci_gate"], "incomplete")
        self.assertEqual(receipt["checks"][0]["reason"], "untrusted_or_unidentifiable_check")

    def test_failed_ci_blocks_without_exposing_secret_data(self):
        receipt = guardian.evaluate(POLICY, SHA, [check(conclusion="failure")])
        self.assertEqual(receipt["ci_gate"], "blocked")
        self.assertFalse(receipt["can_merge"])

    def test_pending_ci_is_not_a_pass(self):
        receipt = guardian.evaluate(
            POLICY, SHA, [check(status="in_progress", conclusion=None)]
        )
        self.assertEqual(receipt["ci_gate"], "incomplete")

    def test_bad_sha_rejected(self):
        with self.assertRaises(ValueError):
            guardian.evaluate(POLICY, "main", [check()])

    def test_sha_and_receipt_are_deterministic(self):
        first = guardian.evaluate(POLICY, SHA, [check()])
        second = guardian.evaluate(POLICY, SHA, [check()])
        self.assertEqual(first["receipt_checksum_sha256"], second["receipt_checksum_sha256"])

    def test_rejects_incomplete_checks_payload(self):
        pr = {
            "base": {"repo": {"full_name": "memolabs-dev/cuesheet"}},
            "head": {"sha": SHA},
            "draft": False,
        }
        checks = {"check_runs": [check()], "total_count": 101}
        with patch.object(guardian, "read_github", side_effect=[pr, checks]):
            with self.assertRaises(RuntimeError):
                guardian.run(57)
