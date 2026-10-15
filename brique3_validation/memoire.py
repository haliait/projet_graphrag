"""Réutilisation des corrections de l'expert :
1) réponses validées, indexées par le plan (intention + entités) : une paraphrase retombe dessus ;
2) faits validés / rejetés, transmis à la règle R8 de la brique 2 (Hetionet n'est jamais modifié) ;
3) synonymes proposés par l'expert pour les entités non reconnues."""
import copy, json
from brique3_validation.config import MEMOIRE

VIDE = {"reponses": {}, "faits_valides": [], "faits_rejetes": [], "synonymes": {}}


def signature(o):
    if not o.get("intention") or not o.get("emplacements"):
        return None
    return o["intention"] + "|" + "|".join(f"{k}={v}" for k, v in sorted(o["emplacements"].items()))


class Memoire:
    def __init__(self, chemin=MEMOIRE):
        self.chemin = chemin
        self.d = json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else copy.deepcopy(VIDE)
        for k, v in VIDE.items():
            self.d.setdefault(k, copy.deepcopy(v))

    def sauver(self):
        self.chemin.write_text(json.dumps(self.d, ensure_ascii=False, indent=2), encoding="utf-8")

    def reinitialiser(self):
        self.d = copy.deepcopy(VIDE)
        self.sauver()

    def faits(self):
        """(faits validés, faits rejetés) sous forme d'ensembles de triplets (sujet, relation, objet)."""
        return ({tuple(t) for t in self.d["faits_valides"]}, {tuple(t) for t in self.d["faits_rejetes"]})

    def appliquer(self, o):
        """Si une question de même plan a déjà été validée, on renvoie la réponse de l'expert."""
        sig = signature(o)
        if sig and sig in self.d["reponses"]:
            o.update({"reponse": self.d["reponses"][sig]["reponse"], "source": "memoire",
                      "confiance": 1.0, "decision": "LIVREE", "priorite": None,
                      "raison": "Réponse déjà validée par l'expert"})
            return True
        return False

    def reverifier(self, o):
        """Équivalent de R8 côté brique 3 (utile si la brique 2 n'a pas reçu la mémoire)."""
        valides, rejetes = self.faits()
        modifie = False
        for a in o.get("affirmations", []):
            t = (a.get("sujet"), a.get("relation"), a.get("objet"))
            if t in valides:
                a["statut"] = "CONTRADICTOIRE" if a.get("nie") else "SOUTENUE"
            elif t in rejetes:
                a["statut"] = "SOUTENUE" if a.get("nie") else "CONTRADICTOIRE"
            else:
                continue
            a["regle"], a["explication"], modifie = "R8", "Fait tranché par l'expert", True
        if modifie:
            o["score_verification_b2"] = None      # recalcul à partir des nouveaux statuts

    def enregistrer_correction(self, o, reponse_finale, corrections):
        sig = signature(o)
        if sig:
            self.d["reponses"][sig] = {"reponse": reponse_finale, "id": o["id"]}
        for c in corrections.get("affirmations", []):
            liste = "faits_valides" if c["vraie"] else "faits_rejetes"
            if c["triplet"] not in self.d[liste]:
                self.d[liste].append(c["triplet"])
        self.d["synonymes"].update(corrections.get("synonymes", {}))
        self.sauver()


class MemoirePourBrique2:
    """Objet attendu par Verificateur(memoire=...) de la brique 2 (règle R8) :
    fait(sujet, relation, objet) -> (vrai: bool, source: str) ou None."""

    def __init__(self, memoire):
        self.valides, self.rejetes = memoire.faits()

    def fait(self, s, r, o):
        if (s, r, o) in self.valides:
            return True, "expert"
        if (s, r, o) in self.rejetes:
            return False, "expert"
        return None