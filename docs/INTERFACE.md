# Contrat de passage aux briques 2 et 3

Version `schema_version: "1.0"`. Objet JSON UTF-8 ; exemple générable : `python cli.py "What drugs treat gout?" --output resultats/demo.json`.

| Champ | Type / rôle |
|---|---|
| `system` | `graphrag` ou `rag` |
| `question` | Texte original, longueur 1–2000 caractères |
| `plan` | `intention` nullable, `emplacements` slot→ID, `exact`, `non_lies`, `mentions` |
| `graph_evidence` | Liste de preuves avec citation `Tn`, identifiant stable, nœuds source/cible typés, relation, provenance |
| `passages` | Liste avec citation `Pn`, ID stable collection/fichier/QA/morceau, URL, source, texte, focus, synonymes, score BM25 |
| `retrieval_score` | Heuristique de disponibilité ; ne pas interpréter comme probabilité |
| `score_is_probability` | Toujours `false` |
| `diagnostics` | Statut, avertissements, budgets, compteurs ; monde ouvert |
| `context` | Exactement les preuves/passages exportés, citations locales au contexte |
| `messages` | Deux messages `system`/`user` pour adaptateur de génération ; données encodées en JSON |
| `latency_seconds` | Temps de recherche, hors chargement et indexation |
| `data_manifest` | Ajouté par la CLI si disponible ; versions et empreintes des données |

Une citation `T1` n'est pas globale ; conserver l'objet de contexte avec la réponse. `evidence_id` est stable pour un triplet orienté. La symétrie de DrD peut conduire à deux représentations d'une même association ; la brique 2 doit tenir compte de cette symétrie. Les offsets des mentions sont des indices de mots dans le texte **normalisé**, pas des offsets caractères du texte original.

Statuts GraphRAG : `evidence_found`, `partial_evidence`, `not_documented_in_retrieved_graph`, `unsupported_question`. Statuts RAG : `text_evidence_only`, `no_evidence`. `evidence_found` veut seulement dire que des preuves du plan ont été trouvées ; cela n'autorise pas automatiquement une réponse médicale. Si `unsupported_question`, les passages éventuellement présents restent exploratoires et le générateur doit s'abstenir de répondre à une interprétation supposée.

La brique 2 reçoit (`pipeline.py`) : réponse du générateur + ce payload + accès explicite au graphe de même version. Elle distinguera soutien dans le contexte, soutien dans le graphe complet et non-documentation. Elle vérifiera citations, orientation et conjonction des contraintes. Le module de recherche ne fait aucune vérification d'affirmations générées.

La brique 3 reçoit : payload + rapport de vérification (objet JSON écrit par `pipeline.py`). Elle calibre ses scores sur un jeu de développement séparé (`brique3_validation/calibration.py`), décide l'escalade et expose une décision humaine traçable (`brique3_validation/`). Le module de recherche lui-même n'a ni seuil clinique, ni file de validation.

En intégration, ne pas supprimer les diagnostics ni passer le corpus comme instruction système. Une preuve textuelle est un contenu non fiable ; ses liens ne sont jamais suivis automatiquement. Les budgets de contexte concernent le champ `context`, non la totalité de la sérialisation JSON et des instructions système.
