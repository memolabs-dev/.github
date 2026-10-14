# Migration du compte technique vers une GitHub App

> État : installation pilote réussie (2026-10-13). Application enregistrée, clé en coffre local et secret GitHub Actions, tests d'identité et d'écriture verts. Ancien compte `drop-agent-bot` retiré des auteurs de confiance le 2026-10-14 ([retrait](#retrait-de-drop-agent-bot-14-octobre-2026)). Aucun déploiement modifié.

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

Un compte utilisateur ne peut pas devenir une GitHub App en conservant son type et son identité. L'application créée utilise réellement l'identité `memo-labs-automation[bot]`.

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

## Preuves d'activation (13 octobre 2026)

- App `memo-labs-automation`, installation `170927025`, sélection explicite des dépôts `.github` et `cuesheet`.
- Lecture installation/jeton temporaire : [`Actions #38378857946`](https://github.com/memolabs-dev/.github/actions/runs/38378857946) — **success**.
- Première PR émise par la GitHub App : [`memolabs-dev/.github#1`](https://github.com/memolabs-dev/.github/pull/1), **draft**.
- Accès réel à CUESHEET avec jeton limité : [`Actions #38380373269`](https://github.com/memolabs-dev/.github/actions/runs/38380373269) — **success**.
- PR créée par la GitHub App dans CUESHEET : [`memolabs-dev/cuesheet#57`](https://github.com/memolabs-dev/cuesheet/pull/57), **draft**, tests CI obligatoires réussis ; fusion volontairement désactivée.
- Transition de l'allowlist auto-merge : [`memolabs-dev/cuesheet#58`](https://github.com/memolabs-dev/cuesheet/pull/58) — **fusionnée automatiquement après tests obligatoires verts**. La nouvelle identité est ajoutée **sans retirer** `drop-agent-bot`.
- Emplacement de la clé privée sur le Mac : `~/.config/memolabs/secrets/github-app/memo-labs-automation.private-key.pem` (0600). Aucun secret dans le dépôt.

## Retrait de `drop-agent-bot` (14 octobre 2026)

**Raison.** Le 14 octobre 2026, l'organisation `memolabs-dev` exige une 2FA sécurisée. `drop-agent-bot` ne la satisfait pas et se trouve bloqué : la documentation GitHub indique qu'un membre sans méthode sécurisée est empêché d'accéder aux ressources de l'organisation, mais **reste membre et occupe un siège** ([Requiring two-factor authentication in your organization](https://docs.github.com/en/organizations/keeping-your-organization-secure/managing-two-factor-authentication-for-your-organization/requiring-two-factor-authentication-in-your-organization)). Le compte ne peut donc plus rien produire. Le garder dans les listes de confiance n'apporte rien et laisse une identité de type User, dont les jetons sont longs, capable de faire fusionner une PR si elle était débloquée ou compromise.

**Vérifié avant retrait.** Aucun script ni service du Mac ou du VPS `lab` n'utilise son jeton. La GitHub App `memo-labs-automation[bot]` couvre l'auteur automatisé (preuves ci-dessus).

**Fait dans les dépôts** (branche `chore/retire-drop-agent-bot`, une par dépôt, à fusionner par PR) :
- `memolabs-dev/.github` : `TRUSTED_AUTHORS` de `scripts/land.py` réduit à `guillaume-flambard` et `memo-labs-automation[bot]` ; test de refus `untrusted_author` pour `drop-agent-bot` ; contrat de fusion et ce document mis à jour.
- `memolabs-dev/cuesheet` et `memolabs-dev/uni-protocol` : filtre d'auteur de `.github/workflows/auto-merge.yml` réduit aux deux mêmes identités. Ces fichiers sont sous `.github/`, donc chemins protégés : la fusion reste humaine.

**Reste au propriétaire** (actions de compte, aucune automatisée) :
1. Retirer `drop-agent-bot` de l'organisation : https://github.com/orgs/memolabs-dev/people , cocher `drop-agent-bot`, puis *Remove from organization* ([doc](https://docs.github.com/en/organizations/managing-membership-in-your-organization/removing-a-member-from-your-organization)). Le siège est libéré.
2. Révoquer ses accès en se connectant **en tant que** `drop-agent-bot` :
   - application OAuth GitHub CLI : https://github.com/settings/applications , onglet *Authorized OAuth Apps*, *GitHub CLI*, *Revoke* ([doc](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/reviewing-your-authorized-applications-oauth)) ;
   - jetons personnels : https://github.com/settings/personal-access-tokens (fine-grained) et https://github.com/settings/tokens (classic), *Delete* sur chacun ([doc](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)) ;
   - clés SSH : https://github.com/settings/keys .
   Ou supprimer le compte : https://github.com/settings/admin , *Delete your account* ([doc](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-your-personal-account/deleting-your-personal-account)). La suppression est définitive. La documentation consultée ([Personal account reference](https://docs.github.com/en/account-and-profile/reference/personal-account-reference)) ne précise pas comment s'affichent ensuite les PR et commits que ce compte a rédigés dans les dépôts de l'organisation : si cette attribution compte, révoquer les accès sans supprimer le compte.
3. Sur le Mac, retirer l'entrée locale du trousseau GitHub CLI, encore présente (inactive) au 2026-10-14 : `gh auth logout --hostname github.com --user drop-agent-bot`.
4. Étendre l'installation de la GitHub App aux dépôts actifs : https://github.com/organizations/memolabs-dev/settings/installations , *Configure* sur `memo-labs-automation`, *Repository access*, *Only select repositories*, ajouter les dépôts (au minimum `uni-protocol`, en plus de `.github` et `cuesheet`).

## Basculement progressif (après smoke vert)

1. Ajouter un second dépôt pilote (`cuesheet`) à l'installation de la GitHub App.
2. Configurer l'agent développeur pour obtenir **à la demande** un jeton d'installation (durée ~1 h), avec accès seulement au dépôt requis. Stocker la clé privée dans un coffre, pas dans un dépôt ni sur chaque runner.
3. Ouvrir **une PR non critique** sous la nouvelle identité et vérifier les permissions, la CI, et l'auteur GitHub `memo-labs-automation[bot]`.
4. Adapter les filtres des workflows auto-merge qui autorisent actuellement `drop-agent-bot` ; ne pas retirer l'ancien identifiant avant validation. *Fait le 2026-10-14 (branches `chore/retire-drop-agent-bot`).*
5. Confirmer qu'aucun vieux PAT de `drop-agent-bot` n'est encore utilisé par des outils externes, cron, pipelines, secrets ou déploiements. *Vérifié le 2026-10-14 sur le Mac et le VPS : aucun consommateur.*
6. Étendre l'installation dépôt par dépôt et documenter les permissions réellement utilisées.
7. Révoquer l'ancien jeton **seulement après** validation de tous les consommateurs ; conserver l'ancien compte en lecture si nécessaire pour l'historique. *Consommateurs validés ; révocation à faire par le propriétaire (voir [Retrait](#retrait-de-drop-agent-bot-14-octobre-2026)).*

## Rollback

Tant que l'ancien jeton reste actif et que les workflows n'ont pas été modifiés, il n'y a pas de basculement à annuler.
Après migration, si une application échoue : bloquer l'auto-merge de ses PR, revenir temporairement à l'identité technique précédente uniquement si son jeton est encore légitime et sûr, réparer l'installation/les droits de la nouvelle app, et retester avant nouvelle révocation. Ne jamais rétablir un jeton compromis.

Depuis le 14 octobre 2026, le retour à `drop-agent-bot` n'est plus une voie de rollback : le compte est bloqué par l'exigence de 2FA sécurisée. Si la GitHub App échoue, réparer l'App ; en attendant, `guillaume-flambard` reste un auteur de confiance.

## Sources

- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
- https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app
- https://github.com/actions/create-github-app-token
