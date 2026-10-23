"""In-memory atomicity tests; real GitHub concurrency is tested separately."""
import hashlib,importlib.util,json,sys,threading,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
root=Path(__file__).resolve().parents[1]/"scripts"
sys.path.insert(0,str(root))
spec=importlib.util.spec_from_file_location("issue_lease",root/"issue_lease.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
REPO="memolabs-dev/.github"
NOW=datetime(2026,10,13,15,0,tzinfo=timezone.utc)

class MemoryGit:
    def __init__(self):
        self.lock=threading.RLock();self.refs={"refs/heads/main":"a"*40};self.seq=0
        self.commits={"a"*40:{"message":"main","tree":{"sha":"e"*40},"parents":[]}}
    def head(self,name):
        with self.lock:return self.refs.get(name)
    def commit(self,sha):
        with self.lock:return self.commits[sha]
    def create_commit(self,parent,msg):
        with self.lock:
            self.seq+=1;sha=hashlib.sha1((str(self.seq)+parent+msg).encode()).hexdigest()
            self.commits[sha]={"message":msg,"tree":{"sha":"e"*40},"parents":[parent]}
            return sha
    def create_ref(self,name,sha):
        with self.lock:
            if name in self.refs:raise m.Denied("ref exists")
            self.refs[name]=sha
    def advance(self,name,sha):
        with self.lock:
            parent=self.commits[sha]["parents"][0]
            if self.refs.get(name)!=parent:raise m.Denied("non fast forward")
            self.refs[name]=sha

def eligible(repo,n):
    if repo!=REPO or int(n)!=44:raise m.Denied("Not eligible")
    return {"issue_updated_at":"2026-10-13T12:00:00Z","issue_body_sha256":"f"*64}

class TestLease(unittest.TestCase):
    def setUp(self):
        self.store=MemoryGit();self.clock=[NOW]
        self.make=lambda:m.Lease(api=self.store,eligible=eligible,clock=lambda:self.clock[0])
    def test_two_parallel_claims_only_one_wins(self):
        start=threading.Event()
        def fn(worker):
            start.wait()
            try:return self.make().claim(REPO,44,worker)
            except m.Denied:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(fn,"pilot-one");b=pool.submit(fn,"pilot-two");start.set();result=[a.result(),b.result()]
        self.assertEqual(sum(item is not None for item in result),1)
    def test_heartbeat_release_and_reclaim(self):
        obj=self.make();a=obj.claim(REPO,44,"pilot-one")
        b=obj.heartbeat(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])
        self.assertNotEqual(a["fence_sha"],b["fence_sha"])
        with self.assertRaises(m.Denied):obj.verify(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])
        obj.verify(REPO,44,"pilot-one",b["claim_id"],b["fence_sha"])
        c=obj.release(REPO,44,"pilot-one",b["claim_id"],b["fence_sha"],"completed")
        self.assertEqual(c["state"],"released")
        self.assertEqual(obj.claim(REPO,44,"pilot-two")["epoch"],2)
    def test_expired_recovery_fences_old_worker(self):
        a=self.make().claim(REPO,44,"pilot-one",60)
        self.clock[0]+=timedelta(seconds=61)
        b=self.make().claim(REPO,44,"pilot-two",60)
        self.assertEqual(b["epoch"],2)
        with self.assertRaises(m.Denied):self.make().verify(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])
    def test_concurrent_sibling_update_conflicts(self):
        obj=self.make();obj.claim(REPO,44,"pilot-one")
        name,parent,record=obj.current(REPO,44)
        x=self.store.create_commit(parent,m.MARKER+json.dumps({**record,"state":"released"}))
        y=self.store.create_commit(parent,m.MARKER+json.dumps({**record,"state":"released","outcome":"failed"}))
        self.store.advance(name,x)
        with self.assertRaises(m.Denied):self.store.advance(name,y)
    def test_org_scope_enforced_even_with_custom_eligibility(self):
        # The repository name check runs before any eligibility function: a repository outside
        # the owner's namespaces is refused. Privacy is checked against GitHub in assess().
        with self.assertRaises(m.preflight.PreflightDenied):
            self.make().claim("someone-else/lab-infra",44,"pilot-one")
        with self.assertRaises(m.Denied):self.make().claim(REPO,44,"x")
    def test_stale_fence_and_changed_issue(self):
        a=self.make().claim(REPO,44,"pilot-one")
        with self.assertRaises(m.Denied):self.make().verify(REPO,44,"pilot-one",a["claim_id"],"b"*40)
        altered=m.Lease(api=self.store,clock=lambda:self.clock[0],eligible=lambda r,n:{
            "issue_updated_at":"2026-10-13T12:00:01Z","issue_body_sha256":"a"*64})
        with self.assertRaises(m.Denied):altered.verify(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])

