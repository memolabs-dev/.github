# Contrat de fusion Memo Labs (`memo-labs/landing@0.1.0`)

**Décision du 13 octobre 2026.** Un seul contrat de fusion pour tous les dépôts. Il remplace progressivement les quatre mécanismes observés le même jour :
- auto-merge natif armé à l'ouverture (`cuesheet`, `uni-protocol`) ;
- fusion déclenchée par une CI verte (`emargo`) ;
- label `safe-automerge` (`lab-infra`) ;
- file de fusion configurée mais inutilisée (`drop`).

Contexte d'ensemble : la note Vault `1-Projects/memo-labs-os.md`.

## Règle

**Un agent ne fusionne jamais. Le contrat fusionne**, quand le commit exact a été vérifié.

Une PR est fusionnée si toutes ces conditions sont vraies sur le SHA testé :

1. elle est ouverte, n'est pas un brouillon, vient du même dépôt et cible la branche par défaut ;
2. son auteur est une identité de confiance (`guillaume-flambard`, `memo-labs-automation[bot]`, `drop-agent-bot` pendant la transition) ;
3. elle ne porte pas le label `hold-merge` ;
4. elle ne touche aucun chemin protégé : `.github/`, `Dockerfile*`, `docker/`, `deploy/`, `deployment/`, `scripts/deploy*`, `ansible/`, `stacks/`, `infra/`, plus les motifs propres au dépôt. Ces changements restent fusionnés par un humain ;
5. tous les check runs et statuts de ce SHA sont terminés et verts (`success`, `neutral` ou `skipped`), et au moins un existe ;
6. chaque preuve requise par le dépôt (`required_checks`, par exemple un reçu UNI ou Guardian) est présente et en `success`.

La fusion utilise `--match-head-commit`, si bien qu'un push plus récent et non testé ne peut jamais être fusionné à sa place. La branche est supprimée après fusion : GitHub reporte alors automatiquement les PR empilées sur la branche par défaut.

## Pourquoi ce mécanisme

- **Il fonctionne partout.** Un workflow réutilisable d'un dépôt public peut être appelé par des dépôts privés ([doc GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations)). Il ne dépend pas de la protection de branche, indisponible sur les dépôts privés du plan Free.
- **Il ne lit que des métadonnées de l'API GitHub.** Il ne récupère jamais le code de la PR et ne l'exécute jamais.
- **Les pushes faits avec `GITHUB_TOKEN` ne déclenchent aucun workflow.** Le paramètre `dispatch` relance explicitement les workflows de la branche par défaut (CI, build) après la fusion, comme le faisait `emargo`.

## Adopter le contrat dans un dépôt

Copier `workflow-templates/land.yml` dans `.github/workflows/land.yml`. GitHub le propose aussi dans *Actions → New workflow*. Ensuite, ajuster :

- `workflows:` : chaque workflow dont le résultat conditionne la fusion ;
- `method` : `squash` (par défaut) ou `merge` ;
- `required_checks` : les noms de checks de preuve obligatoires ;
- `extra_protected` : les chemins propres au dépôt qui exigent un humain (migrations, signature…) ;
- `dispatch` : les workflows à relancer sur la branche par défaut après la fusion. Chacun doit accepter `workflow_dispatch`.

Ajouter ce fichier touche `.github/`, donc **la PR d'adoption est elle-même fusionnée par un humain**, une seule fois par dépôt.

## Observer et suspendre

- **Observer.** Chaque exécution écrit son verdict JSON dans le résumé du job. Les raisons qui commencent par `wait_` signifient qu'une prochaine complétion de CI pourra fusionner la PR.
- **Suspendre.** Le label `hold-merge` met une PR en pause, et la passer en brouillon a le même effet.
- **Tester à blanc :** `python3 scripts/land.py --repo <owner/repo> --sha <sha> --dry-run`.

## Ordre de déploiement

1. Pilote : `memo-bridge`.
2. Puis `cuesheet` et `uni-protocol` (remplacement de leur auto-merge natif) et `emargo` (remplacement de son workflow local).
3. Puis les dépôts sans aucun mécanisme : `intentlane`, `world-kernel`, `kollio-mac`, `stasis`, `memo-cc`, `infrastructure-guardian`.
4. `lab-infra` et `drop` en dernier, avec leurs règles propres (`extra_protected`, file de fusion).

Quand Guardian publiera ses checks (#2, #7), son nom sera ajouté à `required_checks`.
