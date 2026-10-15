"""Évaluation de la brique 2 (vérification par règles) — EXPÉRIENCE SYNTHÉTIQUE.

On part des réponses fidèles GraphRAG (gabarit) aux 20 questions, on y injecte des erreurs
contrôlées (llm_simule.py), puis on mesure ce que la brique 2 détecte :
  * taux d'erreurs injectées détectées, par type (oubli, substitution, ajout, inversion…) ;
  * fausses alertes : éléments corrects de la réponse que la brique 2 signale ;
  * accord entre la version Python et la version ProbLog des règles.
La référence est le graphe complet : la mesure porte sur l'écart au graphe, pas sur la vérité
clinique (voir docs/EVALUATION.md). Aucun chiffre ici ne décrit les performances d'un vrai LLM.

    python brique2_experience.py            # 5 graines, taux 0 / 0,1 / 0,2 / 0,3 / 0,5
    python brique2_experience.py --rapide   # 2 graines, taux 0,1 seulement
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from brique2_problog import statut_depuis_proba, verifier_problog
from brique2_verification_regles import Verificateur
from cli import construire
from entites import Dictionnaire
from llm_simule import LLMSimule
from plans import executer

RESULTATS = Path(__file__).resolve().parent / "resultats"
TYPES = ("oubli", "substitution", "ajout", "inversion", "affirmation_hallucinee")


def detectee(typ, x, rapport, gold):
    """Une erreur injectée est-elle signalée par la brique 2 ?"""
    if typ in ("substitution", "ajout"):
        if x in gold:
            return None                      # le distracteur était en fait correct : pas une erreur
        statut = rapport.elements.get(x)
        if statut is None:                   # nom non relié : signalé comme élément inconnu ?
            return any(str(k).startswith("?") for k in rapport.elements)
        return statut != "SOUTENUE"
    if typ == "oubli":
        return x in rapport.omissions
    # inversion / affirmation hallucinée (question oui / non)
    return (any(a.statut != "SOUTENUE" for a in rapport.affirmations if a.relation == "CcSE")
            or bool({"contradiction", "non_verifiable", "partielle"} & set(rapport.drapeaux)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rapide", action="store_true")
    args = ap.parse_args()
    graines = [0, 1] if args.rapide else [0, 1, 2, 3, 4]
    taux_liste = [0.1] if args.rapide else [0.0, 0.1, 0.2, 0.3, 0.5]

    g, recherche = construire()
    verif = Verificateur(g, Dictionnaire(g, approche=True))
    questions = json.loads(Path("questions.json").read_text(encoding="utf-8"))["questions"]
    contextes = [(q, recherche.rechercher(q["question"])) for q in questions]

    lignes, accord, total_pl = [], 0, 0
    for taux in taux_liste:
        compte = defaultdict(lambda: [0, 0])          # type -> [injectées, détectées]
        fa_signales = fa_total = reponses = escalade_b2 = 0
        for seed in graines:
            llm = LLMSimule(g, taux, seed)
            for q, ctx in contextes:
                texte, injections = llm.repondre(ctx)
                rapport = verif.verifier(texte, ctx.plan, ctx)
                gold = executer(ctx.plan, g) if ctx.plan.complet() else set()
                reponses += 1
                escalade_b2 += bool(rapport.drapeaux)
                for typ, x in injections:
                    d = detectee(typ, x, rapport, gold)
                    if d is None:
                        continue
                    compte[typ][0] += 1
                    compte[typ][1] += bool(d)
                injectes = {x for _, x in injections}
                for x, statut in rapport.elements.items():   # fausses alertes sur les bons éléments
                    if x in gold and x not in injectes:
                        fa_total += 1
                        fa_signales += statut != "SOUTENUE"
                if taux == 0.1:                              # accord Python / ProbLog
                    probas, _ = verifier_problog(rapport.affirmations, verif, ctx.plan)
                    for cid, (ps, pk) in probas.items():
                        total_pl += 1
                        accord += statut_depuis_proba(ps, pk) == rapport.affirmations[int(cid[1:])].statut
        inj = sum(v[0] for v in compte.values())
        det = sum(v[1] for v in compte.values())
        ligne = {"taux_erreur": taux, "reponses": reponses, "erreurs_injectees": inj, "erreurs_detectees": det,
                 "taux_detection": round(det / inj, 3) if inj else None,
                 "fausses_alertes": round(fa_signales / fa_total, 4) if fa_total else None,
                 "reponses_avec_drapeau": round(escalade_b2 / reponses, 3)}
        for typ in TYPES:
            n, k = compte[typ]
            ligne[f"detection_{typ}"] = f"{k}/{n}" if n else ""
        lignes.append(ligne)
        print(ligne)

    RESULTATS.mkdir(exist_ok=True)
    with open(RESULTATS / "brique2_detection.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(lignes[0]), delimiter=";")
        w.writeheader(); w.writerows(lignes)
    resume = {"experience": "synthétique (erreurs injectées, référence = graphe complet)",
              "graines": graines, "par_taux": lignes,
              "accord_python_problog": {"affirmations": total_pl, "accord": round(accord / total_pl, 4) if total_pl else None}}
    (RESULTATS / "brique2_resume.json").write_text(json.dumps(resume, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Accord Python / ProbLog :", resume["accord_python_problog"])
    print("Écrit : resultats/brique2_detection.csv, resultats/brique2_resume.json")


if __name__ == "__main__":
    main()
