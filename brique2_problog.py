"""Brique 2, version ProbLog : mêmes règles que la version Python, pondérées (regles_verification.pl).

Pour une réponse : on génère les faits utiles (affirmations, arêtes du sujet, couverture, effets
plus généraux, corrections de l'expert), on ajoute une règle element_ok/1 par élément de réponse,
et ProbLog calcule P(support) pour chaque affirmation et P(element_ok) pour chaque élément.
"""
from __future__ import annotations

import os

from problog import get_evaluatable
from problog.program import PrologString

ICI = os.path.dirname(os.path.abspath(__file__))
REGLES = open(os.path.join(ICI, "regles_verification.pl"), encoding="utf-8").read()


def atome(x):
    return "'" + str(x).replace("'", "\\'") + "'"


def programme(affirmations, verificateur, plan=None):
    g = verificateur.g
    faits, vus = [], set()

    def fait(f):
        if f not in vus:
            vus.add(f); faits.append(f)

    claims = {}
    for i, a in enumerate(affirmations):
        if a.sujet is None or a.objet is None or a.phrase == "(question)":
            continue
        c = f"c{i}"
        claims[c] = a
        r = a.relation.lower()
        fait(f"claim({c}, {atome(a.sujet)}, {r}, {atome(a.objet)}).")
        if a.nie:
            fait(f"negated({c}).")
        if g.a_arete(a.sujet, a.relation, a.objet):
            fait(f"edge({atome(a.sujet)}, {r}, {atome(a.objet)}).")
        if a.relation == "CtD" and g.a_arete(a.sujet, "CpD", a.objet):
            fait(f"edge({atome(a.sujet)}, cpd, {atome(a.objet)}).")
        if verificateur.couverture(a.sujet, a.relation):
            fait(f"covered({atome(a.sujet)}, {r}).")
        if a.relation == "CcSE":
            for e in verificateur.effet_plus_general(a.sujet, a.objet):
                fait(f"general({atome(a.objet)}, {atome(e)}).")
                fait(f"edge({atome(a.sujet)}, ccse, {atome(e)}).")
        mem = verificateur.memoire
        if mem is not None:
            v = mem.fait(a.sujet, a.relation, a.objet)
            if v is not None:
                fait(f"expert_{'ok' if v[0] else 'ko'}({atome(a.sujet)}, {r}, {atome(a.objet)}).")
    # éléments de réponse : conjonction de leurs contraintes
    elements = {}
    if plan is not None and plan.type_reponse:
        for c, a in claims.items():
            for x in (a.sujet, a.objet):
                if g.type.get(x) == plan.type_reponse and x not in plan.emplacements.values():
                    elements.setdefault(x, []).append(c)
    regles_el = []
    for j, (x, cs) in enumerate(elements.items()):
        regles_el.append(f"element_ok(e{j}) :- " + ", ".join(f"support({c})" for c in cs) + ".")
    requetes = [f"query(support({c})). query(contradiction({c}))." for c in claims]
    requetes += [f"query(element_ok(e{j}))." for j in range(len(elements))]
    # faits sentinelles : déclarent chaque prédicat même quand il n'a aucune instance
    sentinelles = ["negated(aucun).", "edge(aucun, aucun, aucun).", "covered(aucun, aucun).",
                   "general(aucun, aucun).", "expert_ok(aucun, aucun, aucun).", "expert_ko(aucun, aucun, aucun)."]
    texte = REGLES + "\n" + "\n".join(sentinelles + faits + regles_el + requetes)
    return texte, claims, list(elements)


def verifier_problog(affirmations, verificateur, plan=None):
    """Renvoie ({id_affirmation: (P(support), P(contradiction))}, {element: P(element_ok)})."""
    texte, claims, elements = programme(affirmations, verificateur, plan)
    if not claims:
        return {}, {}
    res = get_evaluatable().create_from(PrologString(texte)).evaluate()
    par_nom = {str(k): v for k, v in res.items()}
    p_claims = {c: (par_nom.get(f"support({c})", 0.0), par_nom.get(f"contradiction({c})", 0.0)) for c in claims}
    p_elems = {x: par_nom.get(f"element_ok(e{j})", 0.0) for j, x in enumerate(elements)}
    return p_claims, p_elems


def statut_depuis_proba(p_support, p_contra):
    if p_contra > 0.5:
        return "CONTRADICTOIRE"
    if p_support >= 0.9:
        return "SOUTENUE"
    if p_support >= 0.5:
        return "PARTIELLE"
    if p_support >= 0.2:
        return "NON_VERIFIABLE"
    return "NON_SOUTENUE"
