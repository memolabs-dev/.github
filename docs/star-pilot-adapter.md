# STAR pilot adapter — synthetic fixture only

This candidate is stacked on the Git-ref lease PR #37, itself dependent on preflight PR #31. This is NOT a generic task/code executor or unattended service.

## Exact workflow

A human creates a new public governance Issue with a line containing only STAR_PILOT_FIXTURE_V1, labels agent:ready and exactly one priority. The pilot validates that Issue, obtains a Git-ref lease with 5-minute TTL, pins governance main SHA, verifies docs/automation-architecture.md exists at that SHA, builds a synthetic JSON receipt in a disposable temporary directory and validates its roundtrip.

Read-only default:

    python3 scripts/star_pilot.py --issue N --worker pilot-owner

Explicit synthetic publication, after owner review:

    python3 scripts/star_pilot.py --issue N --worker pilot-owner --publish-fixture

Publication writes only the branch pilot/star-fixture-N in memolabs-dev/.github, a JSON file at docs/automation/pilot-fixtures/issue-N.json, and a Draft PR back to main. It does not merge, deploy, run user Issue commands, modify product repositories, or execute any agent-provided code. An existing branch denies replay pending human reconciliation.

## Protections and limits

The adapter checks the lease and Issue state before creating the branch, writing the receipt, and opening the Draft PR. If the fence is lost, subsequent operations stop. A partial write or unknown API outcome leaves the branch for manual reconciliation; automatic retries are not permitted. A non-Draft PR response fails closed. Local unit tests inject failures at different boundaries.

This is COOPERATIVE fencing only. The verification and later GitHub mutation are two independent API requests, not one atomic transaction. A stale worker might act in that gap. The worker ID is manually selected, not cryptographically bound to the GitHub App. No multi-host, timed expiration, crash replay or malicious executor integration has been proven; Issue #39 therefore remains OPEN.

Future worker must authenticate identities, enforce protected-write fencing at the writer, verify source spec/dependencies/commit SHA, use isolated real code worktrees, run actual repository test suites and stage a PR requiring human review. This fixture deliberately does none of that.

## Audit correction — 13 October 2026
An initial live test on fixture #41 produced PR #42. The original preview acquired and released a Git-ref lease, so it was NOT strictly read-only; that claim has been corrected here. The current preview calls eligibility and metadata GETs only and never claims/releases; explicit publication alone uses a Git-ref lease. Fixture #41/#42 remain valid proof of the publication flow, but not evidence of the corrected preview behavior.
