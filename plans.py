"""Analyse de la question en « plan de requête » sur le graphe, et exécution du plan.

Un plan = une intention + des emplacements typés (entités du graphe) + des contraintes que
doit vérifier la variable réponse X. Exemple, « Which drugs that treat rheumatoid arthritis are
known to cause hepatotoxicity? » :
    intention  treat_and_cause
    X : Compound
    contraintes  X -CtD-> rheumatoid arthritis   ET   X -CcSE-> Hepatotoxicity      (2 sauts)

Le plan sert à trois endroits : la recherche (quelles relations extraire), la génération par
gabarit (quelles phrases écrire) et la vérification (complétude, conformité à la question).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from entites import normaliser

# intention -> (type de la réponse, emplacements attendus, contraintes, nb de sauts)
# contrainte : (relation, sens, emplacement) ; sens "vers" = X -rel-> e ; "depuis" = e -rel-> X
INTENTIONS = {
    "treat_disease":        ("Compound", ["D"], [("CtD", "vers", "D")], 1),
    "palliates":            ("Compound", ["D"], [("CpD", "vers", "D")], 1),
    "symptoms_of":          ("Symptom", ["D"], [("DpS", "depuis", "D")], 1),
    "resembles":            ("Disease", ["D"], [("DrD", "depuis", "D")], 1),
    "diseases_treated_by":  ("Disease", ["C"], [("CtD", "depuis", "C")], 1),
    "causes_yesno":         (None, ["C", "SE"], [], 1),
    "treat_and_cause":      ("Compound", ["D", "SE"], [("CtD", "vers", "D"), ("CcSE", "vers", "SE")], 2),
    "drugs_for_resembling": ("Compound", ["D"], [("CtD", "vers", "D'"), ("DrD", "D'", "D")], 2),
    "shared_symptoms":      ("Symptom", ["D", "D2"], [("DpS", "depuis", "D"), ("DpS", "depuis", "D2")], 2),
    "treat_both":           ("Compound", ["D", "D2"], [("CtD", "vers", "D"), ("CtD", "vers", "D2")], 2),
    "class_treat":          ("Compound", ["P", "D"], [("PCiC", "depuis", "P"), ("CtD", "vers", "D")], 2),
}
TYPE_EMPLACEMENT = {"D": "Disease", "D2": "Disease", "C": "Compound", "SE": "Side Effect",
                    "P": "Pharmacologic Class"}
RELATIONS_PERTINENTES = {
    "treat_disease": {"CtD"}, "palliates": {"CpD"}, "symptoms_of": {"DpS"}, "resembles": {"DrD"},
    "diseases_treated_by": {"CtD"}, "causes_yesno": {"CcSE"}, "treat_and_cause": {"CtD", "CcSE"},
    "drugs_for_resembling": {"DrD", "CtD"}, "shared_symptoms": {"DpS"}, "treat_both": {"CtD"},
    "class_treat": {"PCiC", "CtD"},
}

R_TRAITE = r"\b(treat|treats|treated|treating|treatment|treatments|therap|indicated|used for|used to|used in|medication|medications|medicine|medicines|drug|drugs|for)\b"
R_CAUSE = r"\b(cause|causes|caused|causing|induce|induces|side effect|side effects|adverse|lead to|leads to|provoke|provokes|damage|toxic|hepatotoxic)\b"
R_SYMPT = r"\b(symptom|symptoms|sign|signs|present|presents|manifestation|manifestations|in common)\b"
R_RESSEMBLE = r"\b(resemble|resembles|resembling|similar|related|like)\b"
R_SOULAGE = r"\b(relieve|relieves|relief|palliat\w*|symptomatic)\b"


@dataclass
class Plan:
    intention: str | None
    emplacements: dict = field(default_factory=dict)   # nom -> id du nœud
    exact: bool = True                                  # toutes les entités repérées exactement ?
    non_lies: list = field(default_factory=list)       # mentions repérées mais de type incompatible
    mentions: list = field(default_factory=list)

    @property
    def type_reponse(self):
        return INTENTIONS[self.intention][0] if self.intention else None

    @property
    def sauts(self):
        return INTENTIONS[self.intention][3] if self.intention else 0

    def signature(self):
        """Clé canonique de la question : sert à réutiliser les corrections de l'expert."""
        if not self.intention:
            return None
        sig = self.intention + "|" + "|".join(f"{k}={v}" for k, v in sorted(self.emplacements.items()))
        if not self.complet():
            # entité hors graphe : la signature garde le texte non relié (ex. « fibromyalgia »)
            if not self.non_lies:
                return None
            sig += "|?" + "|?".join(sorted(self.non_lies))
        return sig

    def complet(self):
        return self.intention is not None and all(e in self.emplacements for e in INTENTIONS[self.intention][1])


