#!/usr/bin/env python3
"""Atomic local SQLite gate for inert STAR evidence; NOT an external writer."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import time

ISSUE = 47
ACTIONS = frozenset(("record_test_pass", "record_draft_proposal"))
WORKER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{3,79}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Denied(Exception):
    pass


def ident(issue, worker=None, nonce=None, generation=None):
    if type(issue) is not int or issue != ISSUE:
        raise Denied("Only explicit pilot Issue 47 accepted")
    if worker is not None and (not isinstance(worker, str) or not WORKER.fullmatch(worker)):
        raise Denied("Invalid worker name")
    if nonce is not None and (not isinstance(nonce, str) or not HEX64.fullmatch(nonce)):
        raise Denied("Invalid claim nonce")
    if generation is not None and (type(generation) is not int or generation < 1):
        raise Denied("Invalid lease generation")


class LocalGate:
    """Every mutation obtains BEGIN IMMEDIATE before checking lease and writing."""

    def __init__(self, db, clock=None):
        db = Path(db).expanduser().resolve()
        if not db.parent.is_dir():
            raise Denied("Database directory does not exist")
        self.db = str(db)
        self.clock = clock or (lambda: time.time_ns() // 1000000)
        self._init()

    def connection(self):
        db = sqlite3.connect(self.db, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout = 10000")
        return db

    def transaction(self, function):
        with closing(self.connection()) as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                result = function(db)
                db.execute("COMMIT")
                return result
            except BaseException:
                db.execute("ROLLBACK")
                raise

    def _init(self):
        def schema(db):
            db.execute("""CREATE TABLE IF NOT EXISTS lease (
                issue INTEGER PRIMARY KEY,
                generation INTEGER NOT NULL,
                worker TEXT NOT NULL,
                nonce TEXT NOT NULL,
                expires_ms INTEGER NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('active','released'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS effect (
                issue INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                action TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                generation INTEGER NOT NULL,
                committed_ms INTEGER NOT NULL,
                PRIMARY KEY(issue,idempotency_key)
            )""")
        self.transaction(schema)

    def now(self):
        ms = self.clock()
        if type(ms) is not int or ms <= 0:
            raise Denied("Broker clock invalid")
        return ms

    @staticmethod
    def current(db, issue):
        return db.execute("SELECT * FROM lease WHERE issue=?", (issue,)).fetchone()

    def claim(self, issue, worker, ttl=300):
        ident(issue, worker)
        if type(ttl) is not int or not 60 <= ttl <= 1800:
            raise Denied("TTL outside pilot bounds")
        def action(db):
            now = self.now()
            old = self.current(db, issue)
            if old and old["state"] == "active" and now < old["expires_ms"]:
                raise Denied("Existing active lease")
            generation = (old["generation"] + 1) if old else 1
            nonce = secrets.token_hex(32)
            expires = now + ttl * 1000
            db.execute("""INSERT INTO lease(issue,generation,worker,nonce,expires_ms,state)
                VALUES(?,?,?,?,?,'active') ON CONFLICT(issue) DO UPDATE SET
                generation=excluded.generation, worker=excluded.worker,
                nonce=excluded.nonce, expires_ms=excluded.expires_ms, state='active'""",
                (issue, generation, worker, nonce, expires))
            return {"issue":issue,"worker":worker,"nonce":nonce,"generation":generation,
                    "expires_ms":expires}
        return self.transaction(action)

    def require(self, db, issue, worker, nonce, generation, now):
        lease = self.current(db, issue)
        if not lease or lease["state"] != "active":
            raise Denied("Lease not active")
        if (lease["worker"],lease["nonce"],lease["generation"]) != (worker,nonce,generation):
            raise Denied("Stale lease generation or wrong worker")
        if now >= lease["expires_ms"]:
            raise Denied("Lease expired at write boundary")
        return lease

    def verify(self, issue, worker, nonce, generation):
        """Advisory only, never permission for a later write."""
        ident(issue,worker,nonce,generation)
        with closing(self.connection()) as db:
            self.require(db,issue,worker,nonce,generation,self.now())
        return {"valid_now":True,"write_authorized":False}

    def apply(self, issue, worker, nonce, generation, key, action, digest):
        ident(issue,worker,nonce,generation)
        if not isinstance(key,str) or not KEY.fullmatch(key):
            raise Denied("Invalid idempotency key")
        if action not in ACTIONS:
            raise Denied("Operation not in local allowlist")
        if not isinstance(digest,str) or not HEX64.fullmatch(digest):
            raise Denied("Only SHA256 digests are accepted")
        def write(db):
            now = self.now()
            # The check below and the INSERT are in ONE transaction.
            self.require(db,issue,worker,nonce,generation,now)
            old = db.execute("SELECT * FROM effect WHERE issue=? AND idempotency_key=?",
                             (issue,key)).fetchone()
            if old:
                if (old["action"],old["sha256"]) != (action,digest):
                    raise Denied("Replay key conflicts with committed payload")
                return {"committed":False,"replayed":True,"origin_generation":old["generation"]}
            db.execute("""INSERT INTO effect
                (issue,idempotency_key,action,sha256,generation,committed_ms)
                VALUES(?,?,?,?,?,?)""",(issue,key,action,digest,generation,now))
            return {"committed":True,"replayed":False,"origin_generation":generation}
        return self.transaction(write)

    def release(self, issue, worker, nonce, generation):
        ident(issue,worker,nonce,generation)
        def write(db):
            self.require(db,issue,worker,nonce,generation,self.now())
            db.execute("UPDATE lease SET state='released' WHERE issue=?",(issue,))
            return {"released":True,"generation":generation}
        return self.transaction(write)

    def count(self, issue):
        ident(issue)
        with closing(self.connection()) as db:
            return db.execute("SELECT count(*) FROM effect WHERE issue=?",(issue,)).fetchone()[0]


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db",type=Path,required=True)
    sub=ap.add_subparsers(dest="action",required=True)
    for name in ("claim","verify","apply","release","count"):
        p=sub.add_parser(name)
        p.add_argument("--issue",type=int,required=True)
        if name!="count":p.add_argument("--worker",required=True)
        if name in ("verify","apply","release"):
            p.add_argument("--nonce",required=True)
            p.add_argument("--generation",type=int,required=True)
        if name=="claim":p.add_argument("--ttl",type=int,default=300)
        if name=="apply":
            p.add_argument("--key",required=True)
            p.add_argument("--kind",choices=sorted(ACTIONS),required=True)
            p.add_argument("--digest",required=True)
    args=ap.parse_args(argv)
    try:
        gate=LocalGate(args.db)
        if args.action=="claim":result=gate.claim(args.issue,args.worker,args.ttl)
        elif args.action=="verify":result=gate.verify(args.issue,args.worker,args.nonce,args.generation)
        elif args.action=="apply":
            result=gate.apply(args.issue,args.worker,args.nonce,args.generation,
                              args.key,args.kind,args.digest)
        elif args.action=="release":
            result=gate.release(args.issue,args.worker,args.nonce,args.generation)
        else:result={"effects":gate.count(args.issue)}
    except (Denied,sqlite3.Error,OSError) as exc:
        msg=str(exc) if isinstance(exc,Denied) else "Storage unavailable"
        print("WRITE_GATE_DENIED: "+msg,file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
