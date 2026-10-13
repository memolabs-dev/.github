"""No-network tests for GitHub public backlog inventory."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts" / "backlog_inventory.py"
spec = importlib.util.spec_from_file_location("backlog_inventory", path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class BacklogTests(unittest.TestCase):
    def test_checkbox_ids_and_states(self):
        content = "- [ ] H01.1 Implement X\n- [x] H01.2 Test\n- [ ] without ID\n"
        found = tool.parse_checkboxes(content, prefix="LOT-L")
        self.assertEqual([(x["id"], x["status"]) for x in found], [
            ("H01.1", "todo"), ("H01.2", "done"), ("LOT-L3", "todo")])

    def test_drop_multiline_status_and_bad_row(self):
        content = """| T0.7 | Prepare
interview guide (D24) | capability | change | T0.6 | blocked |
| T4.31 | App join | owner | change | T4.23 | doing |
| T4.33 | Broken table
still missing closing status
"""
        found = tool.parse_drop_index(content)
        self.assertEqual([(x["id"], x["status"]) for x in found],
                         [("T0.7", "blocked"), ("T4.31", "doing"), ("T4.33", "unparsed")])

    def test_matching_is_explicit_and_boundaries_work(self):
        issues = [
            {"number": 4, "title": "H01.1 owner", "body": ""},
            {"number": 9, "title": "H01.10 not H01.1", "body": ""},
            {"number": 10, "title": "x", "body": "H01.1\nT4.31"},
        ]
        self.assertEqual(tool.explicit_mentions("H01.1", issues), [4, 9, 10])
        self.assertEqual(tool.explicit_mentions("H01.2", issues), [])
        self.assertEqual(tool.explicit_mentions("T4.31", issues), [10])
        only10 = [{"number": 9, "title": "H01.10", "body": "H01.10"}]
        self.assertEqual(tool.explicit_mentions("H01.1", only10), [])

    def test_denies_non_public_repository_before_api_call(self):
        with self.assertRaises(tool.InventoryError):
            tool.scan("memolabs-dev/emargo", runner=lambda *a, **k: self.fail("API called"))
        with self.assertRaises(tool.InventoryError):
            tool.scan("guillaume-flambard/lab-infra", runner=lambda *a, **k: self.fail("API called"))

    def test_excludes_archive_from_active_lots(self):
        self.assertIsNone(tool.LOT_TASK.match("openspec/changes/archive/l7-studio/tasks.md"))
        self.assertIsNotNone(tool.LOT_TASK.match("openspec/changes/l7-studio/tasks.md"))


if __name__ == "__main__":
    unittest.main()
