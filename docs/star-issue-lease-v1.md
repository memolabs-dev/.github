# GitHub STAR Issue lease v1

**Owner: Memo Coordinator.** Memo Bridge serves this ledger to every AI client (`memolabs-dev/memo-bridge`, `docs/COORDINATOR.md`) and its CI runs the script from this repository's `main`. Changes must keep the CLI, the JSON receipts and the `LEASE_DENIED` messages backward compatible.

**Scope:** public Issues from the preflight allowlist only, in `memolabs-dev/.github`. GitHub Projects remains separate.

- Map each `owner/repo#issue` to an immutable-name branch `refs/heads/star-lease-v1/<sha256>` in the public governance repository. Private Issue metadata is **not allowed** here.
- `claim`: validate Issue state/priority/`agent:ready` and absence of blocked/human/epic/working labels; create a no-file-change Git commit with opaque lease ID, worker ID, expiration and source digest. Create ref atomically. Concurrent ref creation is exclusive.
- Existing ref: read last lease commit. Active claims deny a second worker. Released or expired claims append a child commit and advance ref `force=false`; two sibling updates cannot both fast-forward. Every subsequent update also rotates the `fence_sha`.
- `heartbeat`: verify ownership, current SHA and unchanged Issue metadata; advance the ref with new expiration. `verify`: deny a stale fence or expired claim. `release`: durable audit record; **never closes the Issue or deploys**.
- Use `claim`, `verify`, `heartbeat`, `release`, `status` CLI subcommands manually. `status` also returns the public owner fields (`worker`, `claim_id`, `expires_at`) recorded in the lease commit, so a client that lost the outcome of a write can recover its own claim. All require scoped GitHub permissions; no agent executor is provided. Refs persist and are never force-pushed or deleted by this script.
- **Guardrails**: non-atomic external writes after a successful verify are not protected solely by this protocol. A future worker must pass a fencing token at every side-effect boundary; a hostile/uncooperative worker can bypass this ledger. Wall-clock skew, GitHub outages, race after preflight, conflicts and sticky refs require explicit operational policy and cross-host tests before enabling automated dispatch.
- **Security**: Issue content is untrusted and never turned into shell instructions. No secrets, private Issue titles or bodies in Git commits. GitHub App write scopes remain tightly constrained.
- No rule, PR, release, issue label, worker schedule or production change is activated by this branch.

Part of [#26](https://github.com/memolabs-dev/.github/issues/26); depends on [STAR preflight PR #31](https://github.com/memolabs-dev/.github/pull/31).
