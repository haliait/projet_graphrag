# Audit du point de départ et décisions

La fiche de consignes a été traitée comme une spécification académique ; les commentaires du code fourni comme des assertions à vérifier. Aucun notebook ni script de la base n'a été exécuté avant inspection. Le cache pickle fourni n'a jamais été désérialisé.

| Constat | Adaptation |
|---|---|
| `hetionet_utils.py` existait déjà malgré son absence dans les ressources de cours | Réutilisation et correction du module de l'équipe, pas une dépendance cachée au module enseignant |
| `charger_graphe()` appelait `pickle.load` | Reconstruction depuis TSV/GZIP officiels, jamais d'exécution de cache |
| Parcours de voisins utilisant des ensembles non ordonnés | Tri déterministe, budgets explicites et borne d'exploration |
| Une limite de triplets pouvait couper un chemin à deux arêtes | Groupes de preuves atomiques ; diagnostic de troncature |
| Une question incomplète pouvait être réduite à une recherche de traitements | Refus des contraintes non résolues reconnues, entités ignorées, négations et disjonctions |
| Un même nom pouvait choisir arbitrairement un identifiant du même type | Exclusion des homonymes et inventaire des ambiguïtés |
| Appariement approché par défaut, acronyme MS, correspondance trop large beta blockers | Approché optionnel, suppression des deux correspondances à risque ; limitation documentée |
| `rag_classique.py` utilisait le dictionnaire et le plan du graphe | Référence réellement BM25 seul ; aucun graphe chargé en mode RAG |
| Score de recherche élevé possible sans arête | Score nul sans preuve ; score explicitement non calibré |
| Préparation exécutée à l'import, téléchargements sur main, pas de hash | Fonction main, commits figés, SHA256, temporaires, taille limitée |
| Corpus vide ou erreurs XML pouvaient être masqués | Échec explicite ; XML defusedxml ; IDs stables collection/fichier/QA/chunk |
| Génération simulée, vérification et validation intégrées | Modules exclus de cette branche ; interface documentée pour raccordement ultérieur |
| README initial annonçait des résultats et usages couvrant les trois briques | Nouvelle documentation limitée aux opérations réellement exécutées |

La base complète a été inventoriée : pipeline, générateurs gabarit/simulé/Ollama, vérificateurs Python/ProbLog, politique de validation, interfaces CLI/Streamlit, références, évaluation et figures. Leur rôle et leurs dépendances ont été examinés pour isoler la brique 1. Ils ne sont ni réimplémentés ni certifiés par cet audit. Les résultats préexistants ne sont pas utilisés comme preuve de validation de la nouvelle branche.

L'arborescence distante ne contenait que des dossiers vides, un dictionnaire vide et un script de création de structure ; aucun moteur de recherche à fusionner. `master` descend du commit initial de `main`. La structure plate des modules de recherche est conservée pour faciliter la reprise du code de l'équipe ; les coquilles vides des autres briques sont retirées uniquement sur cette branche.

## Risques résiduels à présenter

- Parseur lexical à intentions limitées ; anglais seulement. Il rejette plusieurs cas dangereux connus mais ne garantit pas la compréhension de toute phrase. Les unités/posologies, interactions, temporalité et décisions patient sont hors périmètre.
- Synonymes manuels hérités non exhaustifs et non validés individuellement par un expert ; supprimer un alias discutable est préférable à une équivalence inventée. Les questions et alias du point de départ sont déjà proches : risque d'optimisme sur le jeu fourni.
- Hetionet v1.0 est un instantané incomplet. Une arête SIDER est une relation de la base, pas une estimation actuelle de risque individuel. Le TSV ne porte pas la preuve documentaire détaillée de chaque arête.
- BM25 peut renvoyer des passages peu pertinents ; aucun jugement humain de pertinence n'est inventé. Le score BM25 n'est pas une confiance médicale.
- Le prompt réduit le mélange instructions/données, mais ne constitue pas une barrière de sécurité démontrée pour un LLM externe. Aucun agent outillé n'est connecté aux passages.
- Les hashes vérifient l'intégrité de versions fixées après leur récupération initiale ; ils ne certifient ni la vérité clinique ni la sécurité absolue des sources.

Les 16 tests ciblent des comportements qui pourraient perdre des contraintes, attribuer des preuves incorrectes ou donner une certitude injustifiée. Une revue par l'équipe reste nécessaire avant soutenance et extension.
