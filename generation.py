"""Génération de la réponse à partir du payload de la brique 1.

- 'ollama'  : petit LLM local, température 0, modèle consigné dans chaque résultat ;
- 'gabarit' : réponse extractive construite à partir des preuves du graphe (à déclarer comme telle).
Aucune bascule silencieuse de l'un vers l'autre : si Ollama ne répond pas, on s'arrête."""
import requests

URL_OLLAMA = "http://localhost:11434/api/chat"


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
    plan = ctx.plan
    if not plan.intention or not ctx.triplets:
        return "I don't know: the answer is not in the context."
    e = plan.emplacements
    if plan.intention == "causes_yesno":
        c, se = e.get("C"), e.get("SE")
        if (c, "CcSE", se) in ctx.triplets:
            return f"Yes, {g.nom[c]} can cause {g.nom[se]}."
        return "I don't know: the context does not state it."
    t = plan.type_reponse
    noms = sorted({g.nom[x] for u, r, v in ctx.triplets for x in (u, v)
                   if g.type.get(x) == t and x not in e.values()})
    if not noms:
        return "I don't know: the answer is not in the context."
    return "The answer is:\n" + "\n".join(f"- {n}" for n in noms)


def generer(payload, ctx, g, mode="ollama", modele="qwen2.5:3b"):
    """Renvoie (texte de la réponse, étiquette du générateur)."""
    if mode == "gabarit":
        return generer_gabarit(ctx, g), "gabarit"
    return generer_ollama(payload, modele), f"ollama:{modele}"