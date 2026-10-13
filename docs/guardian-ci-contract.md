# Guardian v0.1 — précontrôle déterministe des preuves CI

**État : implémenté en lecture seule, sans GitHub App Guardian installée.** Ce contrôle prépare l'intégration future avec UNI/Aftershock, mais **ne remplace pas leurs vérificateurs** et ne constitue pas une validation indépendante de la qualité fonctionnelle.

## Contrat initial

- **Dépôt pilote :** `memolabs-dev/cuesheet`.
- **Version du contrat :** `memo-guardian/ci-provenance@0.1.0`, [politique JSON](../github-apps/guardian-cuesheet-policy.json).
- **Entrée obligatoire :** numéro de PR. La CLI GitHub lit la PR, capture le **SHA HEAD complet**, puis demande les Check Runs associés à ce SHA.
- **Contrôle requis :** `Core and integration tests`, publié par l'application vérifiée `github-actions`.
- **Décisions :** `ci_success`, `blocked`, `incomplete`.
- **Refus explicites :** SHA invalide, résultat absent, check d'un autre commit, doublon ambigu, vérificateur non reconnu, check non terminé, CI échouée, réponse paginée/non exhaustive.
- **Sortie :** JSON avec preuve GitHub, version de politique, SHA, conclusion et empreinte SHA-256 pour comparaison ; **ce hash n'est pas une signature** et ne prouve pas que la preuve est indépendante.
- **Sécurité :** aucune édition, publication de Check, fusion, déploiement ou lecture de secret.

## Démonstration exécutée

```bash
python3 scripts/guardian-ci-preflight.py --pr 57
```

Exécuté sur la [PR CUESHEET #57](https://github.com/memolabs-dev/cuesheet/pull/57) le 13 octobre 2026 :

- SHA : `08525ef8e5e747841589257101234944c82f47d4`.
- Check : `Core and integration tests`, `completed/success`, édité par `github-actions`.
- [Job GitHub Actions source](https://github.com/memolabs-dev/cuesheet/actions/runs/38380403214/job/115239093776).
- Résultat : **`ci_gate=ci_success`**, **`pull_request_is_draft=true`**, **`can_merge=false`**, **`quality_certified=false`**.

Ce résultat signifie uniquement que GitHub rapporte un contrôle CI réussi sur le commit courant de la PR.

## Intégration future UNI/Aftershock

Avant de publier un check Guardian bloquant :

1. Charger et épingler les spécifications/contrats UNI réellement exécutés.
2. Ajouter des preuves avec provenance indépendante, signatures/attestations ou artefacts CI authentifiés, sans faire confiance à un JSON fourni par l'agent développeur.
3. Revalider après chaque changement de SHA et contrôler la fraîcheur des preuves.
4. Définir explicitement les transitions `incomplete → blocked / acceptable` et la politique d'acceptation.
5. Tester des corpus adversariaux et l'indépendance des vérificateurs.
6. Quand **Memo Guardian** sera installée, publier des GitHub Checks avec la permission `checks:write` seulement après avoir lié le verdict au SHA exact. Le `bootstrap` neutre ne doit jamais être un required check.

Issue : [#8 Guardian v1](https://github.com/memolabs-dev/.github/issues/8). Le test ne détermine pas la possibilité de fusion : GitHub et ses protections restent autorités.