class TestStatus(unittest.TestCase):
    def setUp(self):
        self.store=MemoryGit();self.clock=[NOW]
        self.lease=m.Lease(api=self.store,eligible=eligible,clock=lambda:self.clock[0])
    def test_status_exposes_the_public_owner_fields_for_recovery(self):
        self.assertEqual(self.lease.status(REPO,44)["state"],"unclaimed")
        a=self.lease.claim(REPO,44,"pilot-one",ttl=60)
        s=self.lease.status(REPO,44)
        self.assertEqual((s["state"],s["worker"],s["claim_id"],s["fence_sha"],s["epoch"],s["expired"]),
                         ("claimed","pilot-one",a["claim_id"],a["fence_sha"],1,False))
        self.clock[0]=NOW+timedelta(seconds=61)
        self.assertTrue(self.lease.status(REPO,44)["expired"])
        self.lease.claim(REPO,44,"pilot-two")
        self.assertEqual(self.lease.status(REPO,44)["worker"],"pilot-two")

class TestHolderChecks(unittest.TestCase):
    def test_comments_and_labels_do_not_break_a_lease_but_a_body_edit_does(self):
        issue={"updated_at":"2026-10-13T12:00:00Z","body":"f"*64}
        def eligible(repo,n):
            if repo!=REPO or int(n)!=44:raise m.Denied("Not eligible")
            return {"issue_updated_at":issue["updated_at"],"issue_body_sha256":issue["body"]}
        store=MemoryGit();lease=m.Lease(api=store,eligible=eligible,clock=lambda:NOW)
        a=lease.claim(REPO,44,"pilot-one")
        issue["updated_at"]="2026-10-13T12:05:00Z"  # a comment or a label
        b=lease.heartbeat(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])
        issue["body"]="0"*64                         # the task itself changed
        with self.assertRaises(m.Denied):lease.verify(REPO,44,"pilot-one",b["claim_id"],b["fence_sha"])

PRIVATE="guillaume-flambard/private-example"
def private_eligible(repo,n):
    if repo!=PRIVATE or int(n)!=7:raise m.Denied("Not eligible")
    return {"issue_updated_at":"2026-10-22T12:00:00Z","issue_body_sha256":"f"*64,"repository_private":True}

KEY=bytes(range(32))
def keyring(repo):return KEY if repo==PRIVATE else None
def keyed(repo,n):return m.keyed_digest(KEY,repo,n)

