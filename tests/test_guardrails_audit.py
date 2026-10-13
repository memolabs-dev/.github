import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

MODULE_FILE = Path(__file__).resolve().parents[1] / "scripts/guardrails-audit.py"
SPEC = importlib.util.spec_from_file_location("memo_guardrails", MODULE_FILE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class GovernanceAuditTests(TestCase):
    def test_classic_404_can_coexist_with_enforced_rulesets(self):
        values = [
            {"private": False, "default_branch": "main"},
            None,
            [
                {"name": "main", "enforcement": "active", "target": "branch"},
                {"name": "immutable-tags", "enforcement": "active", "target": "tag"},
            ],
            {"workflows": [{"name": "CI", "state": "active"}]},
        ]
        with patch.object(audit, "read_api", side_effect=values):
            row = audit.repository_report("drop")
        self.assertEqual(row["classic_protection"], "unknown")
        self.assertEqual(len(row["branch_rulesets"]), 1)
        self.assertEqual(row["branch_rulesets"][0]["name"], "main")
        self.assertEqual(len(row["workflow_inventory"]), 1)
        self.assertTrue(any("does not imply" in x for x in row["warnings"]))

    def test_denied_repository_remains_unknown(self):
        with patch.object(audit, "read_api", return_value=None):
            row = audit.repository_report("emargo")
        self.assertEqual(row["visibility"], "unknown")
        self.assertEqual(row["classic_protection"], "unknown")
        self.assertIsNone(row["branch_rulesets"])
        self.assertIsNone(row["required_checks"])
        self.assertTrue(row["warnings"])

    def test_classic_protection_preserves_required_ci(self):
        values = [
            {"private": False, "default_branch": "main"},
            {
                "url": "https://api.github.com/repos/memolabs-dev/cuesheet/branches/main/protection",
                "required_status_checks": {"contexts": ["Core and integration tests"]},
                "required_pull_request_reviews": {"required_approving_review_count": 1},
                "enforce_admins": {"enabled": True},
            },
            [],
            {"workflows": []},
        ]
        with patch.object(audit, "read_api", side_effect=values):
            row = audit.repository_report("cuesheet")
        self.assertEqual(row["classic_protection"], "present")
        self.assertEqual(row["required_checks"], ["Core and integration tests"])
        self.assertEqual(row["minimum_review_approvals"], 1)
        self.assertTrue(row["admins_enforced"])
        self.assertEqual(row["branch_rulesets"], [])

    def test_multiple_issues_sorted_in_input_order(self):
        with patch.object(audit, "repository_report", side_effect=lambda name: {"repo": name}):
            result = audit.inventory(("drop", "cuesheet"))
        self.assertTrue(result["read_only"])
        self.assertEqual(result["repositories"], [{"repo": "drop"}, {"repo": "cuesheet"}])
