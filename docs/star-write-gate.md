# STAR local write-boundary gate — Issue 47

This is a review-only proof of a transactional gate. It is NOT a deployed autonomous agent or a remote GitHub/VPS writer.

The source in scripts/star_write_gate.py owns two SQLite tables in one file: leases (worker, generation, random nonce, expiration and state) and effects (allowlisted action, idempotency key and SHA-256 content digest). The only authorized pilot Issue is memolabs-dev/.github#47.

Every mutation enters BEGIN IMMEDIATE before checking lease identity and expiry. An evidence INSERT is committed in the same transaction as its validation. An earlier verify is informational only, and cannot authorize a later operation. A released, expired or superseded agent cannot commit a new effect. Replaying the same key and digest leaves only one row; using the key with different content is denied.

Tests in tests/test_star_write_gate.py include real independent subprocesses contending on the same database file for a claim or effect, plus a stale agent that previously verified successfully but expired before its write. All action types are fixed; no Issue text is interpreted as commands.

This controls ONLY broker-owned inert local SQLite evidence rows. It does not fence arbitrary filesystem writes, GitHub branches/PRs, the VPS or any cloud API. The SQLite database currently resides in the test worker's filesystem and the CLI accepts caller-provided worker identifiers; a malicious same-user process could change the DB directly. A deployable system must put this database behind a separately authenticated and permission-isolated broker service, with all remote write tokens held exclusively there.

The existing Git-ref lease protocol from PR 37 is separate. Combining two lease authorities naively would be incorrect. The parent Issue 39 still requires a single trusted claim authority, a dedicated secret-holding writer, crash reconciliation and multi-host authorization proof.

Tests: python3 -m unittest discover -s tests -p test_*.py -v.
PR is stacked on the verified code-receipt PR 45. Do not merge, auto-run or deploy without human review.
