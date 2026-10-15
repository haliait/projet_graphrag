"""Expert simulé : graphe complet + références corrigées de questions.json."""
import json
from evaluation import reference_edges
from brique3_validation.config import COUTS, QUESTIONS

TYPE_REPONSE = {"treat_disease": "Compound", "palliates": "Compound", "symptoms_of": "Symptom",
                "resembles": "Disease", "drugs_for_resembling": "Compound", "shared_symptoms": "Symptom",
                "treat_and_cause": "Compound", "treat_both": "Compound", "class_treat": "Compound"}


def charger_questions():
    d = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d


def noms(valeurs):
    """Liste de noms (chaînes ou dictionnaires) -> {nom en minuscules: nom original}."""
    out = {}
    for v in valeurs or []:
        n = (v.get("nom") or v.get("name") or "") if isinstance(v, dict) else str(v)
        if n:
            out[n.lower()] = n
    return out


class ExpertSimule:
    def __init__(self, g, questions=None, couts=COUTS):
        self.g, self.couts = g, couts
        self.q = {q["id"]: q for q in (questions or charger_questions())}
        self.par_nom = {}
        for n, nom in g.nom.items():
            self.par_nom.setdefault(nom.lower(), []).append(n)
        self._refs = {}

    # ---- outils ----
    def nom(self, x):
        return self.g.nom.get(x, str(x)).lower() if x not in (None, "?") else ""

    def ids(self, x):
        if x in (None, "", "?"):
            return []
        return [x] if x in self.g.nom else self.par_nom.get(str(x).lower(), [])

    # ---- référence ----
    def reference(self, qid):
        if qid in self._refs:
            return self._refs[qid]
        q = self.q[qid]
        if q.get("hors_graphe"):
            ref = {"type": "escalade", "valeur": None, "affichage": [], "emplacements": {}}
        else:
            edges, e = reference_edges(q, self.g)
            it = q["plan"]["intention"]
            if it == "causes_yesno":
                valeur = bool(q.get("reference_oui_non", bool(edges)))
                ref = {"type": "oui_non", "valeur": valeur, "affichage": [], "emplacements": e}
            else:
                t, vus = TYPE_REPONSE[it], set(e.values())
                attendus = {self.g.nom[n].lower(): self.g.nom[n] for s, r, o in edges for n in (s, o)
                            if self.g.type.get(n) == t and n not in vus}
                attendus.update(noms(q.get("ajouts")))
                for k in noms(q.get("retraits")):
                    attendus.pop(k, None)
                ref = {"type": "liste", "valeur": set(attendus), "affichage": sorted(attendus.values()),
                       "emplacements": e}
        self._refs[qid] = ref
        return ref

    def reponse_reference(self, o):
        if o["id"] not in self.q:
            vraies = [a.get("phrase", "") for a in o.get("affirmations", [])
                      if self.fait_vrai(a, None) != bool(a.get("nie"))]
            return "; ".join(vraies) or "Aucun élément documenté."
        ref = self.reference(o["id"])
        if ref["type"] == "escalade":
            return "Question hors du périmètre du graphe : renvoyée à un spécialiste."
        if ref["type"] == "oui_non":
            source = self.q[o["id"]].get("source")
            return ("Oui" if ref["valeur"] else "Non") + (f" (source : {source})" if source else "")
        return ", ".join(ref["affichage"]) or "Aucun élément documenté dans le graphe."

    # ---- vérité ----
    def fait_vrai(self, a, qid):
        """Le fait POSITIF (sujet, relation, objet) est-il vrai pour l'expert ?"""
        r = a.get("relation")
        for s in self.ids(a.get("sujet")):
            for o in self.ids(a.get("objet")):
                if self.g.a_arete(s, r, o) or (r == "DrD" and self.g.a_arete(o, r, s)):
                    return True
        if qid in self.q:
            ref = self.reference(qid)
            if ref["type"] == "oui_non":
                e = ref["emplacements"]
                if {self.nom(a.get("sujet")), self.nom(a.get("objet"))} == {self.nom(e.get("C")), self.nom(e.get("SE"))}:
                    return ref["valeur"]
            ajouts = noms(self.q[qid].get("ajouts"))
            if self.nom(a.get("sujet")) in ajouts or self.nom(a.get("objet")) in ajouts:
                return True
        return False

    def prediction(self, o):
        if o.get("abstention"):
            return {"type": "abstention"}
        if o.get("oui_non") is not None:
            return {"type": "oui_non", "valeur": bool(o["oui_non"])}
        return {"type": "liste", "valeur": {self.nom(x) for x in o.get("elements", [])} - {""}}

    def est_correcte(self, o):
        if o.get("source") == "memoire":
            return True
        if o["id"] not in self.q:
            affs = o.get("affirmations", [])
            return bool(affs) and all(self.fait_vrai(a, None) != bool(a.get("nie")) for a in affs)
        ref, pred = self.reference(o["id"]), self.prediction(o)
        if ref["type"] == "escalade":
            return pred["type"] == "abstention"
        if ref["type"] == "oui_non":
            return pred["type"] == "oui_non" and pred["valeur"] == ref["valeur"]
        if pred["type"] == "abstention":
            return not ref["valeur"]
        return pred.get("valeur") == ref["valeur"]

    # ---- traitement d'une réponse escaladée ----
    def traiter(self, o):
        """Renvoie (statut, reponse_finale, corrections, temps_en_secondes)."""
        qid = o["id"]
        corrections = {"affirmations": [], "synonymes": {}}
        temps, n_corr = self.couts["lecture"], 0
        for a in o.get("affirmations", []):
            temps += (self.couts["par_affirmation_soutenue"] if a.get("statut") == "SOUTENUE"
                      else self.couts["par_affirmation"])
            if a.get("sujet") in (None, "", "?") or a.get("objet") in (None, "", "?"):
                n_corr += 1
                continue
            fait = self.fait_vrai(a, qid)
            vraie = fait != bool(a.get("nie"))
            if a.get("statut") != "SOUTENUE" or not vraie:
                corrections["affirmations"].append({"triplet": [a["sujet"], a["relation"], a["objet"]],
                                                    "vraie": fait})
            if not vraie:
                n_corr += 1
        n_ent = len(o.get("non_lies") or [])
        if qid in self.q and n_ent:
            cibles = list(self.reference(qid)["emplacements"].values())
            if len(cibles) == 1:
                for m in o["non_lies"]:
                    corrections["synonymes"][m.get("texte") if isinstance(m, dict) else str(m)] = cibles[0]
        if not self.est_correcte(o):
            n_corr = max(n_corr, 1)
        temps += self.couts["par_correction"] * n_corr + self.couts["par_entite_corrigee"] * n_ent
        statut = "validee" if n_corr == 0 and n_ent == 0 else "corrigee"
        return statut, self.reponse_reference(o), corrections, temps


if __name__ == "__main__":
    from hetionet_utils import charger_graphe
    ex = ExpertSimule(charger_graphe())
    for qid, q in ex.q.items():
        ref = ex.reference(qid)
        print(f"{qid} [{q['categorie']}] {ref['type']:8s} {ex.reponse_reference({'id': qid})[:110]}")