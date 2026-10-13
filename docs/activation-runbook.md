# Activation finale — Memo Labs GitHub Apps

**État : préparé, sans activation des nouvelles identités (13 octobre 2026).**

Cette procédure s'exécute **sur le Mac de l'organisation** où `gh` est déjà connecté. Deux GitHub Apps ne doivent pas être confondues avec des agents IA supplémentaires : ce sont des identités/permissions.

## Étape A — Guardian (P0, à activer en premier)

1. Dans un terminal du clone `memolabs-org-gh`, lancer :

   ```bash
   python3 scripts/register-guardian.py --app guardian --doctor
   python3 scripts/register-guardian.py --app guardian --register
   ```

2. Le programme ouvre GitHub. **Confirmer explicitement la création** par `memolabs-dev`. Ne pas élargir les permissions : Contents read, Pull requests read, Actions read, Checks write, Metadata read implicite.
3. **Installer Guardian uniquement sur `memolabs-dev/.github`** depuis la page qui s'ouvre ; n'autoriser aucun autre dépôt.
4. Le programme doit avoir récupéré la PEM dans `~/.config/memolabs/secrets/github-app/memo-labs-guardian.private-key.pem` (0600) et créé la variable/secret `MEMOLABS_GUARDIAN_CLIENT_ID` et `MEMOLABS_GUARDIAN_PRIVATE_KEY`. Aucun secret dans le dépôt.
5. Vérifier avec `python3 scripts/register-guardian.py --app guardian --verify` puis regarder [Actions](https://github.com/memolabs-dev/.github/actions). Attendu : `memo-guardian/bootstrap`, conclusion **neutral**, jamais `success` prétendant attester le code.
6. **Ne pas rendre ce check obligatoire pour fusionner** avant intégration d'un vrai vérificateur UNI/Aftershock.

En cas d'échec de récupération PEM après la création, ne pas recommencer aveuglément : retrouver l'application créée dans GitHub et utiliser `Private keys` pour générer une nouvelle clé, puis suivre la configuration manuelle documentée dans [guardian-app.md](guardian-app.md). Ne jamais partager la clé dans le chat.

## Étape B — Release (P3, option approuvée séparément)

L'architecture Release a été **préparée**, mais **pas encore approuvée pour la production**. Cette identité a des droits élevés : `Contents:write`, `Deployments:write`, `Actions:read`. Vérifier que la séparation apporte une valeur réelle par rapport aux workflows déjà présents.

**Si validation explicite**, faire :

```bash
python3 scripts/register-guardian.py --app release --doctor
python3 scripts/register-guardian.py --app release --register
```

Confirmer sa création puis **l'installer uniquement sur `memolabs-dev/drop`** pour le pilote. La clé sera rangée sous `memo-labs-release.private-key.pem` et les noms Actions seront `MEMOLABS_RELEASE_CLIENT_ID` / `MEMOLABS_RELEASE_PRIVATE_KEY`. Le dépôt `.github` contient un workflow manuel de vérification qui ne demande qu'un jeton **read-only sur Drop** :

```bash
python3 scripts/register-guardian.py --app release --verify
```

Ce test ne crée **aucune release** et ne déclenche **aucun déploiement**. Avant d'autoriser une publication, imposer revue humaine, vérification de signature/artefacts, protections des environnements et plan de rollback.

## Étape C — Relier Automation aux dépôts (P1)

Aujourd'hui : `memo-labs-automation` est installée sur `.github` et `cuesheet` ; CUESHEET a été validé et son auto-merge accepte l'App ainsi que l'ancien bot.

Dans [GitHub → Installations de memolabs-dev](https://github.com/organizations/memolabs-dev/settings/installations) :

1. Ouvrir l'installation `memo-labs-automation` et **ajouter explicitement** le dépôt pilote souhaité, sans sélectionner `All repositories`.
2. Après l'installation, déclencher **uniquement une vérification read-only** via [app-repo-access-smoke.yml](../.github/workflows/app-repo-access-smoke.yml) ou :

   ```bash
   python3 scripts/post-activation.py --repos uni-protocol problem-intelligence-engine drop lab-hub
   # Re-vérifier la sélection dans GitHub, puis déclencher explicitement :
   python3 scripts/post-activation.py --repos uni-protocol problem-intelligence-engine drop lab-hub --execute
   ```

3. Lire le résultat des workflows dans GitHub Actions. Un échec signifie souvent que l'application n'est pas installée sur ce dépôt.
4. Quand la lecture fonctionne, faire une PR **draft non critique** avec l'identité d'App, vérifier CI/ruleset/protection puis, seulement ensuite, modifier une éventuelle allowlist d'auteurs par PR.
5. Pour les dépôts privés `kollio-v3`, `emargo`, `lab-console` : validation d'accès individuelle, **jamais automatique**.
6. Ancienne identité `drop-agent-bot` : aucun PAT révoqué tant que tous les consommateurs Mac/VPS/IDE/CI n'ont pas été testés.

## Étape D — Fonctions du Lab sans nouvelle App

- **Radar v0** : `python3 scripts/radar.py` ; lit le dernier workflow par dépôt. Les déploiements restent **unknown** sans preuve réelle.
- **Steward v0** : `python3 scripts/steward.py --days 14` ; ne fait que signaler les PR ouvertes et anciennes. Aucune clôture, fusion ni suppression. Le pilotage automatisé par PR reste au backlog #19.
- **Scout** : backlog #20 ; rattacher PIE et ses sources au Lab, pas de nouvelle identité.
- **Guardian v1** : backlog #8 et #9 ; brancher UNI/Aftershock après bootstrap seulement.

## Retour arrière et critères de sortie

- Ne jamais désactiver une connexion de travail encore utilisée.
- Révoquer **uniquement** les anciennes autorisations après inventaire exhaustif et test de rollback.
- Consigner dans [migration-matrix.md](migration-matrix.md) pour chaque dépôt : identité, SHA, CI, workflow, capture de l'installation, état d'activation, retour arrière et responsable.
- **Ne pas appeler un check de connectivité un check de qualité**, ni un build un déploiement.
