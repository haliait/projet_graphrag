"""LLM simulé : injecte des erreurs contrôlées dans une réponse fidèle, pour TESTER la brique 2 et
CALIBRER la brique 3. Expérience synthétique : ne mesure jamais les performances d'un vrai LLM.

Erreurs injectées (journalisées, donc vérité connue) :
  oubli          un élément correct disparaît de la liste ;
  substitution   un élément correct est remplacé par un distracteur plausible (il satisfait une
                 seule des contraintes, ou c'est un voisin du bon type dans le graphe) ;
  ajout          un distracteur est ajouté (hallucination) ;
  inversion      « Yes, X can cause Y » devient « No, X does not cause Y » ;
  affirmation_hallucinee   une abstention devient « Yes, X is known to cause Y ».
Bruit de surface (pas une erreur) : synonyme usuel, minuscules ou lettre oubliée dans un nom.
"""
from __future__ import annotations

import random

from entites import SYNONYMES_MANUELS, normaliser
from plans import executer


class LLMSimule:
    def __init__(self, g, taux=0.1, seed=0):
        self.g, self.taux, self.rng = g, taux, random.Random(seed)
        self.synonymes = {}
        for syn, (nom, _t) in SYNONYMES_MANUELS.items():
            self.synonymes.setdefault(normaliser(nom), []).append(syn)

    def surface(self, nom):
        r = self.rng.random()
        syns = self.synonymes.get(normaliser(nom))
        if syns and r < 0.5:
            return self.rng.choice(sorted(syns))
        if r < 0.65 and len(nom) > 8:
            i = self.rng.randrange(2, len(nom) - 2)
            return nom[:i] + nom[i + 1:]
        return nom.lower() if r < 0.8 else nom

    def distracteur(self, plan, exclus):
        g, e, t = self.g, plan.emplacements, plan.type_reponse
        pool = set()
        if t == "Compound":
            for k in ("D", "D2"):
                if k in e:
                    pool |= g.predecesseurs(e[k], "CtD") | g.predecesseurs(e[k], "CpD")
            if "SE" in e and len(pool) < 5:
                pool |= set(sorted(g.predecesseurs(e["SE"], "CcSE"))[:50])
        elif t == "Symptom":
            for k in ("D", "D2"):
                if k in e:
                    for d2 in g.successeurs(e[k], "DrD"):
                        pool |= g.successeurs(d2, "DpS")
        elif t == "Disease":
            for k in ("D", "C"):
                if k in e:
                    for d2 in g.successeurs(e[k], "DrD") | g.successeurs(e[k], "CtD"):
                        pool |= g.successeurs(d2, "DrD")
        pool -= set(exclus) | set(e.values())
        if not pool:
            pool = set(g.par_type.get(t, [])) - set(exclus)
        return self.rng.choice(sorted(pool)) if pool else None

    def repondre(self, ctx):
        """Renvoie (texte, injections) ; injections = [(type, id ou None)].
        Après l'appel, self.items / self.oui_non = ce que la réponse affirme vraiment (avant le bruit
        de surface) : c'est la vérité utilisée pour savoir si la réponse est juste."""
        g, plan = self.g, ctx.plan
        self.items, self.oui_non = [], None
        if not plan.intention or not plan.complet():
            return "I don't know: the answer is not in the context.", []
        e = plan.emplacements
        if plan.intention == "causes_yesno":
            oui = bool(ctx.sous_graphe is not None and ctx.sous_graphe.a_arete(e["C"], "CcSE", e["SE"]))
            c, se = self.surface(g.nom[e["C"]]), self.surface(g.nom[e["SE"]])
            if oui and self.rng.random() < self.taux:
                self.oui_non = False
                return f"No, {c} does not cause {se}.", [("inversion", None)]
            if not oui and self.rng.random() < self.taux:
                self.oui_non = True
                return f"Yes, {c} is known to cause {se}.", [("affirmation_hallucinee", None)]
            self.oui_non = True if oui else None
            return (f"Yes, {c} can cause {se}." if oui else "I don't know: the context does not state it."), []
        corrects = sorted(executer(plan, ctx.sous_graphe)) if ctx.sous_graphe is not None else []
        items, inj = [], []
        for x in corrects:
            r = self.rng.random()
            if r < self.taux / 2:
                inj.append(("oubli", x))
            elif r < self.taux:
                d = self.distracteur(plan, corrects + items)
                if d:
                    inj.append(("substitution", d)); items.append(d)
            else:
                items.append(x)
        if self.rng.random() < self.taux:
            d = self.distracteur(plan, corrects + items)
            if d:
                inj.append(("ajout", d)); items.append(d)
        self.items = list(items)
        if not items:
            return "I don't know: the answer is not in the context.", inj
        return "The answer is:\n" + "\n".join(f"- {self.surface(g.nom[x])}" for x in items), inj
