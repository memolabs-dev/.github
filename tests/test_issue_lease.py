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
    def test_public_allowlist_enforced_even_with_custom_eligibility(self):
        with self.assertRaises(m.preflight.PreflightDenied):
            self.make().claim("memolabs-dev/emargo",44,"pilot-one")
        with self.assertRaises(m.Denied):self.make().claim(REPO,44,"x")
    def test_stale_fence_and_changed_issue(self):
        a=self.make().claim(REPO,44,"pilot-one")
        with self.assertRaises(m.Denied):self.make().verify(REPO,44,"pilot-one",a["claim_id"],"b"*40)
        altered=m.Lease(api=self.store,clock=lambda:self.clock[0],eligible=lambda r,n:{
            "issue_updated_at":"2026-10-13T12:00:01Z","issue_body_sha256":"a"*64})
        with self.assertRaises(m.Denied):altered.verify(REPO,44,"pilot-one",a["claim_id"],a["fence_sha"])
if __name__=="__main__":unittest.main()
