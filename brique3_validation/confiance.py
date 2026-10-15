"""Score de confiance et décision : livrer ou escalader vers l'expert."""
from brique3_validation.config import PARAMS, FACTEUR_STATUT_RECHERCHE, POIDS_STATUT

INCONNU = (None, "", "?")


def score_recherche(o):
    base = o.get("retrieval_score") or 0.0
    facteur = FACTEUR_STATUT_RECHERCHE.get(o.get("statut_recherche"), 0.5)
    exact = 1.0 if o.get("plan_exact", True) else 0.7
    return max(0.0, min(1.0, base * facteur * exact))


def score_verification(o):
    affs = o.get("affirmations", [])
    if o.get("score_verification_b2") is not None:
        s = o["score_verification_b2"]
    elif affs:
        s = sum(POIDS_STATUT.get(a.get("statut"), 0.3) for a in affs) / len(affs)
    else:
        s = 0.0
    if o.get("completude") is not None:
        s *= 0.7 + 0.3 * o["completude"]
    return max(0.0, min(1.0, s))


def regles_strictes(o):
    """Renvoie (raison, priorité) si une règle impose l'escalade, sinon (None, None)."""
    affs = o.get("affirmations", [])
    drapeaux = set(o.get("drapeaux", []))
    if o.get("erreur"):
        return f"Erreur dans le pipeline : {o['erreur']}", 0
    if any(a.get("statut") == "CONTRADICTOIRE" for a in affs):
        return "Affirmation contredite par le graphe", 0
    if o.get("statut_recherche") == "unsupported_question" or "question_non_comprise" in drapeaux:
        return "Question non comprise ou hors du périmètre", 1
    if o.get("non_lies") or "entite_hors_graphe" in drapeaux:
        return "Entité de la question non reconnue", 1
    if any(a.get("sujet") in INCONNU or a.get("objet") in INCONNU for a in affs):
        return "Entité de la réponse non reconnue", 1
    if any(a.get("statut") == "NON_SOUTENUE" for a in affs):
        return "Affirmation non soutenue par le graphe", 1
    if "element_non_conforme" in drapeaux:
        return "Élément ne respectant pas toutes les contraintes (R10)", 1
    if o.get("abstention"):
        return "Le générateur s'abstient de répondre", 2
    if not affs:
        return "Aucune affirmation vérifiable", 1
    return None, None


def decider(o, params=PARAMS, mode="complet"):
    """mode : 'recherche' | 'verification' | 'combine' (sans règles) | 'complet' (avec règles)."""
    sr, sv = score_recherche(o), score_verification(o)
    if mode == "recherche":
        c = sr
    elif mode == "verification":
        c = sv
    else:
        c = params["alpha"] * sr + (1 - params["alpha"]) * sv
    raison, priorite = regles_strictes(o) if mode == "complet" else (None, None)
    if raison is None and c < params["tau"]:
        raison, priorite = f"Confiance faible ({c:.2f} < {params['tau']})", 2
    o.update({"score_recherche": round(sr, 3), "score_verification": round(sv, 3),
              "confiance": round(c, 3), "decision": "ESCALADEE" if raison else "LIVREE",
              "raison": raison, "priorite": priorite})
    return o