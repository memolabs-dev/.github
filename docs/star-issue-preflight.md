# GitHub Issue → agent execution : secure preflight pilot

Part of [Issue #26](https://github.com/memolabs-dev/.github/issues/26), building on [Engineering System #24](https://github.com/memolabs-dev/.github/pull/24).

A manually dispatched GitHub Actions workflow validates *one* existing public Issue before a hypothetical agent picks it up. The contract fails closed unless the repository is a `memolabs-dev` repository that GitHub confirms public and not archived (a private one only with the owner's Mac-only enrollment; the per-repository allowlist was replaced by this organization rule on 2026-10-17), the item is an open Issue, exactly one priority is set and `agent:ready` is present without blocked/epic/human/working labels. A JSON receipt pins the Issue's `updated_at`, body SHA-256 and observed eligibility.

`agent:ready` **does not schedule work**. The CLI does not read Issue body as a command and never writes a label, comment, branch or PR. `workflow_dispatch` is manual; the workflow only runs from the governance repo's default branch. `concurrency` serializes dispatches to this *specific workflow*, not other agents. **No durable, cross-run lease is acquired** and the Issue can change immediately after preflight. This is not permission to code, deploy or merge.

Do **not** remove the `lease_acquired: false` receipt or authorize real execution until a separately reviewed lease protocol is implemented and tested across all agent entrypoints. Do not include private repositories in a centralized public Actions preflight: use least-privilege installation tokens and a private execution context in a later milestone.

Test locally with `python3 -m unittest discover -s tests -p "test_issue_preflight.py" -v`. After merge, an authorized owner can run **STAR Issue preflight (manual, read-only)** on an explicitly eligible public Issue from the Actions tab. The current existing production Issues are not auto-enqueued.

Next: transactional claim/lease, explicit worker identity, stale claim recovery, human decisions, receipt → draft PR linkage, dry-run E2E. Tests must show two workers cannot claim simultaneously, not just that Actions has a concurrency key.
