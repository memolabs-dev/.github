# Audit de réconciliation des tâches publiques — 13 octobre 2026

**Type** : constat en lecture seule ; ce rapport n'est pas une migration de TODO ni une liste de tâches certifiées non livrées.

## Périmètre et politique de confidentialité

Scanner reproductible : `scripts/backlog_inventory.py --all`. Relevé effectué sur les branches par défaut via GitHub CLI authentifié. Seuls cinq dépôts **publics**, explicitement allowlistés, ont été parcourus : `drop`, `cuesheet`, `uni-protocol`, `problem-intelligence-engine`, `guillaume-flambard/kollio-mac`. Les archives OpenSpec sont **exclues** ; seuls les dix fichiers `openspec/changes/l*/tasks.md` actifs de Kollio sont retenus. Aucun contenu de dépôt privé n'est copié dans ce rapport.

| Dépôt | Issues ouvertes observées | Statuts extraits des sources choisies | Observations |
| --- | ---: | --- | --- |
| [Drop](https://github.com/memolabs-dev/drop) | 2 | 65 done, 26 todo, 11 doing, 4 blocked, 4 superseded, 1 deferred, **9 unparsed** | `docs/TASKS.md` est déjà l'index d'exécution ; des lignes Markdown multilignes sont ambiguës. Ne pas convertir automatiquement les 9 lignes inclassables. |
| [CUESHEET](https://github.com/memolabs-dev/cuesheet) | 16 | 15 cochées, 57 non cochées | 8 identifiants du fichier TODO sont explicitement *mentionnés* dans les Issues ouvertes. Les mentions ne prouvent ni couverture complète ni absence de doublon. |
| [Kollio Mac](https://github.com/guillaume-flambard/kollio-mac) | 0 | 126 cochées, 87 non cochées | Les dix lots L0 à L9 nécessitent une cartographie par lot et acceptation, pas 87 nouvelles Issues aveugles. |
| [UNI Protocol](https://github.com/memolabs-dev/uni-protocol) | 4 | 7 cochées, 26 non cochées | Comptes pris dans `docs/roadmap.md` et `specs/003-assurance-model/tasks.md` ; ne reflètent pas nécessairement les autres spécifications. |
| [Problem Intelligence Engine](https://github.com/memolabs-dev/problem-intelligence-engine) | 3 | Aucune checklist reconnue | La roadmap est narrative ; le scanner ne la classe pas comme des tâches ouvertes. |

### Points d'attention

- **Ce sont des compteurs de marqueurs documentaires, pas un statut logiciel validé.** Les TODO peuvent dater d'avant les PR récentes ; seul l'audit code/CI et le propriétaire du chantier peuvent confirmer une livraison.
- **Drop** : T0.7 (mesure D24) demande des développeurs et entretiens réels ; T3.4 demande une installation/recette Mac propre ; T3.7 des validations Windows ; T4.6c un banc à quatre appareils. Ces actions doivent recevoir `needs:human` plutôt que `agent:ready`, sauf petites préparations techniques séparées. Source : [docs/TASKS.md](https://github.com/memolabs-dev/drop/blob/main/docs/TASKS.md).
- **CUESHEET** : priorité aux Issues existantes, notamment [#52](https://github.com/memolabs-dev/cuesheet/issues/52) et [#24](https://github.com/memolabs-dev/cuesheet/issues/24), avant d'ajouter des Issues H01-H10. Source : [docs/harness/TODO.md](https://github.com/memolabs-dev/cuesheet/blob/main/docs/harness/TODO.md).
- **Kollio** : les lots L0–L9 ont des dépendances et des preuves natives ; créer d'abord un Epic d'index, puis des Issues par tranche indépendante après rapprochement des PR et des tests récents. Exemple : [L7](https://github.com/guillaume-flambard/kollio-mac/blob/main/openspec/changes/l7-studio/tasks.md).
- **Provenance** : les références d'Issues sont détectées par mention littérale d'ID, et non par une relation canonique. Une Issue peut mentionner un ID simplement comme dépendance. Le scanner ne crée, ne ferme, n'assigne ni ne relabellise aucune Issue.
- **Vie privée** : les dépôts privés peuvent seulement être rapprochés dans un contexte privé ; ne jamais publier un inventaire détaillé de leurs specs dans `memolabs-dev/.github`.

## Migration progressive à réaliser (chantiers, pas état accompli)

1. Collecter pour chaque source active la preuve GitHub : Issue équivalente, PR ouverte/fusionnée, SHA, CI, source des exigences, responsable, échéance ou blocage humain.
2. Marquer les correspondances **certaines**, les ambigüités et les « à confirmer ». Ne créer une Issue que si le critère d'acceptation est unique et absent de GitHub.
3. Créer un Epic de suivi **sans** déplacer les docs ni supprimer OpenSpec, puis des enfants seulement pour les étapes exécutables encore ouvertes.
4. Ajouter les Issues au **Project privé**, lorsque [#25](https://github.com/memolabs-dev/.github/issues/25) sera débloqué. Conserver les Issues privées dans des vues privées.
5. Relier Issue ↔ spec ↔ PR, produire une vérification STAR, et clôturer uniquement quand le résultat est accepté.

Outils : `python3 scripts/backlog_inventory.py --all` et `python3 -m unittest discover -s tests -p 'test_backlog_inventory.py' -v` (5 tests locaux réussis).

**Limites vérifiées** : scan des sources choisies seulement ; parsing non exhaustif ; aucune corrélation avec les statuts des PR individuelles ; aucun claim, aucune activation d'agent ou migration automatique.
