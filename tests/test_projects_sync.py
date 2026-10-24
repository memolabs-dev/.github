import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock
path = Path(__file__).resolve().parents[1]/"scripts"/"projects_sync.py"
spec = importlib.util.spec_from_file_location("projects_sync",path)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class TestProjectSync(unittest.TestCase):
    def test_idempotent_plan(self):
        found={"A":("org/z",3),"B":("org/a",2),"C":("org/a",1)}
        self.assertEqual(app.pending(found,{"B"}),[("C","org/a",1),("A","org/z",3)])
        self.assertEqual(app.pending(found,set(found)),[])

    def test_reject_public_project(self):
        def api(*args):
            return {"data":{"node":{"id":"PVT_demo","title":"board","public":True,
              "closed":False,"owner":{"login":"org"},
              "items":{"nodes":[],"pageInfo":{"hasNextPage":False}}}}}
        with self.assertRaisesRegex(app.Blocked,"private"):
            app.snapshot("PVT_demo","org",api)

    def test_reject_foreign_project(self):
        def api(*args):
            return {"data":{"node":{"id":"PVT_demo","title":"board","public":False,
              "closed":False,"owner":{"login":"other"},
              "items":{"nodes":[],"pageInfo":{"hasNextPage":False}}}}}
        with self.assertRaisesRegex(app.Blocked,"owner"):
            app.snapshot("PVT_demo","org",api)

    def test_graphql_error_fails_closed(self):
        proc=Mock(return_value=subprocess.CompletedProcess([],0,
                '{"errors":[{"type":"RATE_LIMIT"}]}',""))
        with self.assertRaisesRegex(app.Blocked,"RATE_LIMIT"):
            app.gh("graphql",runner=proc)

    def test_filter_prs_and_closed_issues(self):
        rows=[{"node_id":"I1","number":1,"state":"open"},
              {"node_id":"PR2","number":2,"state":"open","pull_request":{}},
              {"node_id":"I3","number":3,"state":"closed"}]
        self.assertEqual(app.issues_for(["org/demo"],lambda *args:rows),
                         {"I1":("org/demo",1)})

    def test_dry_run_never_writes(self):
        calls=[]
        def api(*args):
            calls.append(args)
            if args[0]=="graphql":
                return {"data":{"node":{"id":"PVT_demo","title":"board","public":False,
                  "closed":False,"owner":{"login":"org"},
                  "items":{"nodes":[],"pageInfo":{"hasNextPage":False}}}}}
            return [{"node_id":"I1","number":1,"state":"open"}]
        receipt=app.sync("PVT_demo","org",["org/demo"],api=api)
        self.assertEqual((receipt["added"],receipt["remaining"]),(0,1))
        self.assertEqual(len([args for args in calls if args[0]=="graphql"]),1)

    def test_ignore_archived_repository(self):
        rows=[{"owner":{"login":"org"},"full_name":"org/demo","private":True},
              {"owner":{"login":"org"},"full_name":"org/old","private":True,"archived":True}]
        self.assertEqual(app.repositories(org="org",api=lambda *args:rows),["org/demo"])

if __name__ == "__main__":
    unittest.main()
