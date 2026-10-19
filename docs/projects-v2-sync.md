# GitHub Projects V2 sync — Memo Labs

Source of truth: existing GitHub Issues. GitHub Projects provides portfolio
views only; technical specs and ADRs stay versioned with repository code.

Org board: https://github.com/orgs/memolabs-dev/projects/2
Private organization project node ID: PVT_kwDOFFp4LM4BnzMe
Baseline on 2026-10-19: 99 open Issues were imported from 9 org repositories.
The 99 count is a verified snapshot, NOT a continuously synchronized guarantee.

Personal board: https://github.com/users/guillaume-flambard/projects/2
Baseline: 22 open Issues in lab-infra, kollio and foldready.
Personal Project must first have its actual PVT_ ID verified.

DRY RUN (no mutations):
    python3 scripts/projects_sync.py --org memolabs-dev --project-id PVT_kwDOFFp4LM4BnzMe

Apply only after reviewing the dry-run count:
    python3 scripts/projects_sync.py --org memolabs-dev --project-id PVT_kwDOFFp4LM4BnzMe --apply --max-add 100

Personal Project: repeat --repo for guillaume-flambard/lab-infra,
guillaume-flambard/kollio, and guillaume-flambard/foldready, then pass
the verified personal Project ID. Never mix owners.

Requires an authenticated gh CLI with read access to each selected repo and
write access to the private Project. Repeatable: existing items are not added
twice, and existing item status/priority is never changed. No new Issues,
leases, agent dispatch, auto-merge or deployment are triggered.
Archived repositories and PRs are excluded. API errors fail closed.

Important: no recurring schedule has been activated. Before automation,
configure an appropriately restricted token or GitHub App with Projects v2
write access; Actions GITHUB_TOKEN alone cannot update the organization board.
Run a successful live dry run, an apply, and a second idempotence check.
Keep Memo Labs OS Project #1 as the separate agent Coordinator view.
