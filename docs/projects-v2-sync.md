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


## Automated reconciliation — gated 2026-10-19

The migration completed with **160 existing open organization Issues** in the PRIVATE Engineering Project; the audit covered **44 active org repositories**. The personal Project now has **22 existing open Issues** (lab-infra 6, kollio 15, foldready 1). Both Projects have the Table view "Toutes les issues" and the Board view "Kanban". No extra Issues were created.

The workflow `.github/workflows/portfolio-projects-sync.yml` is prepared for trusted-main workflow_dispatch (dry-run by default) and a six-hourly schedule gated by **repository variable** `MEMOLABS_PROJECTS_SYNC_ENABLED=true`. The variable must remain disabled until the **Actions secret** `MEMOLABS_PROJECTS_TOKEN` has been provisioned with tightly scoped Project V2 write + repository Issues read. The current `.github` repository has not been verified to possess this secret. Do not export or reuse the developer's macOS gh OAuth token as a long-lived secret. No recurring sync can be claimed as running before the first authenticated successful scheduled execution.

Personal Project automation requires a **separate owner-scoped permission** and must not silently reuse the organization's credential. In the interim, rerun this script with `--repo` for each personal repository and the personal Project ID `PVT_kwHOA2DkXs4Bnzqi`.

Under GitHub Free the built-in auto-add workflow is limited to one per Project and cannot replace this cross-repository reconciliation. Existing project Status and Priorité values are preserved. The March 2026 GitHub GraphQL view API is used for Table and Board views; no separate task database is introduced.
