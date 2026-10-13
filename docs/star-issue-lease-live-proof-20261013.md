# GitHub STAR lease v1 — live concurrency acceptance, 13 Oct 2026

Pilot implementation PR: https://github.com/memolabs-dev/.github/pull/37 (stacked on https://github.com/memolabs-dev/.github/pull/31)

## Proof A — initial claim race

Fixture [#36](https://github.com/memolabs-dev/.github/issues/36) was created with explicit `agent:ready` and `priority:p2` and later closed. Two independent Python processes on the connected Mac simultaneously called the GitHub REST claim operation using `gh api`. Outcome: exactly **one** call returned a valid claim; the other returned code 2 (denied). The successful worker verified ownership, renewed the lease (new `fence_sha`), and the old fence failed validation. Release succeeded; a third worker acquired epoch 2 and released it. No task code ran, no deployment occurred and the lease utility did not modify the Issue itself.

## Proof B — concurrent released-lease recovery

Fixture [#38](https://github.com/memolabs-dev/.github/issues/38) was created and later closed. After a bootstrap worker claimed then released the lease, two independent Python processes attempted to claim **the same released ledger ref** simultaneously. Outcome: exactly **one** non-force-fast-forward update succeeded (epoch 2), the competing update returned code 2, and the winner successfully released the epoch-2 claim. Thus uniqueness was confirmed both for initial Git-ref creation and the competing update path.

Both tests were run against **real GitHub REST endpoints**, not only in-memory mocks. The six local contract tests and GitHub PR checks passed. The lease branches persist as immutable-name audit locations; their exact commit SHAs are queryable from the Git ref.

## Interpretations / limits

1. This proves exclusive acquisition with GitHub's ref-creation and fast-forward APIs in the tested conditions. It does **not** prove fail-safe autonomous operation across worker hosts, nor validate external effect fencing at arbitrary integrations.
2. The pilot used the authenticated GitHub CLI on one host. Actors ran as independent processes but shared host network and credential. Multi-host tests and worker authentication hardening are outstanding.
3. An agent must check current `fence_sha` immediately before every protected write, and the writer must enforce that fence. The current script cannot prevent a disobedient agent from acting outside it.
4. Expiry relies on runner clock synchronization; a 60-second simulated expiry was unit-tested, but no live wall-clock expiration takeover was performed.
5. The public governance repository is **never** a place to record private Issue bodies or secrets. Private repos remain outside the allowlist, and the optional GitHub Projects dashboard remains blocked by missing OAuth scope.
6. No feature, runner, workflow dispatch, auto-merge, branch protection or deployment was enabled. Merging the PR installs a CLI utility but does not schedule its execution.

**Acceptance scope:** a tested candidate exclusive claim ledger. **Not complete:** full Issue #26 worker adapter and side-effect gating.
