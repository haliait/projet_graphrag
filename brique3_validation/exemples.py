"""Fabrique 4 objets d'exemple au format de la brique 3 (tests sans pipeline)."""
import json
from hetionet_utils import charger_graphe
from brique3_validation.config import RESULTATS
from brique3_validation.expert_simule import ExpertSimule

g = charger_graphe()
ex = ExpertSimule(g)


def objet(qid, formulation="question", **kw):
    q, ref = ex.q[qid], ex.reference(qid)
    o = {"id": qid, "formulation": formulation, "systeme": "graphrag",
         "question": q["question"] if formulation == "question" else q["paraphrase"],
         "sauts": q["sauts"], "categorie": q["categorie"], "intention": q["plan"]["intention"],
         "emplacements": ref["emplacements"], "plan_exact": True, "non_lies": [],
         "statut_recherche": "evidence_found", "retrieval_score": 1.0, "preuves": [], "passages": [],
         "reponse": "", "generateur": "exemple", "affirmations": [], "elements": [],
         "score_verification_b2": None, "completude": 1.0, "drapeaux": [], "abstention": False, "oui_non": None}
    o.update(kw)
    return o


def aff(s, r, o, statut, regle, nie=False):
    return {"sujet": s, "relation": r, "objet": o, "nie": nie, "phrase": f"{s} {r} {o}",
            "statut": statut, "regle": regle, "explication": "", "dans_contexte": True}


r1 = ex.reference("Q01")
maladie = g.nom[r1["emplacements"]["D"]]
bons = r1["affichage"]
e6 = ex.reference("Q06")["emplacements"]
warfarine, saignement = g.nom[e6["C"]], g.nom[e6["SE"]]

exemples = [
    objet("Q01", reponse=", ".join(bons), elements=bons,
          affirmations=[aff(c, "CtD", maladie, "SOUTENUE", "R1") for c in bons]),
    objet("Q01", "paraphrase", reponse=", ".join(bons + ["Warfarin"]), elements=bons + ["Warfarin"],
          affirmations=[aff(c, "CtD", maladie, "SOUTENUE", "R1") for c in bons]
                       + [aff("Warfarin", "CtD", maladie, "NON_SOUTENUE", "R7")]),
    objet("Q06", reponse=f"Yes, {warfarine} can cause {saignement}.", oui_non=True,
          statut_recherche="not_documented_in_retrieved_graph", retrieval_score=0.3,
          affirmations=[aff(warfarine, "CcSE", saignement, "NON_VERIFIABLE", "R5")]),
    objet("Q09", reponse="The context does not answer this question.", abstention=True,
          statut_recherche="unsupported_question", retrieval_score=0.0, non_lies=[{"texte": "?"}]),
]
RESULTATS.mkdir(exist_ok=True)
(RESULTATS / "exemples_b3.json").write_text(json.dumps(exemples, ensure_ascii=False, indent=2), encoding="utf-8")
print("Écrit : resultats/exemples_b3.json")