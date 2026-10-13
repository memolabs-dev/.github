# memo-labs-guardian — GitHub App, pilote contrôlé

**État** : non créée/non installée au 13 octobre 2026. GitHub CLI opérationnel, mais **enregistrement GitHub App par le propriétaire via la page web** ; l'API de conversion depuis un manifeste exige aussi une étape de consentement navigateur avec un code temporaire.

## Paramètres exacts d'enregistrement

Ouvrir la page préremplie :

[Créer memo-labs-guardian](https://github.com/organizations/memolabs-dev/settings/apps/new?name=memo-labs-guardian&url=https%3A%2F%2Fgithub.com%2Fmemolabs-dev&description=Independent%20evidence%20and%20verification%20checks%20for%20Memo%20Labs&public=false&webhook_active=false&contents=read&pull_requests=read&actions=read&checks=write)

- Nom : `memo-labs-guardian` ; homepage : `https://github.com/memolabs-dev`.
- OAuth / redirect / device flow : **désactivés**, v1 basée sur les jetons d'installation.
- Webhook : **désactivé** pour ce pilote manuel, pas de serveur récepteur nécessaire.
- Installation autorisée : **Only on this account**, organisation `memolabs-dev`.
- Repository permissions : `Contents:read`, `Pull requests:read`, `Actions:read`, `Checks:read & write`, `Metadata:read` (obligatoire).
- Organization / Account / Enterprise permissions : aucune.
- **Ne pas accorder** `Contents:write`, `Actions:write`, `Workflows:write`, `Administration`, `Secrets`, `Deployments`.
- Installer uniquement sur **`memolabs-dev/.github`** ; autoriser CUESHEET ensuite après smoke vert.

## Clé privée et GitHub Actions

Générer une clé `.pem` dans **App settings → Private keys**, la déplacer hors de Downloads vers un coffre local avec accès 0600 ; ne jamais la publier dans Git, dans les logs ni dans ce chat.

Configurer **dans le dépôt** `memolabs-dev/.github` :
- Variable Actions `MEMOLABS_GUARDIAN_CLIENT_ID` (ID client, non secret).
- Secret Actions `MEMOLABS_GUARDIAN_PRIVATE_KEY` (PEM intégral).

Depuis un terminal **ayant accès au PEM**, exemple (adapter chemin et ID) :

```bash
gh variable set MEMOLABS_GUARDIAN_CLIENT_ID --repo memolabs-dev/.github --body 'YOUR_GUARDIAN_CLIENT_ID'
gh secret set MEMOLABS_GUARDIAN_PRIVATE_KEY --repo memolabs-dev/.github < "$HOME/.config/memolabs/secrets/github-app/memo-labs-guardian.private-key.pem"
```

Ne pas inclure la clé comme argument de commande, ni écrire les tokens en console.

## Premier smoke

Déclencher manuellement `.github/workflows/guardian-check-smoke.yml` depuis Actions sur `main`.

Attendu :
1. Le workflow mint un jeton d'installation limité au dépôt `.github` avec uniquement `Contents:read` + `Checks:write`.
2. L'application publie un check `memo-guardian/bootstrap` **NEUTRAL** sur le SHA du workflow.
3. Les logs affichent seulement le nom du check, son URL et sa conclusion ; pas de jeton.
4. Aucun déploiement, branche, PR ni merge n'est créé.

Ce smoke **n'est pas une preuve de qualité** et ne doit pas devenir un required check. Ce n'est qu'après une vraie exécution reproductible de UNI/Aftershock sur un SHA identifié que Guardian pourra publier des verdicts fondés.

## Limites du CLI

- `gh auth status` confirme l'accès au compte utilisateur et aux repos.
- `gh api` peut consulter les installations, les permissions et utiliser la plupart des API GitHub.
- Le flux officiel d'enregistrement passe par le formulaire web ou par un manifeste qui redirige le propriétaire vers GitHub ; **un token CLI classique ne suffit pas pour créer et installer l'app sans cette étape**.
- Un jeton généré pour Automation ne confère pas de capacité de création arbitraire d'une autre app.

Sources :
- https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-using-url-parameters
- https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
- https://docs.github.com/en/rest/checks/runs
- https://github.com/actions/create-github-app-token
