# Migration du compte technique vers une GitHub App

> État : préparation (2026-10-13). Aucun secret, aucune permission existante et aucun déploiement n'ont été modifiés.

## Audit vérifié

- Organisation : `memolabs-dev`.
- Ancien compte : `drop-agent-bot` (GitHub `type: User`, non GitHub App).
- Exemples de PR ouvertes par l'ancien compte et fusionnées :
  - `memolabs-dev/cuesheet#36`
  - `memolabs-dev/uni-protocol#16`
  - `memolabs-dev/problem-intelligence-engine#23`
- Les workflows `cuesheet/.github/workflows/auto-merge.yml` et `uni-protocol/.github/workflows/auto-merge.yml` utilisent explicitement `drop-agent-bot` ou `guillaume-flambard` dans leur filtre d'auteur.
- Les workflows CI ordinaires utilisent `GITHUB_TOKEN` et ne dépendent pas nécessairement de ce compte.
- Le workflow `lab-hub/.github/workflows/build.yml` construit et publie une image GHCR. Le déploiement est géré séparément par le VPS.
- La liste d'installations de l'organisation consultée via `gh api /orgs/memolabs-dev/installations` était vide au moment de l'audit.

Un compte utilisateur ne peut pas devenir une GitHub App en conservant son type et son identité. Les nouvelles actions seront signées sous `memo-labs-automation[bot]` si le nom d'app `memo-labs-automation` est disponible.

## Enregistrement (opération de propriétaire, non automatisée)

Créer une **nouvelle** GitHub App dans les paramètres de l'organisation :
https://github.com/organizations/memolabs-dev/settings/apps/new

Configuration prévue :
- Nom : `memo-labs-automation` (ou autre nom libre ; mettre alors à jour les contrôles d'auteur avant migration).
- Homepage : `https://github.com/memolabs-dev`.
- Propriétaire : organisation `memolabs-dev` ; installation autorisée uniquement sur ce compte.
- Webhooks : désactivés (la première version sert à authentifier des outils et workflows, pas à recevoir des événements).
- OAuth utilisateur : non requis ; ne pas activer Request user authorization.
- Permissions de départ : Repository Contents **Read & write**, Pull requests **Read & write**, Issues **Read & write**, Actions **Read-only**. Metadata Read-only est implicite.
- Permission Workflows **Read & write** (si proposée) : **ne pas accorder initialement** ; ajout uniquement après preuve du besoin d'éditer des fichiers `.github/workflows/`, avec revue de sécurité.
- Ne pas demander les permissions d'administration, de gestion des secrets, d'organisation ou des runners.
- Installation : **Selected repositories**, initialement le dépôt `memolabs-dev/.github` uniquement.

Ensuite : onglet **Credentials** de l'application, générer une clé privée (PEM) et la conserver dans un gestionnaire de secrets. Ne jamais l'inclure dans une issue, une PR, des logs ou un message de chat.

## Préparer le smoke test sans afficher les secrets

Dans ce dépôt `memolabs-dev/.github`, configurer :
- Variable GitHub Actions `MEMOLABS_APP_CLIENT_ID` = Client ID de la GitHub App.
- Secret GitHub Actions `MEMOLABS_APP_PRIVATE_KEY` = contenu intégral de la clé privée PEM.

Commande possible depuis une session `gh` connectée à l'organisation, **sur la machine possédant le PEM** :

```bash
gh variable set MEMOLABS_APP_CLIENT_ID --repo memolabs-dev/.github --body 'YOUR_APP_CLIENT_ID'
gh secret set MEMOLABS_APP_PRIVATE_KEY --repo memolabs-dev/.github < /path/to/private-key.pem
```

Ne pas coller de clé privée ni utiliser un argument en ligne de commande contenant sa valeur.

Déclencher manuellement **Verify Memo Labs GitHub App** depuis Actions. Il doit produire un jeton d'installation de courte durée et prouver uniquement l'accès en lecture à ce dépôt. Le test est volontairement incapable de déployer, pousser ou fusionner une PR.

## Basculement progressif (après smoke vert)

1. Ajouter un second dépôt pilote (`cuesheet`) à l'installation de la GitHub App.
2. Configurer l'agent développeur pour obtenir **à la demande** un jeton d'installation (durée ~1 h), avec accès seulement au dépôt requis. Stocker la clé privée dans un coffre, pas dans un dépôt ni sur chaque runner.
3. Ouvrir **une PR non critique** sous la nouvelle identité et vérifier les permissions, la CI, et l'auteur GitHub `memo-labs-automation[bot]`.
4. Adapter les filtres des workflows auto-merge qui autorisent actuellement `drop-agent-bot` ; ne pas retirer l'ancien identifiant avant validation.
5. Confirmer qu'aucun vieux PAT de `drop-agent-bot` n'est encore utilisé par des outils externes, cron, pipelines, secrets ou déploiements.
6. Étendre l'installation dépôt par dépôt et documenter les permissions réellement utilisées.
7. Révoquer l'ancien jeton **seulement après** validation de tous les consommateurs ; conserver l'ancien compte en lecture si nécessaire pour l'historique.

## Rollback

Tant que l'ancien jeton reste actif et que les workflows n'ont pas été modifiés, il n'y a pas de basculement à annuler.
Après migration, si une application échoue : bloquer l'auto-merge de ses PR, revenir temporairement à l'identité technique précédente uniquement si son jeton est encore légitime et sûr, réparer l'installation/les droits de la nouvelle app, et retester avant nouvelle révocation. Ne jamais rétablir un jeton compromis.

## Sources

- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
- https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
- https://github.com/actions/create-github-app-token
