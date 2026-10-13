"""Safety and provenance contract tests for the real STAR test receipt."""
import copy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import star_receipt as s

def okay():
    return {
        "format":"star-code-receipt/v1","repo":s.REPO,"issue":44,
        "url":"https://github.com/memolabs-dev/.github/issues/44",
        "branch":s.BRANCH,"base_sha":"a"*40,"head_sha":"b"*40,
        "spec_path":s.SPEC,"spec_blob_sha":"c"*40,
        "changed_paths":sorted(s.ALLOWED),"fence":"d"*40,
        "worker":"star-receipt-pilot","claim_id":"e"*32,"epoch":1,
        "tests":{"state":"PASSED","count":32,"exit_code":0,"command":list(s.TEST)},
        "issue_commands_executed":False,"deployed":False
    }

class ReceiptTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(s.validate(okay()))
    def test_issue_and_spec_identity(self):
        for key,value in (("repo","memolabs-dev/emargo"),("issue",45),
                          ("url","https://example.com/issue/44"),
                          ("branch","main"),("spec_path","../private")):
            obj=okay();obj[key]=value
            with self.subTest(key=key),self.assertRaises(s.Denial):s.validate(obj)
    def test_invalid_sha_and_no_actual_commit(self):
        for key,value in (("fence","not-hex"),("head_sha","a"*40),
                          ("spec_blob_sha","invalid"),("base_sha","")):
            obj=okay();obj[key]=value
            with self.subTest(key=key),self.assertRaises(s.Denial):s.validate(obj)
    def test_forbids_other_paths(self):
        for paths in ([],["../../config"],["scripts/star_receipt.py","scripts/star_receipt.py"],
                      ["scripts/star_receipt.py",".github/workflows/deploy.yml"]):
            obj=okay();obj["changed_paths"]=paths
            with self.subTest(paths=paths),self.assertRaises(s.Denial):s.validate(obj)
    def test_forbids_synthetic_test_pass(self):
        for state,count,code in (("PASSED",0,0),("PASSED",None,0),("PASSED",5,1)):
            obj=okay();obj["tests"].update(state=state,count=count,exit_code=code)
            with self.assertRaises(s.Denial):s.validate(obj)
    def test_test_command_cannot_be_from_issue(self):
        obj=okay();obj["tests"]["command"]=["sh","-c","echo injected"]
        with self.assertRaises(s.Denial):s.validate(obj)
    def test_prohibits_issue_execution_and_deploy(self):
        for key in ("issue_commands_executed","deployed"):
            obj=okay();obj[key]=True
            with self.assertRaises(s.Denial):s.validate(obj)
    def test_fixed_runner(self):
        mock=Mock(return_value=subprocess.CompletedProcess([],0,"","Ran 28 tests in 0.006s\nOK"))
        result=s.fixed_tests(Path("/tmp/isolated"),runner=mock)
        self.assertEqual((result["state"],result["count"]),("PASSED",28))
        self.assertEqual(tuple(mock.call_args.args[0]),s.TEST)
        self.assertNotIn("shell",mock.call_args.kwargs)
    def test_does_not_copy_test_log(self):
        mock=Mock(return_value=subprocess.CompletedProcess([],1,"","TOKEN_TEXT\nRan 1 test in 0.006s\nFAILED"))
        result=s.fixed_tests(Path("/tmp/isolated"),runner=mock)
        self.assertEqual(result["state"],"FAILED")
        self.assertNotIn("TOKEN_TEXT",repr(result))
    def test_timeout(self):
        mock=Mock(side_effect=subprocess.TimeoutExpired(["python3"],180))
        self.assertEqual(s.fixed_tests(Path("/tmp"),runner=mock)["state"],"BLOCKED")
    def test_without_count_no_false_pass(self):
        mock=Mock(return_value=subprocess.CompletedProcess([],0,"","OK"))
        self.assertEqual(s.fixed_tests(Path("/tmp"),runner=mock)["state"],"FAILED")
    def test_not_isolated_worktree(self):
        with self.assertRaises(s.Denial):s.inspect(Path("/tmp"))
if __name__=="__main__":unittest.main()
