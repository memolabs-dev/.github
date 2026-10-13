# Matrice de migration — GitHub Apps Memo Labs

Données observées le 13 octobre 2026 via `gh repo list` et `gh workflow list`. La présence d'un workflow ne prouve pas son succès.

| Dépôt | Privé | Automation | Guardian | Particularité / risque |
| --- | --- | --- | --- | --- |
| `.github` | non | installé, smoke lecture + PR réussi | NON INSTALLÉ | Dépôt de gouvernance |
| `cuesheet` | non | installé, PR #57 + CI réussie, allowlist #58 fusionnée | non | Ne pas retirer l'ancien bot avant migration des agents |
| `uni-protocol` | non | à migrer | après pilote CUESHEET | CI d'identité, contrat probatoire |
| `problem-intelligence-engine` | non | à migrer | après UNI | Source et assertions indépendantes |
| `drop` | non | à migrer | après pilotes | Apple signing, release, CodeQL, zizmor, Scorecard |
| `lab-hub` | non | à migrer | après pilotes | GHCR n'est pas production |
| `kollio-v3` | **oui** | sélection explicite requise | option, à justifier | Code privé, tests natifs |
| `emargo` | **oui** | sélection explicite requise | option, à justifier | Client/projet privé |
| `lab-console` | **oui** | en dernier | option, à justifier | Opérations sensibles |

## Procédure par dépôt

1. Relever owner, visibility, règles de branche, CI exigée, secrets utilisés, workflow auto-merge et consommateurs de jetons.
2. Ajouter **seulement ce dépôt** à l'installation GitHub App depuis l'interface d'administration si le CLI n'a pas le droit de modifier l'installation.
3. Mint un jeton d'installation limité au dépôt. Smoke : création de PR **draft non exécutée en production**.
4. Constater identité réelle `memo-labs-automation[bot]`, tests, règle `hold-merge`.
5. Faire évoluer l'allowlist d'auteurs par PR ; CI obligatoire ; auto-merge n'est jamais une revue humaine.
6. Migrer les applications/agents qui utilisent les anciens PAT, en prouvant chaque chemin d'accès.
7. Archiver le verdict, rollback et source dans ce dépôt.
8. Révoquer les anciens tokens **uniquement une fois tous les consommateurs identifiés et migrés**.

## Garde-fous

- `memo-labs-guardian` ne doit pas utiliser les secrets `MEMOLABS_APP_*` d'Automation.
- Éviter `All repositories` par défaut et installer explicitement sur les dépôts privés.
- Ne pas copier des clés PEM dans un dossier Git ni dans un check-run output.
- Ne pas confondre `gh` connecté comme utilisateur et GitHub App utilisant un token d'installation.
- Ne pas déclencher de release ni déploiement lors du smoke de migration.
