# IA Hybride — Sujet 5 : assistant clinique GraphRAG validé par l'humain

ISIS Castres · FIE5 DSIA · mini-projet en trinôme.

Question clinique : répondre à des questions qui relient plusieurs faits (« quels médicaments qui
traitent la maladie X sont connus pour provoquer l'effet Y ? »), vérifier chaque affirmation de la
réponse contre le graphe, et transmettre à un expert les réponses peu sûres.

| Brique | Responsable | Fichiers |
|---|---|---|
| 1. Recherche par graphe | Ahmed Ben Rejeb | `brique1_recherche_graphe.py`, `plans.py`, `entites.py`, `hetionet_utils.py`, `medquad_utils.py`, `rag_classique.py`, `cli.py`, `evaluation.py`, `tests/` |
| 2. Vérification par règles | Enzo Ferrier | `brique2_verification_regles.py`, `brique2_problog.py`, `regles_verification.pl`, `tests_extraction.py`, `brique2_experience.py` |
| 3. Validation humaine | Halima Ait Hamou | `brique3_validation/` (confiance, file, mémoire, interface Streamlit, expert simulé, calibration, expériences) |
| Commun | — | `pipeline.py` (enchaînement), `generation.py` (Ollama ou gabarit), `llm_simule.py` (erreurs injectées, expériences seulement), `preparer_donnees.py`, `questions.json` |

Le prototype est local et fonctionne sur CPU, sans clé API ni service payant. Les seuls accès réseau
sont l'installation, la préparation explicite des données et, en option, un Ollama local. Le résultat
est un dossier de preuves académique, **pas une recommandation médicale**.

## Installation (Windows / PowerShell)

Python **3.12** recommandé. Depuis ce dossier :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe preparer_donnees.py      # Hetionet + MedQuAD, révisions figées, SHA256
```

Sur Linux/macOS, remplacer `.\.venv\Scripts\python.exe` par `.venv/bin/python`. Les données
(`data/`) et les résultats (`resultats/`) ne sont pas versionnés : après un clonage, lancer
`preparer_donnees.py` (environ 90 Mo). `--graph-only` ne prépare que le graphe.

## Tout réexécuter

```powershell
$py = ".\.venv\Scripts\python.exe"
# Tests
& $py -m unittest discover -s tests -v                 # brique 1 : 16 tests
& $py tests_extraction.py                              # brique 2 : 11 réponses en texte libre
# Brique 1 seule : évaluation de la recherche (retrieval.csv, summary.json)
& $py evaluation.py
# Brique 2 seule : détection d'erreurs injectées + accord Python / ProbLog (expérience synthétique)
& $py brique2_experience.py
# Brique 3 : calibration de alpha et tau sur un jeu de développement séparé du test
& $py -m brique3_validation.calibration
# Chaîne complète, générateur par gabarit (même générateur pour les deux systèmes)
& $py pipeline.py --systeme graphrag --generateur gabarit
& $py pipeline.py --systeme rag --generateur gabarit
& $py -m brique3_validation.lancer --entree resultats/pipeline_graphrag_question_gabarit.json --passe 1 --expert auto --reinitialiser
& $py -m brique3_validation.lancer --entree resultats/pipeline_rag_question_gabarit.json --passe 1
# Réutilisation des corrections de l'expert sur les paraphrases
& $py pipeline.py --systeme graphrag --formulation paraphrase --generateur gabarit --avec-memoire
& $py -m brique3_validation.lancer --entree resultats/pipeline_graphrag_paraphrase_memoire_gabarit.json --passe 2
# Mesures de la brique 3 (balayage du seuil, ablation, RAG vs GraphRAG, réutilisation, catégories)
& $py -m brique3_validation.experiences --passe1 resultats/b3_pipeline_graphrag_question_gabarit_passe1.json --passe2 resultats/b3_pipeline_graphrag_paraphrase_memoire_gabarit_passe2.json --rag resultats/b3_pipeline_rag_question_gabarit_passe1.json
# Interface de l'expert
& .\.venv\Scripts\streamlit.exe run brique3_validation/interface.py
```

Avec un vrai petit LLM : installer [Ollama](https://ollama.com), `ollama pull qwen2.5:3b`, puis
remplacer `--generateur gabarit` par `--generateur ollama` (option `--modele`). Si Ollama ne répond
pas, le pipeline s'arrête avec un message : il ne se replie jamais en silence sur le gabarit.

## Architecture

```
question ─► [1] entités (dictionnaire strict) ─► plan typé ─► preuves Hetionet (groupes atomiques ≤ 2 sauts)
                                                           └► passages MedQuAD (BM25, focus des entités)
         ─► génération : Ollama | gabarit (GraphRAG : preuves [Tn] ; RAG : extraction des passages [Pn])
         ─► [2] extraction des affirmations (dictionnaire tolérant) ─► règles R1–R12 (+ ProbLog)
         ─► [3] confiance (alpha·recherche + (1−alpha)·vérification) + règles d'escalade
                 ─► réponse livrée | file de l'expert (SQLite, Streamlit)
                 ─► mémoire : réponses validées (signature du plan), faits validés/rejetés (règle R8), synonymes
```

## Brique 1 — Recherche par graphe (Ahmed Ben Rejeb)

1. **Repérage déterministe** par plus longue correspondance sur les noms du graphe et leurs variantes.
   Les homonymes de même type sont exclus. L'appariement approché est désactivé par défaut (`cli.py --fuzzy`).
   L'acronyme « MS » et l'alias « beta blockers » ont été retirés volontairement (trop ambigus).
2. **Plan typé** : traitements, palliation, symptômes, maladies proches, effets indésirables,
   contraintes communes, classes pharmacologiques. Français, négations, disjonctions et posologies sont refusés.
3. **Extraction ciblée** : pour `Disease <-CtD- Compound -CcSE-> Side Effect`, chaque composé exige les
   deux arêtes ; un groupe de preuves n'est jamais coupé par le budget.
4. **MedQuAD** : BM25 restreint aux focus des entités, repli global étiqueté.
5. **Contexte** : 100 triplets, 3 passages, 12 000 caractères au plus ; export JSON versionné
   (contrat dans [docs/INTERFACE.md](docs/INTERFACE.md)).

Le RAG de référence (`rag_classique.py`) cherche par BM25 seul, sans graphe. Le score de recherche est
une heuristique de disponibilité de preuves, pas une probabilité.

## Brique 2 — Vérification par règles (Enzo Ferrier)

Extraction des affirmations sans LLM (déclencheurs lexicaux, signature typée des relations,
coordination, négation, listes à puces), puis règles appliquées dans l'ordre :
R8 mémoire de l'expert, R6 entité hors graphe, R1 arête présente, R3 négation contredite, R4 négation
sans arête (monde ouvert), R5 couverture de la source (« absent ≠ faux »), R2 relation voisine,
R7 arête absente ; au niveau de la réponse : R9 fidélité au contexte, R10 conformité aux contraintes,
R11 complétude, R12 candidats proches. Détails : [docs/BRIQUE2.md](docs/BRIQUE2.md).
La vérification utilise son propre dictionnaire **tolérant** (fautes de frappe d'un LLM), sans
modifier le repérage strict de la brique 1.

## Brique 3 — Validation humaine (Halima Ait Hamou)

Confiance C = alpha · score de recherche + (1 − alpha) · score de vérification ; escalade si C < tau
ou si une règle stricte s'applique (contradiction, entité ou question hors périmètre, affirmation non
soutenue / non vérifiable / partielle, élément non conforme, omissions R11, candidats proches R12,
abstention). alpha et tau sont réglés sur un **jeu de développement synthétique** (150 questions
générées depuis le graphe, entités du test exclues) : `resultats/calibration_b3.json`, lu
automatiquement par `brique3_validation/config.py`. File SQLite, interface Streamlit, expert simulé
avec modèle de temps déclaré, mémoire des corrections réutilisée par la brique 1 (synonymes) et la
brique 2 (règle R8).

## Résultats de la dernière exécution complète (15 octobre 2026, générateur par gabarit)

| Mesure (20 questions, dont 11 à deux sauts) | GraphRAG | RAG classique |
|---|---:|---:|
| Réponses exactes avant validation | 85 % | 15 % |
| Taux d'escalade | 25 % | 100 % |
| Erreurs transmises sans escalade | 0 % | 0 % |
| Temps expert simulé | 318 s | 1 720 s |

- Recherche (brique 1) : plan exact 97,5 % sur 40 formulations ; rappel des preuves 96,9 % (63,5 % sans synonymes, 37,5 % limité à un saut).
- Vérification (brique 2, expérience synthétique, 5 graines) : 100 % des erreurs injectées détectées
  à 10, 20 et 30 % d'erreurs (267/268 à 50 %), 0 % de fausses alertes sur les éléments corrects,
  accord Python / ProbLog sur 674 affirmations sur 674.
- Validation (brique 3) : les 3 réponses fausses de GraphRAG (Q06 warfarine, Q07 et Q15 metformine :
  graphe incomplet) sont escaladées ; sur les paraphrases avec mémoire, l'escalade passe de 25 % à
  10 % et le temps expert de 318 s à 140 s.

Limites : la référence est le graphe (sauf ajouts sourcés de `questions.json`) et la vérification
juge contre ce même graphe ; le jeu de test est petit et connu du code ; le LLM simulé n'est pas un
vrai LLM. Voir [docs/EVALUATION.md](docs/EVALUATION.md).

## Sources

- [Hetionet](https://github.com/hetio/hetionet), Himmelstein et al., [eLife 2017](https://doi.org/10.7554/eLife.26726) ; provenance au niveau de la relation (PharmacotherapyDB, SIDER 4.1, MEDLINE).
- [MedQuAD](https://github.com/abachaa/MedQuAD), Ben Abacha & Demner-Fushman, BMC Bioinformatics 2019 ; collections 1 à 9.
- [ProbLog](https://dtai.cs.kuleuven.be/problog/) pour la version pondérée des règles.
- Notices FDA (Coumadin, Glucophage) pour les références externes de `questions.json`.
- Supports du cours IA Hybride (S1, S2_demo_RAG, S3).

**Assistants de code** (déclaration exigée par le sujet) : la base et les briques 2 et 3 ont été
écrites avec l'aide de Claude (Anthropic) ; l'audit et la refonte de la brique 1 avec OpenAI Codex.
Le code a été relu et exécuté par le trinôme, qui en reste responsable.

## Git

Branche principale : `main` (la branche `master` ne contient que la brique 1, version d'Ahmed). Ne versionner ni `data/`, ni `resultats/`, ni la base SQLite ou la mémoire de
l'expert (voir `.gitignore`). Avant de pousser : lancer les tests, relire `git diff --cached`.
Historique de l'audit de la brique 1 : [docs/AUDIT.md](docs/AUDIT.md).
