# GitHub — Canonical repository ownership

Observed 2026-10-26. One logical codebase has **one canonical repository**; an archived snapshot, fork, or distinct product is not a second source of truth.

| Owner | Purpose |
| --- | --- |
| [memolabs-dev](https://github.com/memolabs-dev) | Memo Labs products, shared tools, lab research, libraries, organization infrastructure and collaborative initiatives. |
| [guillaume-flambard](https://github.com/guillaume-flambard) | Developer profile and portfolio, independent personal projects, upstream OSS forks/contributions, prototypes and archives. |

## Mandatory agent rules before creating a GitHub repository

1. Search *both* owners and local PROJECTS.md by project name, aliases, description, remote and stable repository ID; do not create a duplicate. Determine the canonical project and ask for a decision where ownership is ambiguous.
2. Verify GitHub default branch, open PRs, unique commits, remotes, tags/releases, packages/GHCR, Actions, deployment origin, credentials and external consumers before migrating.
3. Preserve independent histories; write an explicit link from any retired repository to the canonical source. **Do not archive, transfer, delete or make public** a repo until non-loss and CI/deployment impact is verified.
4. A fork of external open source should normally remain personal. The individual receives authorship credit for commits to an organization repo, so never mirror an organization repo under a personal account for presentation.
5. Never publish a private repository, private repository inventory or secrets without specific authorization. Documentation of public repositories must not imply production readiness.
6. Keep a versioned, verified public owner inventory here, but consult live GitHub before writes because snapshots age.

## Overlap decisions and exceptions

| Repositories | Relationship / decision | Remaining verification |
| --- | --- | --- |
| [Personal Mediterranean Rescue](https://github.com/guillaume-flambard/mediterranean-rescue) / [Memo Labs Mediterranean Rescue](https://github.com/memolabs-dev/mediterranean-rescue) | Distinct repository IDs and commit heads. Both AGENTS.md files declare the organization as canonical since 2026-10-25. | Reconcile branches and unique changes; confirm the live production deployment reads the org's GHCR image; add legacy notice and archive only after evidence. |
| Archived private personal `lab-hub` / [organization lab-hub](https://github.com/memolabs-dev/lab-hub) | Public maintained organization presence and preserved private personal historical archive. | Do not publish the archived private content. |
| Archived personal `uni` / [UNI Protocol](https://github.com/memolabs-dev/uni-protocol) | Historical implementation and distinct current Rust protocol, not a blind-merge duplicate. | Preserve historical distinction. |
| Personal `kollio` / [Kollio macOS](https://github.com/memolabs-dev/kollio-mac) | Different web and native product scope. | No automatic deletion or transfer. |
| Each owner's `.github` | Owner-specific configuration, intentional. | Preserve both. |

## Portfolio — no mirrors

The [personal portfolio](https://github.com/guillaume-flambard/portfolio) already ingests public repositories from **both accounts** and GitHub PRs sent to external projects, with a scheduled snapshot and cache. Highlight work by editorially linking to its canonical repo, not copying code to a second owner.

The adjacent `repository-ownership-public.json` is a dated observation of visible public organization repositories, not an authoritative live registry and not a list of private work.
