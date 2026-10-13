# Architecture d'automatisation Memo Labs

**Décision de conception — 13 octobre 2026.** Architecture retenue comme cible, migration progressive, aucune coupure de service sans preuve. Distinguer **identité GitHub**, **agent IA**, **workflow** et **runner** : ce sont quatre responsabilités distinctes.

## Inventaire observé

Organisation `memolabs-dev` : neuf dépôts accessibles au moment de la revue.

| Dépôt | Visibilité | CI et mécanismes observés | Traitement |
| --- | --- | --- | --- |
| `.github` | public | Tests d'identité GitHub App | Centre de gouvernance |
| `cuesheet` | public | CI, auto-merge protégé | Pilote Automation réussi |
| `uni-protocol` | public | CI, release, vérifications d'identité | Contrats et preuves Guardian |
| `drop` | public | Build, test, release, CodeQL, zizmor, Scorecard, Dependabot | Préserver la chaîne de release |
| `problem-intelligence-engine` | public | CI | Preuves de provenance, sans inventer le marché |
| `lab-hub` | public | Publication image Docker GHCR | Le build n'est PAS preuve de déploiement |
| `emargo` | privé | CI, build, Dependabot, auto-merge | Installation explicite, aucun accès global |
| `kollio-v3` | privé | Contrats spatiaux | Installation explicite, tests natifs distincts |
| `lab-console` | privé | Vérification dépôt | Accès opérationnel sensible, en dernier |

Ce recensement n'est pas une certification de leur santé actuelle : vérifier chaque run et son commit avant toute migration.

## Identités

**1 — memo-labs-automation[bot] (EXISTE)**

- Écrit le code et ouvre des PR dans les dépôts installés et autorisés.
- N'est pas un agent cognitif : Claude, ChatGPT, CUESHEET, etc. produisent les décisions.
- Permissions par dépôt limitées ; pas d'administration ni de droits de publication générale.
- Exemple vérifié : CUESHEET #57 écrit en draft. Le filtre d'auto-merge CUESHEET a été élargi via PR #58, fusionnée après CI, et conserve `drop-agent-bot` pendant la transition.

**2 — memo-labs-guardian[bot] (À ENREGISTRER)**

- Identité de vérification : `Contents:read`, `Pull requests:read`, `Actions:read`, `Checks:write`, `Metadata:read`.
- **Jamais** de `Contents:write`, `Workflows:write`, `Deployments:write`, `Administration` ou gestion des secrets.
- Publie un check GitHub uniquement sur le **SHA examiné** et avec des conclusions fidèles aux preuves.
- Ne doit ni relire aveuglément les affirmations du développeur ni produire artificiellement un PASS sur un smoke test d'authentification.
- UNI/Aftershock pourront fournir des artefacts vérifiables : leur intégration réelle est un chantier ultérieur.

**3 — memo-labs-release[bot] (NON CRÉÉ, OPTIONNEL)**

- Identité de livraison indépendante, seulement si les pipelines multi-dépôts nécessitent une séparation forte.
- D'abord établir provenance, signatures, santé post-déploiement, approbation des environnements et rollback.
- Ne pas lui donner un accès de production permanent pour simplifier une démo.

**Fonctions sans GitHub App dédiée :**
- **Radar** : santé et alertes dans Lab Console, lecture agrégée sans inventer des résultats.
- **Steward** : maintenance des dépôts ; tâches avec `GITHUB_TOKEN` ou jeton Automation restreint.
- **Scout** : intégration à PIE, sources primaires et corroboration sans conclure automatiquement à une demande commerciale.

## Repositionnement de drop-agent-bot

`drop-agent-bot` est un compte GitHub de type User, **pas** le moteur de calcul des agents. On peut réaffecter l'agent logiciel qui l'utilisait à des tâches Guardian, mais **l'identité compte utilisateur doit à terme être retirée** ; ne pas lui donner des permissions Guardian pour une indépendance fictive.

Avant révocation : inventorier les tâches cron, secrets, scripts, connexions CLI et dépôts concernés ; tester les consommateurs en jetons temporaires et garder une voie de rollback sûre.

## Règle de contrôle des changements

1. Agent de développement produit une PR avec SHA et sources.
2. GitHub CI réalise ses vérifications techniques.
3. Guardian valide des **contrats pré-définis** sur ce SHA et publie un résultat selon une politique versionnée.
4. Seuls les **checks déterministes** réellement fondés sur des preuves peuvent bloquer une fusion ; les avis IA ou les checks de connexion restent neutres/informatifs.
5. GitHub protège `main`. Un check Guardian ne remplace pas une revue humaine lorsque celle-ci est requise.
6. Release publie un artefact immuable et laisse la production confirmer ce qui est réellement déployé.

Menaces : prompt injection dans la PR, changements de SHA entre l'examen et la fusion, token trop large, secret dans logs, checks mensongers, boucles inter-workflows, approbation par le même agent qui a modifié le code.

## Ordre

P0 : créer Guardian (sélection `.github` seulement), tester `Checks:write` avec conclusion `neutral`.
P1 : connecter une seule PR réelle sur CUESHEET ; contrat initial local et déterministe (pas de jugement LLM comme contrôle bloquant).
P2 : inventorier puis migrer les autres dépôts un à un vers Automation. Aucun retrait des anciens accès avant preuve.
P3 : Radar et Steward dans Lab Console.
P4 : décider si la séparation Release vaut la maintenance d'une troisième application.

Sources officielles :
- https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
- https://docs.github.com/en/rest/checks/runs
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
