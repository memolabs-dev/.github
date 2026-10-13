# Audit branche principale — Memo Labs (13 octobre 2026)

Lecture non destructive via le CLI propriétaire `gh api` des 6 dépôts publics actifs de `memolabs-dev`. Cet audit ne certifie ni les dépôts privés ni la qualité des checks. Une réponse 404 sur `branches/main/protection` ne prouve pas l'absence de *ruleset*, qui utilise une autre API.

| Dépôt | Protection observée | Checks nécessaires | Approbations exigées | Admins | Commentaire |
| --- | --- | --- | --- | --- | --- |
| `.github` | Aucune branch protection API; aucun ruleset observé | aucun à ce niveau | aucune règle visible | s.o. | Centre de gouvernance à protéger avec prudence |
| `cuesheet` | Branch protection | Core and integration tests | **0** | Oui | Force push désactivé |
| `uni-protocol` | Branch protection | UNI required checks | **0** | Oui | Force push désactivé |
| `problem-intelligence-engine` | Branch protection | test (22), test (24) | **0** | Oui | Force push désactivé |
| `drop` | Ruleset active `main` | test, test-windows, test-macos | **0** | Aucun bypass | Merge queue et résolution des fils de review requises |
| `lab-hub` | Branch protection | build | **0** | Oui | Force push désactivé |

### Cas Drop : ruleset #24880009

Cible : branche par défaut, enforcement **active**. Exige PR, trois status checks, merge queue. Refuse suppression et non-fast-forward ; interdit les bypass actors. Réponses de revue périmées invalidées sur nouveau push, fils de discussion requis résolus, mais **required_approving_review_count = 0**, `require_code_owner_review = false`, `require_last_push_approval = false`. La merge queue n'est pas une approbation humaine. Les rulesets de tags de release sont également actifs.

### Décision et risque

Les checks obligatoires ne garantissent pas une revue humaine. Un compte auteur unique ne peut normalement pas approuver sa propre PR : activer brutalement `required_approving_review_count=1` pourrait bloquer la livraison tant qu'aucun reviewer indépendant n'est disponible. Conserver provisoirement les protections existantes, mais **ne pas affirmer que la review humaine est déjà imposée**.

### Plan de durcissement avant activation d'un runner d'agents

1. Confirmer l'équipe de reviewers (humain, non auteur) et leurs permissions pour chaque dépôt, y compris gouvernance `.github`.
2. Ajouter une règle de PR/checks sur `.github` après une CI pilote stable ; aucune merge automatique sans décision propriétaire.
3. Tester une PR auteur humain, une PR auteur App, une PR fork, un SHA changé après revue, un échec CI et le scénario sans reviewer.
4. Régler les exigences de revue repository par repository uniquement lorsque la procédure de secours évite un blocage irréversible ; garder un rollback documenté.
5. Ne jamais traiter Guardian, auto-merge ou le simple statut d'un agent comme validation humaine.

Suivi existant : [garde-fous GitHub #6](https://github.com/memolabs-dev/.github/issues/6). Aucune configuration de protection ou de release modifiée pendant cet audit.
