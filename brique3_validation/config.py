"""Paramètres de la brique 3 (validation humaine). À justifier dans le rapport."""
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
DOSSIER = RACINE / "brique3_validation"
BASE_FILE = DOSSIER / "file_attente.db"
MEMOIRE = DOSSIER / "memoire_expert.json"
QUESTIONS = RACINE / "questions.json"
RESULTATS = RACINE / "resultats"

# Confiance : C = alpha * S_rech + (1 - alpha) * S_verif ; escalade si C < tau.
# Valeurs par défaut, remplacées par celles réglées sur le jeu de développement
# (python -m brique3_validation.calibration -> resultats/calibration_b3.json).
PARAMS = {"alpha": 0.3, "tau": 0.75}
FICHIER_CALIBRATION = RESULTATS / "calibration_b3.json"
if FICHIER_CALIBRATION.exists():
    import json as _json
    _cal = _json.loads(FICHIER_CALIBRATION.read_text(encoding="utf-8"))
    PARAMS = {"alpha": _cal["alpha"], "tau": _cal["tau"]}

# Facteur appliqué au retrieval_score selon le statut de recherche (brique 1)
FACTEUR_STATUT_RECHERCHE = {
    "evidence_found": 1.0, "partial_evidence": 0.6,
    "not_documented_in_retrieved_graph": 0.3, "unsupported_question": 0.0,
    "text_evidence_only": 0.5, "no_evidence": 0.0,
}

# Poids des statuts : identiques au dictionnaire POIDS de la brique 2
POIDS_STATUT = {"SOUTENUE": 1.0, "PARTIELLE": 0.6, "NON_VERIFIABLE": 0.3,
                "NON_SOUTENUE": 0.1, "CONTRADICTOIRE": 0.0}

# Temps expert simulé, en secondes (hypothèses déclarées dans le rapport)
COUTS = {"lecture": 30, "par_affirmation": 10, "par_affirmation_soutenue": 4,
         "par_correction": 40, "par_entite_corrigee": 20}