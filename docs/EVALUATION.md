# Protocole et cadrage collectif

## Ce que cette branche mesure

`evaluation.py` exécute 20 questions, dont 11 multi-sauts, plus leurs 20 paraphrases, sur quatre configurations : GraphRAG, RAG BM25 seul, GraphRAG sans synonymes manuels, GraphRAG limité à un saut. Même corpus, même k maximal et même plafond de caractères ; le filtre de focus constitue une partie explicite du mécanisme GraphRAG.

Sorties : `retrieval.csv` (chaque recherche), `contexts.jsonl` (preuves consultables), `summary.json` (moyennes et dénominateurs), `passage_judgments.csv` (annotations humaines à compléter). Le chargement/indexage est mesuré séparément de la recherche. Les latences varient avec la machine et ne sont pas un benchmark matériel.

Dimensions couvertes au niveau recherche : performance (plan exact, rappel des preuves), cohérence (orientation/types et contraintes), explicabilité (preuves/citations), robustesse (paraphrases, synonymes absents, OOD), coût (temps et taille du contexte). La validité des arêtes est une mesure de traçabilité, pas une mesure de fidélité de génération.

Référence : les plans canoniques sont fournis dans `questions.json`. Un oracle séparé construit les arêtes attendues sans appeler le parseur ni la fonction d'exécution de production. Les cas sans preuve ont un rappel non défini (`null`), pas 100 %. RAG ne reçoit aucun score de rappel de triplets, métrique inapplicable à son résultat textuel. Les ajouts/retraits cliniques hérités ne sont pas injectés dans les données.

Échec principal observé : Q11 paraphrase (« MS »), attribué à la liaison d'entités ; l'abstention évite d'inventer une maladie. Les questions sur des relations absentes et la fibromyalgie illustrent une limite de couverture des données, distincte d'un échec technique. Une preuve inexistante ne permet pas une réponse négative.

## Travail collectif restant pour satisfaire intégralement le sujet

1. Figer cette version, les paramètres et les 20 questions avant la comparaison finale. Ajouter un jeu de développement et un jeu inédit indépendant, sans réglage sur le test.
2. Annoter les passages pertinents et les réponses attendues avec sources précises ; deux membres relisent les désaccords. Une référence construite seulement par le graphe mesure la récupération du graphe, pas l'exactitude clinique. Revoir notamment les annotations externes FDA héritées de la base.
3. Brancher le même générateur sur les deux systèmes : soit un LLM local fixé, soit un gabarit/extracteur explicitement justifié. Conserver modèle, température, prompt, réponses, citations et versions. Aucun LLM simulé ne peut servir à annoncer les performances d'un vrai LLM.
4. Brique 2 : mesurer fidélité au contexte et détection des affirmations non soutenues sur annotations ; séparer non documenté et contradictoire. Une injection d'erreurs peut tester le vérificateur, mais doit être publiée comme expérience synthétique séparée.
5. Brique 3 : calibrer sur développement uniquement ; mesurer taux d'escalade et temps expert simulé selon hypothèses explicites. Le score de recherche fourni ne suffit pas pour calculer ces métriques.
6. Comparer l'exactitude des réponses RAG/GraphRAG sur les mêmes 20 questions ; présenter aussi les huit questions multi-sauts au minimum (ici onze). Attribuer les erreurs à liaison, plan, extraction, texte, génération, vérification ou décision humaine.

La pertinence des passages, l'exactitude des réponses générées, leur fidélité, la détection, l'escalade et le temps expert restent **non mesurés** dans cette branche. Les tableaux vides d'annotation sont des tâches restantes, pas des résultats.

## État de l'intégration (15 octobre 2026)

| Point ci-dessus | État |
|---|---|
| 1. Jeu de développement séparé | Fait pour la brique 3 : `brique3_validation/calibration.py` génère 150 questions depuis le graphe, entités du test exclues. Un jeu inédit annoté à la main reste à faire. |
| 2. Annotations humaines | Reste à faire (`passage_judgments.csv`). |
| 3. Même générateur pour les deux systèmes | Fait : `generation.py`, gabarit extractif déclaré (preuves [Tn] pour GraphRAG, phrases des passages [Pn] pour le RAG) ; Ollama branché, pas de repli silencieux. |
| 4. Brique 2 : détection et fidélité | Fait en expérience synthétique séparée : `brique2_experience.py` (erreurs injectées par `llm_simule.py`, fausses alertes, accord Python / ProbLog). |
| 5. Brique 3 : calibration, escalade, temps expert | Fait : calibration sur le développement, `lancer.py`, `experiences.py`, modèle de temps dans `config.py`. |
| 6. Comparaison RAG / GraphRAG, erreurs par brique | Fait avec le gabarit (`experiences.py`, E3 et E5/E6) ; à refaire avec Ollama pour un vrai LLM. |

Résultats de la dernière exécution : voir le README.

## Fiche de cadrage proposée

**Problème :** relier des faits médicaux publics et montrer les preuves avant génération. **Hypothèse :** les jointures typées améliorent la récupération de preuves composées par rapport au texte seul. **Périmètre :** anglais, six relations Hetionet, deux sauts, corpus MedQuAD fixe, absence de données patient. **Livrable Ahmed :** cette brique, son contrat JSON et son évaluation de recherche.

**Répartition :** Ahmed — recherche/contexte ; responsable brique 2 — vérification et fidélité ; responsable brique 3 — calibration, file humaine et corrections. Les identités/rôles de l'équipe sont à confirmer collectivement d'après la répartition du projet initial.

**Ordre d'intégration :** stabiliser payload → brancher génération et vérification → brancher validation humaine → produire mesures collectives → rédiger et répéter la soutenance.

**Rapport de six pages proposé :** (1) question, données, périmètre et baseline ; (2) recherche et contrat ; (3) génération/vérification ; (4) validation humaine ; (5) protocole, résultats, ablations ; (6) erreurs, limites, coûts et conclusion. Sources et usage des assistants à rendre visibles.

**Soutenance de 15 minutes + 7 minutes de questions :** environ 4 minutes par brique, 3 minutes pour cadrage/comparaison/limites. Pour la première brique, démontrer une question à deux sauts, les IDs/citations, puis une absence d'arête qui ne produit jamais « faux ».
