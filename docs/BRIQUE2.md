# Brique 2 — Vérification par règles (Enzo Ferrier)

Mini-projet IA hybride, sujet 5 (assistant clinique GraphRAG validé par l'humain).

| Fichier | Rôle |
|---|---|
| `brique2_verification_regles.py` | extraction des affirmations de la réponse + règles R1–R12 (statut, règle, explication) |
| `brique2_problog.py` | génération et évaluation du programme ProbLog pour une réponse |
| `regles_verification.pl` | les mêmes règles en ProbLog, pondérées |
| `tests_extraction.py` | 11 tests d'extraction sur des réponses en texte libre (`python tests_extraction.py`) |

Ces fichiers s'utilisent dans le dossier complet du projet (`sujet5_graphrag`) : ils importent les
modules partagés `hetionet_utils.py`, `entites.py` et `plans.py`, et la vérification ProbLog a besoin
du paquet `problog` (`pip install problog`).
