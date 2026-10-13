# Memo Labs — GitHub automation

Gouvernance GitHub de [memolabs-dev](https://github.com/memolabs-dev).

## État réel — 13 octobre 2026

- **memo-labs-automation[bot]** : application GitHub en place ; installation initiale sur `.github` et `cuesheet`, preuve d'écriture et CI vérifiées.
- **memo-labs-guardian** : architecture et manifeste préparés, **application non encore enregistrée**. [Assistant CLI de création](scripts/register-guardian.py) utilisant le flux GitHub officiel avec consentement propriétaire, workflow de preuve préparé mais non exécuté.
- **memo-labs-release** : hypothèse pour une phase ultérieure ; aucune application créée.
- **drop-agent-bot** : compte utilisateur technique maintenu temporairement pour compatibilité, jetons non révoqués.

## Références

- [Architecture cible, répartition des identités et décisions](docs/automation-architecture.md)
- [Guardian : création, permissions minimales et vérification](docs/guardian-app.md)
- [Ordre de migration et critères de sortie](docs/migration-matrix.md)
- [Historique du remplacement de l'ancien bot](docs/github-app-migration.md)

## Tests disponibles

- [Authentification de l'App Automation](.github/workflows/app-auth-smoke.yml)
- [Écriture par l'App Automation](.github/workflows/app-write-smoke.yml)
- [Écriture sur CUESHEET par l'App Automation](.github/workflows/app-cuesheet-smoke.yml)
- [**Guardian : preuve neutre de l'API Checks**](.github/workflows/guardian-check-smoke.yml), **manuel, inactif tant que Guardian n'est pas créé**

**Règle de sécurité :** aucun assistant ni agent ne peut annoncer une validation UNI/Aftershock simplement parce qu'un jeton de GitHub App fonctionne. Les vérifications de fond nécessitent preuves, version exacte du code et conditions d'acceptation indépendantes.
