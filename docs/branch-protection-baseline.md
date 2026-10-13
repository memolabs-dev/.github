# Memo Labs — protections GitHub : état de référence

**Contrôle du 13 octobre 2026.** Relevé avec `scripts/guardrails-audit.py`, en **lecture seule**. La connexion CLI actuelle peut ne pas révéler certaines règles de niveau organisation ou restrictions liées au plan GitHub.

| Dépôt | Visibilité | Protection classique visible | Rulesets de branche visibles | Workflows | Interprétation |
| --- | --- | --- | --- | ---: | --- |
| `.github` | public | inconnue | 0 | 7 | **À examiner** : aucune protection classique ni ruleset de dépôt observé ; vérifier les règles héritées puis définir une protection du dépôt de gouvernance. |
| `cuesheet` | public | présente | 0 | 2 | Conserver les checks de CI, les conditions de fusion et la commande de suspension. |
| `uni-protocol` | public | présente | 0 | 5 | Vérifier le filtre d'identité du bot avant migration. |
| `problem-intelligence-engine` | public | présente | 0 | 1 | Préserver les tests et la provenance. |
| `drop` | public | non visible | **1** | 9 | **Le ruleset actif doit être examiné en détail** : l'absence de protection classique n'implique pas l'absence de protection. Préserver les règles des tags de release également. |
| `lab-hub` | public | présente | 0 | 2 | Maintenir le build obligatoire ; ne pas confondre avec un déploiement vérifié. |
| `kollio-v3` | privé | inconnue | inconnus | 1 | Le CLI/API n'a pas pu confirmer les règles ; ne pas supposer que le dépôt est protégé. |
| `emargo` | privé | inconnue | inconnus | 4 | Vérification complémentaire dans l'UI du propriétaire nécessaire. |
| `lab-console` | privé | inconnue | inconnus | 1 | Accès sensible ; migrer en dernier, uniquement si besoin démontré. |

## Mesures proposées, **pas encore appliquées**

1. **Gouvernance `.github`** : contrôler les règles héritées. Exiger une PR et la CI `unit-tests` avant fusion de code lié aux identités, si le plan GitHub le permet. Utiliser une revue humaine pour les changements aux scripts d'authentification et aux workflows sensibles.
2. **Autorisations** : une GitHub App à jetons éphémères est une identité, pas un moteur d'exécution autonome. Installer chaque app sur les seuls dépôts nécessaires, sans droits d'administration.
3. **Fusion** : refuser les branches externes, les PR en brouillon et les labels `hold-merge` lorsque l'auto-merge est activé. Ne jamais rendre un test d'installation Guardian `neutral` bloquant.
4. **Releases** : séparer construction, signature, publication et preuve du déploiement effectif. Ne pas attribuer les permissions de déploiement à Guardian.
5. **Protections privées** : les réponses API 403/404 sont un état **inconnu** et non une garantie. Ne rien modifier sans validation du propriétaire.
6. **Vérification des rulesets** : la présence d'un ruleset dans la liste ne prouve pas qu'il s'applique à `main`. Vérifier sa condition `ref_name` et ses exclusions avant toute revendication.

## Reproduction

```bash
python3 scripts/guardrails-audit.py
python3 scripts/guardrails-audit.py --repo drop --repo cuesheet --json
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Le script ne lit pas les valeurs de secrets, ne change ni settings, ni règles, ni branches. Son inventaire ponctuel **ne certifie pas** un statut de sécurité durable : recontrôler avant chaque modification de permissions et changement de workflow d'auto-merge.

Issues : [#6 P0.3](https://github.com/memolabs-dev/.github/issues/6) · [#3 Migration](https://github.com/memolabs-dev/.github/issues/3).
