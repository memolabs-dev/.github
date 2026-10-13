#!/usr/bin/env python3
"""Candidate GitHub Git-ref lease for public STAR Issues; never executes tasks."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib,json,re,subprocess,sys,uuid
import issue_preflight as preflight

LEDGER="memolabs-dev/.github"
PREFIX="refs/heads/star-lease-v1/"
MARKER="MEMO_STAR_LEASE_V1\n"
WORKER=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
ID=re.compile(r"^[a-f0-9]{32}$")
SHA=re.compile(r"^[a-f0-9]{40}$")
OUTCOMES=("completed","blocked","failed","cancelled")
class Denied(Exception):pass

def stamp(dt):return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
def date(s):
    try:
        d=datetime.fromisoformat(s)
        if d.tzinfo is None:raise ValueError("missing timezone")
        return d.astimezone(timezone.utc)
    except (ValueError,TypeError):raise Denied("Malformed lease expiration") from None

def ref(repo,n):
    preflight.checked_repo(repo);num=preflight.checked_number(n)
    return PREFIX+hashlib.sha256((repo+"#"+str(num)).encode()).hexdigest()

class Github:
    def req(self,verb,path,body=None):
        args=["gh","api","-X",verb,"-H","Accept: application/vnd.github+json",path]
        if body is not None:args+=["--input","-"]
        p=subprocess.run(args,input=json.dumps(body) if body is not None else None,
                         capture_output=True,text=True,timeout=35)
        if p.returncode:
            if verb=="GET" and "/git/ref/" in path and "HTTP 404" in p.stderr:return None
            raise Denied("GitHub API operation failed; do not proceed")
        try:return json.loads(p.stdout)
        except ValueError:raise Denied("Malformed GitHub response") from None
    def head(self,name):
        item=self.req("GET","repos/"+LEDGER+"/git/ref/"+name.removeprefix("refs/"))
        return item["object"]["sha"] if item is not None else None
    def commit(self,sha):
        return self.req("GET","repos/"+LEDGER+"/git/commits/"+sha)
    def create_commit(self,parent,msg):
        tree=self.commit(parent)["tree"]["sha"]
        return self.req("POST","repos/"+LEDGER+"/git/commits",
                        {"message":msg,"tree":tree,"parents":[parent]})["sha"]
    def create_ref(self,name,sha):
        self.req("POST","repos/"+LEDGER+"/git/refs",{"ref":name,"sha":sha})
    def advance(self,name,sha):
        self.req("PATCH","repos/"+LEDGER+"/git/refs/"+name.removeprefix("refs/"),
                 {"sha":sha,"force":False})

class Lease:
    def __init__(self,api=None,eligible=None,clock=None,make_id=None):
        self.api=api or Github()
        self.eligible=eligible or preflight.assess
        self.clock=clock or (lambda:datetime.now(timezone.utc))
        self.make_id=make_id or (lambda:uuid.uuid4().hex)
    def current(self,repo,number):
        key=ref(repo,number);head=self.api.head(key)
        if head is None:return key,None,None
        msg=self.api.commit(head).get("message","")
        if not msg.startswith(MARKER):raise Denied("Unknown lease format")
        try:r=json.loads(msg[len(MARKER):])
        except ValueError:raise Denied("Malformed lease record") from None
        if not isinstance(r,dict) or r.get("repo")!=repo or r.get("issue")!=int(number):
            raise Denied("Lease identity mismatch")
        if r.get("state") not in ("claimed","released") or not ID.fullmatch(str(r.get("claim_id",""))):
            raise Denied("Invalid stored lease")
        if type(r.get("epoch"))!=int or r["epoch"]<1:raise Denied("Invalid lease epoch")
        date(r.get("expires_at"));return key,head,r
    def append(self,key,old,r):
        parent=old or self.api.head("refs/heads/main")
        if not SHA.fullmatch(str(parent)):raise Denied("Unverified ledger base SHA")
        new=self.api.create_commit(parent,MARKER+json.dumps(r,sort_keys=True,separators=(",",":")))
        if old is None:self.api.create_ref(key,new)  # atomic ref uniqueness
        else:self.api.advance(key,new)              # non-force sibling conflict
        if self.api.head(key)!=new:raise Denied("Concurrent lease change")
        return new
    def receipt(self,key,sha,r):
        return {"reference":key,"fence_sha":sha,"claim_id":r["claim_id"],"worker":r["worker"],
                "repo":r["repo"],"issue":r["issue"],"epoch":r["epoch"],
                "state":r["state"],"expires_at":r["expires_at"],
                "execution_performed":False,"deployment_performed":False}
    def claim(self,repo,number,worker,ttl=300):
        key=ref(repo,number) # mandatory allowlist even if eligibility injected
        if not WORKER.fullmatch(worker) or not 60<=ttl<=1800:raise Denied("Invalid worker/TTL")
        before=self.eligible(repo,number);now=self.clock()
        key,old,prev=self.current(repo,number)
        if prev and prev["state"]=="claimed" and date(prev["expires_at"])>now:
            raise Denied("Active lease exists")
        nonce=self.make_id()
        if not ID.fullmatch(nonce):raise Denied("Invalid claim ID")
        reason="new" if prev is None else "released_reclaim" if prev["state"]=="released" else "expired_recovery"
        r={"repo":repo,"issue":int(number),"worker":worker,"claim_id":nonce,
           "state":"claimed","epoch":prev["epoch"]+1 if prev else 1,
           "reason":reason,"issued_at":stamp(now),"expires_at":stamp(now+timedelta(seconds=ttl)),
           "issue_updated_at":before["issue_updated_at"],"issue_body_sha256":before["issue_body_sha256"]}
        child=self.append(key,old,r)
        try:
            after=self.eligible(repo,number)
            if (before["issue_updated_at"],before["issue_body_sha256"])!=(
                    after["issue_updated_at"],after["issue_body_sha256"]):
                raise Denied("Issue changed after preflight")
        except Exception:
            try:self.release(repo,number,worker,nonce,child,"cancelled")
            except Exception:pass
            raise Denied("Post-claim preflight failed; execution forbidden") from None
        return self.receipt(key,child,r)
    def status(self,repo,number):
        """Read-only view of the lease. Worker, claim ID and expiry are already public in the
        lease commit; exposing them lets a client recover a claim whose write outcome it lost."""
        key,sha,r=self.current(repo,number)
        if not r:
            return {"reference":key,"fence_sha":None,"state":"unclaimed","epoch":None,"expired":False,
                    "worker":None,"claim_id":None,"expires_at":None}
        return {"reference":key,"fence_sha":sha,"state":r["state"],"epoch":r["epoch"],
                "expired":date(r["expires_at"])<=self.clock() if r["state"]=="claimed" else False,
                "worker":r["worker"],"claim_id":r["claim_id"],"expires_at":r["expires_at"]}
    def owned(self,repo,number,worker,claim_id,fence):
        if not WORKER.fullmatch(worker) or not ID.fullmatch(claim_id) or not SHA.fullmatch(fence):
            raise Denied("Invalid ownership parameters")
        key,sha,r=self.current(repo,number)
        if not r or r["state"]!="claimed" or (r["worker"],r["claim_id"],sha)!=(worker,claim_id,fence):
            raise Denied("Missing or superseded lease")
        if date(r["expires_at"])<=self.clock():raise Denied("Lease expired")
        return key,sha,r
    def verify(self,repo,number,worker,claim_id,fence):
        key,sha,r=self.owned(repo,number,worker,claim_id,fence)
        item=self.eligible(repo,number)
        if (r["issue_updated_at"],r["issue_body_sha256"])!=(
                item["issue_updated_at"],item["issue_body_sha256"]):
            raise Denied("Issue changed since claim")
        return self.receipt(key,sha,r)
    def heartbeat(self,repo,number,worker,claim_id,fence,ttl=300):
        if not 60<=ttl<=1800:raise Denied("Invalid TTL")
        key,sha,r=self.owned(repo,number,worker,claim_id,fence)
        self.verify(repo,number,worker,claim_id,fence)
        now=self.clock()
        new={**r,"last_heartbeat":stamp(now),"expires_at":stamp(now+timedelta(seconds=ttl))}
        return self.receipt(key,self.append(key,sha,new),new)
    def release(self,repo,number,worker,claim_id,fence,outcome):
        if outcome not in OUTCOMES:raise Denied("Invalid outcome")
        key,sha,r=self.owned(repo,number,worker,claim_id,fence)
        new={**r,"state":"released","outcome":outcome,"released_at":stamp(self.clock())}
        return self.receipt(key,self.append(key,sha,new),new)

def cli():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="action",required=True)
    for action in ("claim","verify","heartbeat","release","status"):
        p=sub.add_parser(action);p.add_argument("--repo",required=True);p.add_argument("--issue",required=True)
        if action!="status":p.add_argument("--worker",required=True)
        if action in ("verify","heartbeat","release"):
            p.add_argument("--claim-id",required=True);p.add_argument("--fence",required=True)
        if action in ("claim","heartbeat"):p.add_argument("--ttl",type=int,default=300)
        if action=="release":p.add_argument("--outcome",required=True,choices=OUTCOMES)
    args=parser.parse_args();manager=Lease()
    try:
        if args.action=="status":result=manager.status(args.repo,args.issue)
        elif args.action=="claim":result=manager.claim(args.repo,args.issue,args.worker,args.ttl)
        elif args.action=="verify":result=manager.verify(args.repo,args.issue,args.worker,args.claim_id,args.fence)
        elif args.action=="heartbeat":result=manager.heartbeat(args.repo,args.issue,args.worker,args.claim_id,args.fence,args.ttl)
        else:result=manager.release(args.repo,args.issue,args.worker,args.claim_id,args.fence,args.outcome)
    except (Denied,preflight.PreflightDenied) as e:
        print("LEASE_DENIED: "+str(e),file=sys.stderr);return 2
    print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":sys.exit(cli())
