# Journal STAR des chantiers d'identités GitHub

Les cycles ci-dessous représentent uniquement le travail réellement effectué. Un travail préparatoire n'est pas une activation.

## Cycle 1 — Applications distinctes

- **Situation** : Automation est opérationnelle ; Guardian et Release ne sont pas installées.
- **Tâche** : définir deux profils séparés, sans droits Guardian d'écriture du code.
- **Actions** : manifeste Guardian existant, nouveau manifeste Release optionnel ; assertions de permissions dans `tests/test_app_specs.py` ; `register-guardian.py` adapté aux profils `--app guardian` et `--app release`.
- **Résultat** : permissions des manifestes contrôlées localement ; **GitHub registration et installation à confirmer par le propriétaire**.

## Cycle 2 — Tests GitHub sans mutation

- **Situation** : l'installation Automation couvre initialement `.github` et CUESHEET.
- **Tâche** : pouvoir prouver l'accès à chaque nouveau dépôt sans modifications de code.
- **Actions** : workflow manuel `app-repo-access-smoke.yml` avec choix limité aux neuf dépôts ; script `post-activation.py` en dry-run par défaut.
- **Résultat** : test statique de permissions et répétition à blanc passés ; chaque preuve de dépôt supplémentaire exigera d'abord installation + workflow vert.

## Cycle 3 — Guardian et Release bootstrap

- **Situation** : la connexion à une App n'atteste ni qualité ni déploiement.
- **Tâche** : séparer le test technique d'identité et la vraie vérification du logiciel.
- **Actions** : contrôle Guardian `memo-guardian/bootstrap` à conclusion `neutral` ; Release dispose d'un smoke **read-only sur Drop**, sans création de release.
- **Résultat** : tests prêts, **non lancés** puisque les nouvelles applications ne sont pas créées. Aucun required check ajouté.

## Cycle 4 — Supervision minimale

- **Situation** : aucun tableau transverse ne montre les dernières CI des neuf dépôts.
- **Tâche** : produire un état lisible en lecture seule, sans confondre build et déploiement.
- **Actions** : `scripts/radar.py`, lecture du dernier workflow via CLI.
- **Résultat** : script exécuté sur les neuf dépôts et affichage des résultats ; colonne déploiement marquée **Unknown**. Intégration Lab Console, alertes et reçus de production restent à implémenter (#18).

## Préconditions avant la suite

1. Confirmer manuellement Guardian puis Release si décidé ; aucune clé affichée dans GitHub ou les journaux.
2. Installer les applications avec sélection explicite des dépôts.
3. Exécuter les smokes en lecture seule et confronter leurs statuts au SHA.
4. Migrer les agents et outils consommateurs des PAT *avant* la révocation.
5. Lancer UNI/Aftershock sur un cas réel pour que Guardian puisse émettre des conclusions justifiées.


## Cycle 5 — Vérification GitHub du pilote déjà installé

- **Situation** : `.github` et CUESHEET disposent déjà de l'installation Automation.
- **Tâche** : valider le nouveau workflow en lecture seule contre GitHub réel.
- **Actions** : exécution du workflow `app-repo-access-smoke.yml` une fois sur `.github`, une fois sur `cuesheet`.
- **Résultat** : [run .github #38387727480](https://github.com/memolabs-dev/.github/actions/runs/38387727480) — **success** ; [run CUESHEET #38387827602](https://github.com/memolabs-dev/.github/actions/runs/38387827602) — **success**. Aucun autre dépôt n'a été connecté.

## Cycle 6 — Memo Steward, inspection non destructive

- **Situation** : la maintenance des dépôts n'a pas de vue transversale simple des PR inactives.
- **Tâche** : produire des candidates à la revue sans pouvoir clôturer ou fusionner une PR.
- **Actions** : `scripts/steward.py --days 14` lit les dates de mise à jour des PR ouvertes sur les neuf dépôts.
- **Résultat** : exécution réelle réussie ; **0 candidate** âgée d'au moins 14 jours au moment de l'exécution. Aucun changement de PR, branche ou étiquette. Les règles de maintenance et l'intégration UI restent dans #19.

## Cycle 7 — CI des spécifications

- **Situation** : les permissions proposées doivent rester séparées lors des futures révisions.
- **Tâche** : exécuter les tests statiques à chaque modification du dépôt de gouvernance.
- **Actions** : workflow `automation-spec-ci.yml` ; cinq tests indépendants de tout secret.
- **Résultat** : [run #38387677500](https://github.com/memolabs-dev/.github/actions/runs/38387677500) — **success**, sur commit `a8f338e`.

## Cycle 8 — Client local de jetons éphémères, sans PAT

- **Situation** : les workflows Actions savaient utiliser une GitHub App, mais les agents locaux dépendaient encore d'identités CLI utilisateur.
- **Tâche** : fournir un mécanisme partagé pour une commande `gh`, avec jeton d'installation limité à un dépôt et aux permissions demandées.
- **Actions** : ajout de `scripts/with-app-token.py` et des tests `tests/test_app_token.py` ; vérification des clés 0600, de l'App (ID/slug), de l'installation organisation et des permissions autorisées. Ajout du stockage de l'ID public des nouvelles Apps après leur inscription.
- **Résultat** : **17 tests unitaires locaux réussis** ; authentification GitHub App réelle réussie pour `memolabs-dev/.github` et `memolabs-dev/cuesheet` avec `contents:read`. Aucun jeton imprimé ou enregistré par l'outil. **Les cas d'écriture, les identités Guardian/Release non créées et les autres dépôts restent non validés.**
