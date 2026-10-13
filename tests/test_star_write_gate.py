"""Atomic local write gate tests across process boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import star_write_gate as gate

SCRIPT=Path(gate.__file__).resolve()
DIGEST="a"*64
ISSUE=47

class Clock:
    def __init__(self):
        self.value=100000000
    def __call__(self):
        return self.value

class TestWriteGate(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/"local.sqlite3"
        self.clock=Clock()
        self.broker=gate.LocalGate(self.path,clock=self.clock)
        self.token=self.broker.claim(ISSUE,"worker-one",60)

    def put(self, token=None, key="test-rec-01", digest=DIGEST):
        t=token or self.token
        return self.broker.apply(ISSUE,t["worker"],t["nonce"],t["generation"],
                                 key,"record_test_pass",digest)

    def test_commits_one_protected_record(self):
        self.assertTrue(self.put()["committed"])
        self.assertEqual(self.broker.count(ISSUE),1)

    def test_expired_lease_fails_at_commit_even_after_verify(self):
        t=self.token
        self.assertTrue(self.broker.verify(ISSUE,t["worker"],t["nonce"],t["generation"])["valid_now"])
        self.clock.value+=60000
        with self.assertRaisesRegex(gate.Denied,"expired"):
            self.put()
        self.assertEqual(self.broker.count(ISSUE),0)

    def test_superseded_lease_fails_at_commit(self):
        self.clock.value+=60001
        newer=self.broker.claim(ISSUE,"worker-two",60)
        self.assertEqual(newer["generation"],2)
        with self.assertRaises(gate.Denied):
            self.put()
        self.assertTrue(self.put(newer)["committed"])

    def test_release_invalidates_old_claim(self):
        t=self.token
        self.broker.release(ISSUE,t["worker"],t["nonce"],t["generation"])
        with self.assertRaises(gate.Denied):
            self.put()

    def test_idempotent_replay_does_not_duplicate(self):
        self.assertTrue(self.put()["committed"])
        again=self.put()
        self.assertTrue(again["replayed"])
        self.assertFalse(again["committed"])
        self.assertEqual(self.broker.count(ISSUE),1)

    def test_idempotency_key_payload_conflict(self):
        self.put()
        with self.assertRaisesRegex(gate.Denied,"conflicts"):
            self.put(digest="b"*64)
        self.assertEqual(self.broker.count(ISSUE),1)

    def test_reclaimer_does_not_duplicate_previous_result(self):
        self.put()
        self.clock.value+=60001
        fresh=self.broker.claim(ISSUE,"worker-two",60)
        result=self.put(fresh)
        self.assertTrue(result["replayed"])
        self.assertEqual(result["origin_generation"],1)
        self.assertEqual(self.broker.count(ISSUE),1)

    def test_rejects_untrusted_operations(self):
        t=self.token
        for key,kind,digest in (("../secret","record_test_pass",DIGEST),
                                ("valid-key","arbitrary_shell",DIGEST),
                                ("valid-key","record_test_pass","invalid")):
            with self.subTest(key=key,kind=kind):
                with self.assertRaises(gate.Denied):
                    self.broker.apply(ISSUE,t["worker"],t["nonce"],t["generation"],
                                      key,kind,digest)

    def test_rejects_wrong_issue_worker_nonce_generation(self):
        with self.assertRaises(gate.Denied):
            self.broker.claim(48,"worker-two")
        with self.assertRaises(gate.Denied):
            self.broker.claim(ISSUE,"$(whoami)")
        with self.assertRaises(gate.Denied):
            self.broker.apply(ISSUE,"worker-one","bad",1,
                              "valid-key","record_test_pass",DIGEST)

    def test_two_independent_processes_exactly_once(self):
        # Cross-process actors share the real wall-clock broker, not our fake clock.
        active_path=Path(self.folder.name)/"effects-real.sqlite3"
        active=gate.LocalGate(active_path)
        t=active.claim(ISSUE,"worker-one",60)
        cmd=[sys.executable,str(SCRIPT),"--db",str(active_path),"apply",
             "--issue",str(ISSUE),"--worker",t["worker"],"--nonce",t["nonce"],
             "--generation",str(t["generation"]),"--key","process-race-key",
             "--kind","record_test_pass","--digest",DIGEST]
        procs=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
               for _ in range(2)]
        results=[proc.communicate(timeout=30) for proc in procs]
        self.assertEqual([proc.returncode for proc in procs],[0,0],results)
        receipts=[json.loads(row[0]) for row in results]
        self.assertEqual(sum(row["committed"] for row in receipts),1)
        self.assertEqual(sum(row["replayed"] for row in receipts),1)
        self.assertEqual(active.count(ISSUE),1)

    def test_independent_processes_compete_for_released_claim(self):
        # Use real wall time in subprocesses; fake test clock not shared.
        other=Path(self.folder.name)/"multi.sqlite3"
        active=gate.LocalGate(other)
        initial=active.claim(ISSUE,"worker-one",60)
        active.release(ISSUE,initial["worker"],initial["nonce"],initial["generation"])
        commands=[[sys.executable,str(SCRIPT),"--db",str(other),"claim","--issue",
                   str(ISSUE),"--worker",worker,"--ttl","60"]
                  for worker in ("worker-alpha","worker-beta")]
        procs=[subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
               for cmd in commands]
        outputs=[proc.communicate(timeout=30) for proc in procs]
        self.assertEqual(sum(proc.returncode==0 for proc in procs),1,outputs)
        self.assertEqual(sum(proc.returncode==2 for proc in procs),1,outputs)

    def test_expired_worker_is_denied_in_another_process(self):
        # Claim uses past injected clock; child process uses real clock.
        other=Path(self.folder.name)/"expired.sqlite3"
        expired=gate.LocalGate(other,clock=lambda:1000000)
        token=expired.claim(ISSUE,"worker-old",60)
        cmd=[sys.executable,str(SCRIPT),"--db",str(other),"apply","--issue",
             str(ISSUE),"--worker",token["worker"],"--nonce",token["nonce"],
             "--generation",str(token["generation"]),"--key","expired-req",
             "--kind","record_test_pass","--digest",DIGEST]
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
        self.assertEqual(proc.returncode,2)
        self.assertEqual(gate.LocalGate(other).count(ISSUE),0)

if __name__=="__main__":
    unittest.main()
