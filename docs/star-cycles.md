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
