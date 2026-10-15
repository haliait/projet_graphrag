# IA Hybride — Sujet 5, brique 1 : recherche par graphe

**Responsable : Ahmed Ben Rejeb.** Cette branche livre uniquement la recherche : question anglaise → entités typées → preuves Hetionet → passages MedQuAD → contexte et messages pour un LLM. Elle ne contient ni vérificateur d'affirmations, ni décision clinique, ni interface de validation humaine.

Le prototype est gratuit, local et fonctionne sur CPU, sans clé API, sans modèle à télécharger et sans service payant. Les seuls accès réseau sont l'installation et la préparation explicite des données. Les questions ne quittent pas la machine. Le résultat est un dossier de preuves académique, pas une recommandation médicale.

## Démarrage sous Windows / PowerShell

Python **3.12** recommandé, Git pour le dépôt. Depuis ce dossier :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe preparer_donnees.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe cli.py "Which drugs that treat rheumatoid arthritis are known to cause hepatotoxicity?" --output resultats/demo.json
.\.venv\Scripts\python.exe evaluation.py
```

Sur Linux/macOS, remplacer `.\.venv\Scripts\python.exe` par `.venv/bin/python`. Aucun script d'activation PowerShell n'est nécessaire. Prévoir quelques centaines de Mo de disque et de la RAM pour les matrices creuses et le graphe ; aucun GPU. L'index est reconstruit à chaque lancement, puis réutilisé en mémoire pendant l'évaluation.

Les données complètes sont déjà préparées dans la copie locale livrée. Après clonage Git, lancer `preparer_donnees.py` : les données et les résultats détaillés ne sont pas versionnés. Les téléchargements sont figés par révision et vérifiés par SHA256 dans `data_checksums.json`. Une interruption se reprend en relançant la commande ; un fichier au hash erroné doit être supprimé explicitement avant relance. `--data-dir CHEMIN` permet un autre dossier, `--graph-only` ne prépare que le graphe.

## Utilisation et sortie pour l'équipe

```powershell
# Graphe et passages, export JSON version 1.0
.\.venv\Scripts\python.exe cli.py "What drugs treat gout?" --output resultats/gout.json
# Référence non hybride : BM25 seul, sans dictionnaire ni plan issus du graphe
.\.venv\Scripts\python.exe cli.py "What drugs treat gout?" --mode rag --output resultats/rag.json
# Monde ouvert : un lien absent reste non documenté
.\.venv\Scripts\python.exe cli.py "Does warfarin cause bleeding?" --output resultats/unknown.json
```

En Python, construire les ressources une fois :

```python
from cli import construire
g, recherche = construire()
contexte = recherche.rechercher("What drugs treat gout?")
payload = contexte.exporter(g)
print(payload["context"])
messages = payload["messages"]  # prêt pour un futur adaptateur LLM local
```

Le contrat détaillé est dans [docs/INTERFACE.md](docs/INTERFACE.md). Les identifiants Hetionet et les citations `T1`, `P1` servent de références pour les briques suivantes. Les passages conservent leur identifiant, URL, source, texte, focus, score BM25 et mode de récupération. Les messages séparent une instruction système des données JSON non fiables. Cela réduit le mélange entre documents et instructions, sans garantir la résistance d'un futur LLM aux injections.

**Aucune `AI_API_KEY` n'est nécessaire.** Le contexte se teste indépendamment de la génération. Un futur adaptateur Ollama pourra consommer `messages`, à température fixe, avec modèle et version consignés. Il devra annoncer une panne explicitement, sans remplacer silencieusement le modèle par un gabarit. Aucun résultat de LLM n'est revendiqué ici.

## Structure

| Fichier | Fonction |
|---|---|
| `hetionet_utils.py` | Chargement TSV/GZIP validé, relations typées, voisinage et chemins bornés |
| `entites.py` | Noms du graphe, normalisation, synonymes éditoriaux hérités, ambiguïtés |
| `plans.py` | Intentions et emplacements typés ; rejet de contraintes non prises en charge |
| `brique1_recherche_graphe.py` | Jointures de graphe, groupes de preuves indivisibles, contexte borné et export |
| `medquad_utils.py` | XML sécurisé, découpage 120 mots/20 de recouvrement, BM25 creux |
| `rag_classique.py` | Référence BM25 sans accès au graphe |
| `preparer_donnees.py` | Téléchargements explicites, révisions figées, intégrité, manifeste |
| `cli.py` | Point d'entrée pour l'équipe |
| `evaluation.py`, `questions.json` | Comparaison sur 20 questions et 20 paraphrases ; deux ablations |
| `tests/` | Tests hors ligne sur un mini-graphe synthétique, sans données médicales réelles |
| `docs/` | Audit, contrat, cadrage, protocole et mesures réellement exécutées |
| `data/`, `resultats/` | Données et exports locaux ignorés par Git |

Les quatre dépendances directes sont NumPy, pandas, SciPy et defusedxml, figées dans `requirements.txt`. `unittest`, JSON, CSV, ZIP et HTTP utilisent la bibliothèque standard. NetworkX, Neo4j, PyTorch, ProbLog, Streamlit et Jupyter ne sont pas requis pour cette brique.

## Choix de recherche

1. Repérage déterministe par plus longue correspondance des noms du graphe et variantes. Les synonymes manuels sont des aides linguistiques héritées à relire, pas des équivalences cliniques certifiées. Les homonymes de même type sont exclus au lieu de sélectionner arbitrairement un identifiant. L'appariement approché est désactivé par défaut ; `--fuzzy` l'active expérimentalement avec un avertissement dans le résultat.
2. Analyse en plan typé : traitements, palliation, symptômes, maladies proches, effets indésirables, contraintes communes et classes pharmacologiques. Les questions anglaises du jeu fourni constituent le périmètre validé. Français, négations, disjonctions, posologies et contraintes reconnues mais non consommées sont refusés. Le parseur à règles ne couvre pas tout le langage naturel : une formulation inconnue reste un risque, à documenter et tester avant élargissement.
3. Extraction ciblée : les voisinages filtrés/jointures réalisent les motifs à un ou deux sauts. Pour `Disease <-CtD- Compound -CcSE-> Side Effect`, chaque composé exige les **deux** arêtes. Une preuve à deux arêtes n'est jamais coupée par le budget. Le parcours générique `chemins()` est également disponible, avec limite de profondeur et d'expansions ; il n'est pas nécessaire aux jointures typées du moteur principal.
4. MedQuAD : recherche BM25 restreinte aux focus/synonymes des entités ; repli global explicitement étiqueté si nécessaire. Le même corpus, même BM25, même nombre maximal de passages et même plafond de contexte servent au RAG de référence. Un passage proche lexicalement ne prouve pas à lui seul une relation.
5. Contexte : maximum 100 triplets, 3 passages, 12 000 caractères par défaut. Deux tiers du plafond sont réservés aux preuves du graphe quand le texte est activé. Les preuves/passages trop grands sont omis avec diagnostic, sans découpe trompeuse. Ce plafond en caractères n'est pas une garantie de nombre de jetons pour tous les modèles.

`CtD` (traite) et `CpD` (soulage) restent distincts. `DpS` et `DrD` sont des associations, pas une preuve de causalité. Les traitements d'une maladie proche ne deviennent pas des traitements de la maladie demandée. **Absent du graphe ≠ faux.** Le score de recherche est une heuristique de disponibilité de preuves, jamais une probabilité de justesse ni un score clinique calibré.

## Validation et limites des résultats

Validation effectuée le 15 octobre 2026, Python 3.12.3, Windows : **16 tests unitaires réussis**, préparation complète de **8 206 nœuds, 145 018 arêtes, 38 810 passages**, exécution de la CLI et **160 recherches** (20 questions × 2 formulations × 4 configurations).

| Mesure de recherche | GraphRAG | Sans synonymes | Un saut seulement |
|---|---:|---:|---:|
| Plan exact, 40 formulations | 97,5 % | 55 % | 97,5 % |
| Rappel moyen des arêtes de référence, 32 cas avec preuves | 96,875 % | 63,54 % | 37,5 % |

Les triplets restitués correspondent aux arêtes du graphe dans tous les contextes non vides contrôlés. Ce contrôle mesure la traçabilité, **pas** la vérité clinique ni la fidélité d'une réponse générée. Les huit cas sans preuve de référence ne gonflent pas artificiellement le rappel. Les références structurées viennent des plans canoniques fournis, avec un oracle distinct du parseur testé. Les corrections cliniques externes de `questions.json` restent des annotations héritées, non des arêtes ajoutées au graphe.

Le seul échec de plan GraphRAG du jeu fourni est Q11 paraphrasée (« MS »), abréviation ambiguë volontairement non liée. Le jeu est petit, connu du code initial et utilisé pendant le développement : ces résultats sont descriptifs, **pas une validation indépendante**. Préparer un jeu tenu à l'écart avant toute conclusion de généralisation.

La référence RAG produit les passages et contextes pour les mêmes 20 questions. Le rappel de triplets n'est pas une métrique applicable au RAG texte et reste `null`. Les fichiers `passage_judgments.csv` et `contexts.jsonl` permettent d'annoter la pertinence et le soutien des réponses ; **la supériorité clinique de GraphRAG sur RAG n'est pas démontrée par cette brique seule**. Voir [docs/EVALUATION.md](docs/EVALUATION.md) pour terminer honnêtement les exigences collectives.

## Sources, attribution et périmètre académique

- [Hetionet](https://github.com/hetio/hetionet) : jeu de données et schéma ; [article eLife](https://doi.org/10.7554/eLife.26726). Révision dans le manifeste. Les TSV ne donnent pas la provenance détaillée de chaque arête : celle exportée ici est au niveau de la relation.
- [hetnetpy](https://github.com/hetio/hetnetpy) : bibliothèque de graphes hétérogènes, distincte du jeu de données. Consultée ; non nécessaire comme dépendance pour ces six relations et ces jointures.
- [MedQuAD](https://github.com/abachaa/MedQuAD) : corpus et conditions d'utilisation ; collections 1 à 9 utilisées. Le code n'attribue pas une licence unique à tous les contenus sources et ne republie pas les corpus.
- Supports locaux IA Hybride, chapitres 1–4 : triplets et logique, RAG/GraphRAG, évaluation séparée recherche/génération, calibration, humain dans la boucle. S2_demo_RAG est le point d'appui direct pour BM25, contexte sourcé et abstention. S1 éclaire les représentations/graphes ; S3 illustre l'ablation et la séparation entre perception et règles, sans imposer MNIST/ProbLog à cette partie.
- Base principale : code `sujet5_graphrag` fourni par un membre de l'équipe. Modules de recherche adaptés ; empreintes originales dans `docs/original_hashes.json`. Le dépôt distant initial (`8337565`) ne contenait qu'une structure de dossiers. Les autres briques restent dans l'original et dans le travail de leurs responsables.
- Assistance de code : la base déclare une assistance Claude (Anthropic). L'audit, les adaptations, les tests et cette documentation ont été préparés avec **OpenAI Codex**. Leur exécution par l'assistant ne remplace pas la relecture et l'appropriation par le trinôme.

## Git et livraison

Branche demandée : `master`, basée sur l'historique de `main` du dépôt de l'équipe. Aucun force-push ; aucun secret, corpus, environnement virtuel, cache pickle ou résultat contenant les passages complets n'est ajouté. Seuls code, tests, documentation, questions et mesures synthétiques sont versionnés. Le dossier initial sur le Bureau est conservé.

Avant une publication ultérieure : exécuter les tests, inspecter `git diff --cached`, contrôler les fichiers ajoutés et utiliser `git push -u origin master`. Ne pas exécuter l'ancien `creer_arborescence.py` : il réécrirait les dépendances et fichiers de configuration.
