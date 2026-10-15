# Brique 2 — Vérification par règles (Enzo Ferrier)

| Fichier | Rôle |
|---|---|
| `brique2_verification_regles.py` | extraction des affirmations de la réponse + règles R1–R12 (statut, règle, explication) |
| `brique2_problog.py` | génération et évaluation du programme ProbLog pour une réponse |
| `regles_verification.pl` | les mêmes règles en ProbLog, pondérées |
| `tests_extraction.py` | 11 réponses en texte libre, rédigées comme celles d'un petit LLM |
| `brique2_experience.py` | expérience synthétique : erreurs injectées, détection, fausses alertes, accord Python / ProbLog |

Entrée : la réponse (texte libre), le plan de la question (brique 1) et le contexte. Sortie : un
rapport avec, pour chaque affirmation, un statut, la règle qui l'a établi et une explication.
Dans `pipeline.py`, la vérification reçoit un `Dictionnaire(g, approche=True)` : elle doit relier
des noms écrits avec une faute ou un synonyme par un LLM, alors que la brique 1 reste stricte.

## Règles (la première qui conclut l'emporte)

| Règle | Condition | Statut |
|---|---|---|
| R8 | fait validé / rejeté par l'expert (mémoire de la brique 3) | SOUTENUE / CONTRADICTOIRE |
| R6 | entité absente du graphe ou d'un autre type | NON_VERIFIABLE |
| R1 | arête présente | SOUTENUE (triplet + source) |
| R3 | affirmation niée alors que l'arête existe | CONTRADICTOIRE |
| R4 | affirmation niée, arête absente | NON_VERIFIABLE (monde ouvert) |
| R5 | le sujet n'a aucune arête de ce type (ex. warfarine sans effet dans SIDER) | NON_VERIFIABLE |
| R2 | « traite » alors que le graphe dit « soulage », ou effet plus général présent | PARTIELLE |
| R7 | entités et relation couvertes, arête absente | NON_SOUTENUE (absent ≠ faux) |
| R9 | affirmation absente du contexte fourni au générateur | drapeau `hors_contexte` |
| R10 | un élément ne satisfait pas toutes les contraintes de la question | drapeau `element_non_conforme` |
| R11 | éléments du graphe omis par la réponse | drapeau `omissions` |
| R12 | élément qui satisfait la question avec un effet plus général | drapeau `candidats_proches` |

Poids des statuts (score de vérification) : 1 ; 0,6 ; 0,3 ; 0,1 ; 0. Sources : provenance des arêtes
Hetionet (Himmelstein et al., eLife 2017), SIDER 4.1, PharmacotherapyDB ; hypothèse du monde ouvert
(cours, séance 1).

## Résultats (`python brique2_experience.py`, 20 questions × 5 graines)

| Taux d'erreur injecté | Erreurs détectées | Fausses alertes |
|---:|---:|---:|
| 10 % | 63 / 63 | 0 % |
| 20 % | 118 / 118 | 0 % |
| 30 % | 174 / 174 | 0 % |
| 50 % | 267 / 268 | 0 % |

Accord Python / ProbLog : 674 affirmations sur 674. Expérience synthétique : la référence est le
graphe que la brique 2 utilise aussi ; elle mesure l'écart au graphe, pas la vérité clinique.