class TestPrivateRecords(unittest.TestCase):
    """memo-bridge#257: the public ledger never stores a private repository's name or Issue."""
    def setUp(self):
        self.store=MemoryGit();self.clock=[NOW]
        self.lease=m.Lease(api=self.store,eligible=private_eligible,clock=lambda:self.clock[0],keyring=keyring)
    def messages(self):
        return [c["message"] for c in self.store.commits.values() if c["message"].startswith(m.MARKER)]
    def test_private_lifecycle_never_writes_the_identity(self):
        a=self.lease.claim(PRIVATE,7,"pilot-one")
        self.assertEqual((a["repo"],a["issue"]),(PRIVATE,7))  # the local receipt still names it
        b=self.lease.heartbeat(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])
        self.assertEqual(self.lease.verify(PRIVATE,7,"pilot-one",b["claim_id"],b["fence_sha"])["repo"],PRIVATE)
        self.assertEqual(self.lease.status(PRIVATE,7)["state"],"claimed")
        c=self.lease.release(PRIVATE,7,"pilot-one",b["claim_id"],b["fence_sha"],"cancelled")
        self.assertEqual((c["state"],c["issue"]),("released",7))
        self.assertEqual(self.lease.claim(PRIVATE,7,"pilot-two")["epoch"],2)
        self.assertEqual(len(self.messages()),4)
        for msg in self.messages():
            record=json.loads(msg[len(m.MARKER):])
            self.assertNotIn("repo",record);self.assertNotIn("issue",record)
            self.assertEqual(record["subject"],keyed(PRIVATE,7))
            self.assertNotIn("private-example",msg);self.assertNotIn("guillaume-flambard",msg)
    def test_public_records_keep_their_clear_form(self):
        lease=m.Lease(api=self.store,eligible=eligible,clock=lambda:NOW,keyring=keyring)
        lease.claim(REPO,44,"pilot-one")
        record=json.loads(self.messages()[0][len(m.MARKER):])
        self.assertEqual((record["repo"],record["issue"]),(REPO,44));self.assertNotIn("subject",record)
        self.assertIn(m.ref(REPO,44),self.store.refs,"a public ref keeps its unsalted name")
    def test_a_subject_of_another_issue_is_refused(self):
        a=self.lease.claim(PRIVATE,7,"pilot-one")
        key=a["reference"];head=self.store.refs[key]
        record=json.loads(self.store.commits[head]["message"][len(m.MARKER):])
        forged=self.store.create_commit(head,m.MARKER+json.dumps({**record,"subject":keyed(PRIVATE,8)}))
        self.store.advance(key,forged)
        with self.assertRaisesRegex(m.Denied,"identity mismatch"):self.lease.status(PRIVATE,7)
        both=self.store.create_commit(forged,m.MARKER+json.dumps({**record,"repo":PRIVATE,"issue":7}))
        self.store.advance(key,both)
        with self.assertRaisesRegex(m.Denied,"identity mismatch"):self.lease.status(PRIVATE,7)
    def test_a_legacy_clear_private_record_is_redacted_at_its_next_heartbeat(self):
        clear=m.Lease(api=self.store,eligible=lambda r,n:{**private_eligible(r,n),"repository_private":False},
                      clock=lambda:NOW,keyring=lambda r:None)
        a=clear.claim(PRIVATE,7,"pilot-one")   # what the ledger wrote before #257
        self.assertIn(PRIVATE,self.messages()[-1])
        b=self.lease.heartbeat(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])
        last=json.loads(self.messages()[-1][len(m.MARKER):])
        self.assertNotIn("repo",last);self.assertEqual(last["subject"],m.digest(PRIVATE,7))
        self.assertEqual(self.lease.status(PRIVATE,7)["fence_sha"],b["fence_sha"])

