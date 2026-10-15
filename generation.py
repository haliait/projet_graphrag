"""Génération de la réponse à partir du payload de la brique 1.

- 'ollama'  : petit LLM local, température 0, modèle consigné dans chaque résultat ;
- 'gabarit' : réponse extractive, sans LLM (autorisée par le sujet si elle est déclarée) :
    * GraphRAG : les entités du type attendu présentes dans les preuves du graphe [Tn] ;
    * RAG classique : les entités du type attendu citées dans une phrase des passages [Pn]
      qui contient un mot déclencheur de la relation demandée (réponse extractive).
  Le même gabarit sert aux deux systèmes : seule la recherche change, ce qui isole l'apport du graphe.
Aucune bascule silencieuse de l'un vers l'autre : si Ollama ne répond pas, on s'arrête."""
import re

import requests

from plans import INTENTIONS

URL_OLLAMA = "http://localhost:11434/api/chat"
R_PHRASE = re.compile(r"(?<=[.!?])\s+")
# Mots qui, dans une phrase de passage, signalent la relation demandée (première contrainte du plan)
DECLENCHEURS_TEXTE = {
    "CtD": r"\b(treat\w*|therap\w*|medication\w*|medicine\w*|drug\w*|prescri\w*|indicated|manag\w*)\b",
    "CpD": r"\b(reliev\w*|relief|pain|symptom\w*|treat\w*|medication\w*)\b",
    "DpS": r"\b(symptom\w*|sign\w*|feel\w*|experienc\w*)\b",
    "DrD": r"\b(similar|resembl\w*|related|mistaken|confused)\b",
    "CcSE": r"\b(side effect\w*|cause\w*|risk\w*|adverse|lead\w* to|induc\w*)\b",
    "PCiC": r"\b(class|type|kind|group)\b",
}
ABSTENTION = "I don't know: the answer is not in the context."


class ErreurGeneration(RuntimeError):
    pass


def generer_ollama(payload, modele="qwen2.5:3b", timeout=600):
    try:
        r = requests.post(URL_OLLAMA, timeout=timeout, json={
            "model": modele, "messages": payload["messages"], "stream": False,
            "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 400}})
        r.raise_for_status()
    except requests.RequestException as e:
        raise ErreurGeneration(f"Ollama indisponible ou en erreur ({e}). "
                               "Lancez Ollama, ou utilisez --generateur gabarit.") from e
    return r.json()["message"]["content"].strip()


def generer_gabarit(ctx, g):
    """GraphRAG : réponse construite à partir des seules preuves du graphe présentes dans le contexte."""
    plan = ctx.plan
    if not plan.intention or not ctx.triplets:
        return ABSTENTION
    e = plan.emplacements
    if plan.intention == "causes_yesno":
        c, se = e.get("C"), e.get("SE")
        if (c, "CcSE", se) in ctx.triplets:
            return f"Yes, {g.nom[c]} can cause {g.nom[se]} [T{ctx.index_triplet(c, 'CcSE', se)}]."
        return "I don't know: the context does not state it."
    t = plan.type_reponse
    cites = {}
    for n, (u, r, v) in enumerate(ctx.triplets, 1):
        for x in (u, v):
            if g.type.get(x) == t and x not in e.values():
                cites.setdefault(g.nom[x], []).append(n)
    if not cites:
        return ABSTENTION
    return "The answer is:\n" + "\n".join(f"- {nom} " + "".join(f"[T{n}]" for n in cites[nom])
                                          for nom in sorted(cites))


def generer_gabarit_texte(ctx, g, plan, dico):
    """RAG classique : extraction depuis les passages. `plan` = lecture de la question (ce qu'un LLM
    ferait implicitement) ; aucun fait du graphe n'est utilisé pour choisir la réponse."""
    if plan is None or not plan.intention or not ctx.passages:
        return ABSTENTION
    e = plan.emplacements
    if plan.intention == "causes_yesno":
        if "C" not in e or "SE" not in e:
            return ABSTENTION
        for n, p in enumerate(ctx.passages, 1):
            focus = {v for m in dico.reperer(p.get("focus", ""), approche=False) for v in m.candidats.values()}
            for ph in R_PHRASE.split(p["texte"]):
                ids = focus | {v for m in dico.reperer(ph, approche=False) for v in m.candidats.values()}
                if e["C"] in ids and e["SE"] in ids and re.search(DECLENCHEURS_TEXTE["CcSE"], ph, re.I):
                    return f"Yes, {g.nom[e['C']]} can cause {g.nom[e['SE']]} [P{n}]."
        return "I don't know: the context does not state it."
    t = plan.type_reponse
    contraintes = INTENTIONS[plan.intention][2]
    rel = contraintes[0][0] if contraintes else "CtD"
    cites = {}
    for n, p in enumerate(ctx.passages, 1):
        for ph in R_PHRASE.split(p["texte"]):
            if not re.search(DECLENCHEURS_TEXTE[rel], ph, re.I):
                continue
            for m in dico.reperer(ph, types=[t], approche=False):
                x = m.candidats.get(t)
                if x and x not in e.values():
                    cites.setdefault(g.nom[x], set()).add(n)
    if not cites:
        return ABSTENTION
    return "The answer is:\n" + "\n".join(f"- {nom} " + "".join(f"[P{n}]" for n in sorted(cites[nom]))
                                          for nom in sorted(cites))


def generer(payload, ctx, g, mode="ollama", modele="qwen2.5:3b", plan=None, dico=None):
    """Renvoie (texte de la réponse, étiquette du générateur)."""
    if mode == "gabarit":
        if ctx.systeme == "rag":
            return generer_gabarit_texte(ctx, g, plan, dico), "gabarit_extractif_passages"
        return generer_gabarit(ctx, g), "gabarit_preuves_graphe"
    return generer_ollama(payload, modele), f"ollama:{modele}"
