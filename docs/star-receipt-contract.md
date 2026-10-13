# STAR — contrat de preuve d'un vrai worktree

La tâche [#44](https://github.com/memolabs-dev/.github/issues/44) complète le pilote [#40](https://github.com/memolabs-dev/.github/pull/40) sans démarrer d'agent autonome.

## Contrat

L'outil `scripts/star_receipt.py` ne fait que lire le contexte Git et le bail GitHub actif, puis lancer la **commande de tests fixée dans le code**, sans shell et sans exécuter le texte de l'Issue. Il vérifie les éléments suivants :

- dépôt public Memo Labs identifié par l'URL exacte du remote ;
- worktree Git isolé, branche de tâche approuvée et aucun fichier non commité ;
- parent Git approuvé, SHA de base, SHA de HEAD et SHA blob de la spec ;
- ensemble strictement limité des trois fichiers modifiables ;
- bail lié à l'Issue #44 : identité déclarée, claim-id, SHA de fencing, génération ;
- suite de tests déterministe `python3 -m unittest discover -s tests -p test_*.py -v` avec nombre effectivement observé ;
- retour JSON sans journaux bruts, secrets ni chemin absolu local.

Le bail est revérifié **avant et après** les tests. Un code de retour zéro **sans nombre de tests observé** ne peut pas devenir PASS. L'échec et le timeout restent explicites.

## Lancement du reçu, une fois le code commité

```sh
python3 scripts/star_receipt.py \
  --worktree /Users/memo/projects/_worktrees/memo-star-receipt-44 \
  --worker star-receipt-pilot \
  --claim-id '<identifiant du bail>' \
  --fence '<SHA de référence du bail>'
```

La sortie est un reçu structuré à associer à la Draft PR. Le programme ne crée, ne fusionne ni ne déploie aucune PR. Il n'active aucun runner sur les dépôts privés, ni aucun workflow GitHub non sollicité.

## Limites de sûreté

Ce n'est **pas** une protection atomique des écritures : GitHub vérifie le bail et le push dans des opérations indépendantes. L'identité worker n'est pas encore liée cryptographiquement à un runner attesté, et les tests d'un dépôt inconnu ne doivent pas être lancés automatiquement. Avant l'activation d'un vrai agent non supervisé, le suivi [#39](https://github.com/memolabs-dev/.github/issues/39) devra couvrir ce raccordement et une isolation plus forte.

Exigences de livraison : tests locaux, CI sur SHA courant, Draft PR et preuve de libération du bail. Aucune fusion ni modification de règles de branche.