class TestKeyedPrivateRefs(unittest.TestCase):
    """Fix pass of memo-bridge#258, finding 3: sha256('<repo>#<n>') is enumerable (small
    sequential Issue numbers), so a private lease's ref name and subject are an HMAC under the
    owner's key, which only the owner's Mac holds; the body digest is keyed too and the Issue's
    update time is not stored."""
    def setUp(self):
        self.store=MemoryGit();self.clock=[NOW]
        self.lease=m.Lease(api=self.store,eligible=private_eligible,clock=lambda:self.clock[0],keyring=keyring)
    def records(self):
        return [json.loads(c["message"][len(m.MARKER):]) for c in self.store.commits.values() if c["message"].startswith(m.MARKER)]
    def test_the_ref_name_cannot_be_enumerated_without_the_key(self):
        a=self.lease.claim(PRIVATE,7,"pilot-one")
        lease_refs=[r for r in self.store.refs if r.startswith(m.PREFIX)]
        self.assertEqual(lease_refs,[m.PREFIX+keyed(PRIVATE,7)]);self.assertEqual(a["reference"],lease_refs[0])
        guesses={m.PREFIX+hashlib.sha256(f"{PRIVATE}#{n}".encode()).hexdigest() for n in range(1,2001)}
        self.assertFalse(guesses & set(self.store.refs),"no unsalted digest of an Issue number names the ref")
        self.assertNotEqual(keyed(PRIVATE,7),m.keyed_digest(bytes(32),PRIVATE,7),"another key gives another name")
    def test_a_private_record_keeps_no_issue_time_and_only_a_keyed_body_digest(self):
        self.lease.claim(PRIVATE,7,"pilot-one")
        record=self.records()[-1]
        self.assertNotIn("issue_updated_at",record)
        self.assertNotEqual(record["issue_body_sha256"],"f"*64)
        self.assertEqual(record["issue_body_sha256"],m.keyed_body(KEY,"f"*64))
    def test_a_body_edit_still_breaks_a_keyed_lease(self):
        body=["f"*64]
        lease=m.Lease(api=self.store,clock=lambda:NOW,keyring=keyring,
                      eligible=lambda r,n:{**private_eligible(r,n),"issue_body_sha256":body[0]})
        a=lease.claim(PRIVATE,7,"pilot-one")
        lease.verify(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])
        body[0]="0"*64
        with self.assertRaisesRegex(m.Denied,"changed"):lease.verify(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])
    def test_a_private_claim_without_the_key_fails_closed(self):
        lease=m.Lease(api=self.store,eligible=private_eligible,clock=lambda:NOW,keyring=lambda r:None)
        with self.assertRaisesRegex(m.Denied,"Owner lease key unavailable"):lease.claim(PRIVATE,7,"pilot-one")
        self.assertEqual([r for r in self.store.refs if r.startswith(m.PREFIX)],[],"nothing written")
        bad=m.Lease(api=self.store,eligible=private_eligible,clock=lambda:NOW,keyring=lambda r:b"short")
        with self.assertRaisesRegex(m.Denied,"Invalid owner lease key"):bad.claim(PRIVATE,7,"pilot-one")
    def legacy(self,worker="pilot-one",ttl=300):
        # A redacted record under the unsalted name, as the ledger wrote it before this fix.
        old=m.Lease(api=self.store,eligible=lambda r,n:{**private_eligible(r,n),"repository_private":False},
                    clock=lambda:self.clock[0],keyring=lambda r:None)
        a=old.claim(PRIVATE,7,worker,ttl)
        return old.heartbeat(PRIVATE,7,worker,a["claim_id"],a["fence_sha"]) if False else a
    def test_a_live_legacy_lease_keeps_working_and_blocks_a_new_claim(self):
        a=self.legacy()
        self.assertEqual(self.lease.status(PRIVATE,7)["claim_id"],a["claim_id"],"the legacy lease is found")
        with self.assertRaisesRegex(m.Denied,"Active lease exists"):self.lease.claim(PRIVATE,7,"pilot-two")
        b=self.lease.heartbeat(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])
        self.assertEqual(b["reference"],m.ref(PRIVATE,7),"the holder stays on its ref")
        self.lease.verify(PRIVATE,7,"pilot-one",b["claim_id"],b["fence_sha"])
        c=self.lease.release(PRIVATE,7,"pilot-one",b["claim_id"],b["fence_sha"],"completed")
        self.assertEqual(c["state"],"released")
        d=self.lease.claim(PRIVATE,7,"pilot-two")
        self.assertEqual((d["reference"],d["epoch"]),(m.PREFIX+keyed(PRIVATE,7),2),"the next lease moves to the keyed name")
        self.assertEqual(self.lease.status(PRIVATE,7)["worker"],"pilot-two")
    def test_an_expired_legacy_lease_is_recovered_under_the_keyed_name(self):
        a=self.legacy(ttl=60)
        self.clock[0]=NOW+timedelta(seconds=61)
        d=self.lease.claim(PRIVATE,7,"pilot-two",60)
        self.assertEqual((d["reference"],d["epoch"]),(m.PREFIX+keyed(PRIVATE,7),2))
        with self.assertRaises(m.Denied):self.lease.verify(PRIVATE,7,"pilot-one",a["claim_id"],a["fence_sha"])

if __name__=="__main__":unittest.main()
