# Contrat UNI du dépôt de gouvernance Memo Labs

**Pilote en cours — 13 octobre 2026.** Il s'agit d'une vérification déterministe des tests et du registre de confiance de `memolabs-dev/.github` ; **ce n'est pas encore une attestation Guardian indépendante**.

## Périmètre exact

- [Contrat UNI](../uni/intents/governance.uni) : `INTENT memolabs.governance`, revendication requise `governance-tests`.
- [Registre UNI](../.uni/config.toml) : seul `governance.tests` est autorisé à exécuter `python3 -m unittest discover -s tests -p 'test_*.py'`. Le contrat non fiable ne peut pas choisir une nouvelle commande.
- [Workflow de vérification](../.github/workflows/uni-governance.yml) : `main` seulement, manuellement ou après push sur `main`, permissions `contents:read`, pas de secrets applicatifs.
- Version d'UNI : release **v0.9.4** de `memolabs-dev/uni-protocol`, composite action épinglée au commit `7c78bcca315d45ad4ed456082e29ed70b43dbe66`.
- Preuves locales UNI (`.uni/evidence`, `.uni/decisions`, etc.) ignorées par Git ; seuls contrat et registre sont suivis.

## Comportements et limites

Le binaire UNI v0.9.4 a été testé sur macOS. Son `uni init` **n'accepte pas** `--profile python`, malgré la documentation plus récente de `main`; nous avons utilisé `uni init` puis remplacé le registre par une entrée Python approuvée et versionnée.

Les deux premiers essais locaux ont renvoyé `EvidenceRequired` malgré les tests Python verts. Le premier reçu portait `workspace_dirty=true`, ce qui invalide correctement la preuve. Le deuxième, après commit propre, indiquait `artifact_files={}` : les motifs `tests/*.py` et similaires n'étaient **pas reconnus** comme nous l'avions supposé. En UNI v0.9.4, `*` représente un segment entier et `**` plusieurs segments. Après remplacement initial par `tests/**`, `scripts/**`, `github-apps/**` et `.github/workflows/**`, le commit `5aeb98a` a permis à UNI de répondre **`Accepted`** : `governance-tests` est `Valid`, `artifact_hash` est présent et `uni report` indique 1/1 revendication vérifiée. Mais les 120 chemins surveillés incluaient également des sauvegardes et caches ignorés par Git sur le Mac. **Le registre utilise maintenant 25 chemins Git suivis explicitement** ; `tests/test_uni_governance.py` vérifie que cette liste correspond exactement aux fichiers versionnés pertinents. Une nouvelle preuve sur commit propre est requise pour valider ce périmètre. **L'assurance reste A2/self-declared** : la reproductibilité ne prouve pas une identité indépendante. Ne jamais traiter un code retour de tests 0 comme une acceptation UNI.

Le contrat prouve **que la suite de tests enregistrée a réussi sur une révision identifiée**, pas que chaque intention produit est satisfaite. Une commande de tests approuvée n'est pas équivalente à un audit de code indépendant ou à un certificat cryptographique d'identité.

**Ne pas activer sur `pull_request` pour l'instant** : charger des commandes de vérification depuis une PR non approuvée briserait notre frontière de confiance. La CI existante continue de tester les PR avec ses propres restrictions, et UNI est réservé à `main` pour ce pilote.

## Prochaines étapes

1. Tester `uni lint`, `uni verify`, `uni report` sur un commit propre, puis contrôler les champs d'identité, de révision et d'invalidation des preuves.
2. Confirmer une exécution GitHub Actions de `UNI governance assurance (deterministic)` sur `main`.
3. Ajouter un invariant métier réellement indépendant (p. ex. politique de branche, absence de permissions excessives) avec son propre vérificateur déclaré **par le propriétaire**.
4. Lorsque `memo-labs-guardian` sera enregistrée, publier un résultat GitHub Checks limité à la **preuve réellement obtenue**, lié au même SHA et à la même politique. Ne jamais transformer un état A2/self-declared en A3/identité vérifiée sans jeton d'identité signé validé.

Références : [UNI Quickstart](https://github.com/memolabs-dev/uni-protocol/blob/main/docs/quickstart.md) · [Statut UNI](https://github.com/memolabs-dev/uni-protocol/blob/main/docs/current-status.md) · [Issue #8](https://github.com/memolabs-dev/.github/issues/8).