def analyser_question(question: str, dico) -> Plan:
    """Repère les entités et choisit l'intention par mots déclencheurs + types des entités."""
    q = " " + normaliser(question) + " "
    # Reject unsupported logic instead of silently answering a weaker question.
    if re.search(r"\b(not|never|without|neither|nor|except|excluding|or|contraindicated|contraindication|dosage|dose)\b", q):
        return Plan(None, non_lies=["unsupported_logic"])
    if re.search(r"\b(quels|quelles|quel|quelle|traitent|medicaments|maladie|effets)\b", q):
        return Plan(None, non_lies=["unsupported_language_use_english"])
    mentions = dico.reperer(question)
    types_dispo = [set(m.candidats) for m in mentions]

    def premieres(type_, n=1, exclure=()):
        res = [m for m in mentions if type_ in m.candidats and m not in exclure]
        return res[:n]

    has = lambda t: any(t in s for s in types_dispo)
    nb_maladies = sum(1 for s in types_dispo if "Disease" in s)
    traite, cause = re.search(R_TRAITE, q), re.search(R_CAUSE, q)
    sympt, ressemble, soulage = re.search(R_SYMPT, q), re.search(R_RESSEMBLE, q), re.search(R_SOULAGE, q)
    oui_non = re.match(r"\s*(does|do|can|could|is|are|may|might)\b", q)

    intention, empl = None, {}
    # Une mention ambiguë Maladie / Effet est lue comme effet si elle suit un verbe de cause.
    def mention_effet():
        if not cause:
            return None
        apres = [m for m in mentions if "Side Effect" in m.candidats]
        return apres[-1] if apres else None

    se = mention_effet()
    maladies = [m for m in mentions if "Disease" in m.candidats and m is not se]
    composes = [m for m in mentions if "Compound" in m.candidats]
    classes = [m for m in mentions if "Pharmacologic Class" in m.candidats]

    if oui_non and composes and se is not None:
        intention, empl = "causes_yesno", {"C": composes[0], "SE": se}
    elif sympt and len(maladies) >= 2:
        intention, empl = "shared_symptoms", {"D": maladies[0], "D2": maladies[1]}
    elif sympt and maladies and not soulage and not re.search(r"\b(drugs?|medic\w*|treat\w*)\b", q):
        intention, empl = "symptoms_of", {"D": maladies[0]}
    elif soulage and maladies:
        intention, empl = "palliates", {"D": maladies[0]}
    elif ressemble and maladies and re.search(r"\b(drug|drugs|medication|medications|medicine|medicines|treat|treats|used)\b", q):
        intention, empl = "drugs_for_resembling", {"D": maladies[0]}
    elif ressemble and maladies:
        intention, empl = "resembles", {"D": maladies[0]}
    elif classes and maladies:
        intention, empl = "class_treat", {"P": classes[0], "D": maladies[0]}
    elif se is not None and maladies:
        intention, empl = "treat_and_cause", {"D": maladies[0], "SE": se}
    elif len(maladies) >= 2 and traite:
        intention, empl = "treat_both", {"D": maladies[0], "D2": maladies[1]}
    elif composes and not maladies and traite:
        intention, empl = "diseases_treated_by", {"C": composes[0]}
    elif maladies and traite:
        intention, empl = "treat_disease", {"D": maladies[0]}
    elif traite and not maladies:
        # entité nommée comme une maladie mais absente des maladies du graphe (ex. « fibromyalgia »
        # n'existe qu'en effet indésirable) : intention reconnue, emplacement non rempli.
        intention, empl = "treat_disease", {}

    # An unresolved cause must not turn into an unconstrained treatment request.
    if cause and se is None:
        return Plan(None, mentions=mentions, non_lies=["unresolved_side_effect"])
    if len(maladies) > 2 or len(composes) > 1:
        return Plan(None, mentions=mentions, non_lies=["too_many_entities"])
    plan = Plan(intention, mentions=mentions)
    for nom, m in empl.items():
        t = TYPE_EMPLACEMENT[nom]
        if t in m.candidats:
            plan.emplacements[nom] = m.candidats[t]
            plan.exact &= m.exact
    plan.non_lies = [m.texte for m in mentions if not any(m is x for x in empl.values())]
    if plan.non_lies and plan.complet():
        return Plan(None, mentions=mentions, non_lies=["unused_entity_constraints"] + plan.non_lies)
    if re.search(r"\bboth\b", q) and len(maladies) != 2:
        return Plan(None, mentions=mentions, non_lies=["unresolved_second_disease"])
    return plan


def executer(plan: Plan, g):
    """Ensemble des ids qui satisfont le plan dans le graphe g (graphe complet ou sous-graphe de contexte).
    Pour causes_yesno, renvoie {True} si l'arête existe, set() sinon."""
    if not plan.complet():
        return set()
    e = plan.emplacements
    it = plan.intention
    if it == "causes_yesno":
        return {True} if g.a_arete(e["C"], "CcSE", e["SE"]) else set()
    if it == "drugs_for_resembling":
        res = set()
        for d2 in g.successeurs(e["D"], "DrD"):
            res |= g.predecesseurs(d2, "CtD")
        return res
    res = None
    for rel, sens, nom in INTENTIONS[it][2]:
        cands = g.predecesseurs(e[nom], rel) if sens == "vers" else g.successeurs(e[nom], rel)
        res = cands if res is None else res & cands
    return res or set()


def intermediaires(plan: Plan, g, x):
    """Pour drugs_for_resembling : maladies proches de D traitées par x (sert aux explications)."""
    return {d2 for d2 in g.successeurs(plan.emplacements["D"], "DrD") if g.a_arete(x, "CtD", d2)}
