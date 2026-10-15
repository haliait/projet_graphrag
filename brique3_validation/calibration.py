"""Calibration de la brique 3 sur un JEU DE DÉVELOPPEMENT synthétique, séparé du jeu de test.

Les 20 questions de questions.json ne servent jamais ici. On génère des questions à partir du graphe
(mêmes 11 intentions, formulations variées), en excluant les entités des questions de test, on les
fait passer dans la chaîne réelle (brique 1 -> LLM simulé à 0, 10 et 30 % d'erreurs -> brique 2),
puis on choisit alpha et tau qui minimisent le coût
        coût = taux d'escalade + 10 × taux d'erreurs transmises sans escalade
(une erreur qui atteint l'utilisateur coûte 10 revues d'expert ; hypothèse à discuter).
Résultat : resultats/calibration_b3.json, lu automatiquement par brique3_validation/config.py.

    python -m brique3_validation.calibration [--n 150]
"""
import argparse
import copy
import json
import random

from brique2_verification_regles import Verificateur
from brique3_validation.confiance import decider
from brique3_validation.config import FICHIER_CALIBRATION, RESULTATS
from cli import construire
from entites import Dictionnaire
from llm_simule import LLMSimule
from pipeline import vers_objet
from plans import INTENTIONS, Plan, analyser_question, executer

GABARITS = {
    "treat_disease": ["What drugs treat {D}?", "Which medications are indicated for {D}?", "List treatments for {D}."],
    "palliates": ["Which drugs relieve the symptoms of {D}?", "What gives symptomatic relief in {D}?"],
    "symptoms_of": ["What are the symptoms of {D}?", "Which signs does {D} present?"],
    "resembles": ["Which diseases resemble {D}?", "What conditions are similar to {D}?"],
    "diseases_treated_by": ["Which diseases does {C} treat?", "What is {C} used to treat?"],
    "causes_yesno": ["Does {C} cause {SE}?", "Can {C} lead to {SE}?"],
    "treat_and_cause": ["Which drugs that treat {D} can cause {SE}?", "Which {D} medications may cause {SE}?"],
    "drugs_for_resembling": ["Which drugs treat a disease that resembles {D}?"],
    "shared_symptoms": ["Which symptoms are shared by {D} and {D2}?", "What symptoms do {D} and {D2} have in common?"],
    "treat_both": ["Which drugs treat both {D} and {D2}?"],
    "class_treat": ["Which {P} treat {D}?"],
}


def jeu_dev(g, n, exclus, seed=42):
    rng = random.Random(seed)
    D = sorted(d for d in g.par_type["Disease"] if d not in exclus)
    C = sorted(c for c in g.par_type["Compound"] if c not in exclus)
    res, essais = [], 0
    while len(res) < n and essais < 100 * n:
        essais += 1
        it = rng.choice(sorted(GABARITS))
        if it == "causes_yesno":
            c = rng.choice([x for x in C if g.degre(x, "CcSE") > 0])
            source = c if rng.random() < 0.5 else rng.choice([x for x in C if g.degre(x, "CcSE") > 0])
            empl = {"C": c, "SE": rng.choice(sorted(g.successeurs(source, "CcSE")))}
        elif it == "diseases_treated_by":
            empl = {"C": rng.choice([x for x in C if g.degre(x, "CtD") > 0])}
        elif it == "treat_and_cause":
            d = rng.choice(D)
            tx = sorted(g.predecesseurs(d, "CtD"))
            effets = sorted(g.successeurs(rng.choice(tx), "CcSE")) if tx else []
            if not effets:
                continue
            empl = {"D": d, "SE": rng.choice(effets)}
        elif it in ("shared_symptoms", "treat_both"):
            d = rng.choice(D)
            proches = sorted(set(g.successeurs(d, "DrD")) - exclus)
            if not proches:
                continue
            empl = {"D": d, "D2": rng.choice(proches)}
        elif it == "class_treat":
            d = rng.choice(D)
            classes = sorted({p for c in g.predecesseurs(d, "CtD") for p in g.predecesseurs(c, "PCiC")})
            if not classes:
                continue
            empl = {"P": rng.choice(classes), "D": d}
        else:
            empl = {"D": rng.choice(D)}
        gold = executer(Plan(it, empl), g)
        if it != "causes_yesno" and not 1 <= len(gold) <= 25:
            continue
        texte = rng.choice(GABARITS[it]).format(**{k: g.nom[v] for k, v in empl.items()})
        res.append({"id": f"DEV{len(res):03d}", "question": texte, "sauts": INTENTIONS[it][3],
                    "categorie": "developpement", "intention": it, "gold": gold})
    return res


def correcte(q, llm):
    """Vérité : ce que la réponse affirme réellement (journal du LLM simulé), comparé au graphe."""
    if q["intention"] == "causes_yesno":
        attendu = True if True in q["gold"] else None          # pas d'arête = « non documenté »
        return llm.oui_non is attendu
    return set(llm.items) == set(q["gold"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    args = ap.parse_args()
    g, recherche = construire()
    dico_verif = Dictionnaire(g, approche=True)
    verif = Verificateur(g, dico_verif)
    test = json.loads(open("questions.json", encoding="utf-8").read())["questions"]
    exclus = set()
    for q in test:   # entités des questions de test : interdites dans le jeu de développement
        exclus |= set(analyser_question(q["question"], recherche.dico).emplacements.values())
    dev = jeu_dev(g, args.n, exclus)

    objets = []
    for k, taux in enumerate((0.0, 0.1, 0.3)):
        llm = LLMSimule(g, taux, seed=100 + k)
        for q in dev:
            ctx = recherche.rechercher(q["question"])
            texte, _ = llm.repondre(ctx)
            rapport = verif.verifier(texte, ctx.plan, ctx)
            o = vers_objet(q, "question", "graphrag", q["question"], ctx.exporter(g), ctx.plan,
                           texte, f"llm_simule_{taux}", rapport, g)
            o["_correcte"] = correcte(q, llm)
            objets.append(o)

    meilleur = None
    for a10 in range(0, 11):
        for t20 in range(1, 20):
            params = {"alpha": a10 / 10, "tau": t20 / 20}
            esc = err = 0
            for o in objets:
                d = decider(copy.deepcopy(o), params)
                esc += d["decision"] == "ESCALADEE"
                err += d["decision"] == "LIVREE" and not o["_correcte"]
            n = len(objets)
            cout = esc / n + 10 * err / n
            # à coût égal : le seuil le plus prudent (tau le plus haut), puis alpha proche de la valeur initiale
            cle = (round(cout, 6), esc, -params["tau"], abs(params["alpha"] - 0.3))
            if meilleur is None or cle < meilleur[0]:
                meilleur = (cle, params, esc / n, err / n)
    (cle, params, esc, err) = meilleur
    resultat = {"alpha": params["alpha"], "tau": params["tau"], "cout": cle[0],
                "taux_escalade_dev": round(esc, 3), "erreurs_transmises_dev": round(err, 3),
                "exactitude_generateur_dev": round(sum(o["_correcte"] for o in objets) / len(objets), 3),
                "n_reponses_dev": len(objets), "n_questions_dev": len(dev),
                "taux_erreur_llm_simule": [0.0, 0.1, 0.3], "cout_erreur_transmise": 10}
    RESULTATS.mkdir(exist_ok=True)
    FICHIER_CALIBRATION.write_text(json.dumps(resultat, indent=1), encoding="utf-8")
    print(resultat)
    print("Écrit :", FICHIER_CALIBRATION)


if __name__ == "__main__":
    main()
