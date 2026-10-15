"""Expériences de la brique 3.
  python -m brique3_validation.experiences --passe1 resultats/b3_X_passe1.json [--passe2 ...] [--rag ...]
"""
import argparse, copy, csv, json
from collections import defaultdict
from pathlib import Path
from hetionet_utils import charger_graphe
from brique3_validation.config import PARAMS, RESULTATS
from brique3_validation.confiance import decider
from brique3_validation.expert_simule import ExpertSimule


def charger(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def mesurer(objets, ex):
    n = len(objets)
    if not n:
        return {"n": 0}
    esc = [o for o in objets if o["decision"] == "ESCALADEE"]
    fausses = [o for o in objets if not ex.est_correcte(o)]
    fausses_esc = [o for o in fausses if o["decision"] == "ESCALADEE"]
    return {
        "n": n,
        "taux_escalade": round(len(esc) / n, 3),
        "rappel_escalade": round(len(fausses_esc) / len(fausses), 3) if fausses else None,
        "precision_escalade": round(len(fausses_esc) / len(esc), 3) if esc else None,
        "exactitude_sans_expert": round(1 - len(fausses) / n, 3),
        "erreurs_residuelles": round((len(fausses) - len(fausses_esc)) / n, 3),
        "exactitude_apres_expert": round(1 - (len(fausses) - len(fausses_esc)) / n, 3),
        "temps_expert_s": sum(ex.traiter(o)[3] for o in esc),
        "temps_tout_verifier_s": sum(ex.traiter(o)[3] for o in objets),
    }


def redecider(objets, params, mode="complet"):
    copies = copy.deepcopy(objets)
    for o in copies:
        if o.get("source") != "memoire":
            decider(o, params, mode)
    return copies


def par_groupe(objets, ex, cle):
    groupes = defaultdict(list)
    for o in objets:
        groupes[cle(o)].append(o)
    return [{"groupe": k, **mesurer(v, ex)} for k, v in sorted(groupes.items())]


def ecrire(lignes, nom, titre):
    print(f"\n=== {titre} ===")
    for l in lignes:
        print("  ", l)
    champs = list(dict.fromkeys(k for l in lignes for k in l))
    with open(RESULTATS / nom, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        w.writeheader()
        w.writerows(lignes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--passe1", required=True)
    ap.add_argument("--passe2")
    ap.add_argument("--rag")
    args = ap.parse_args()

    ex = ExpertSimule(charger_graphe())
    p1 = charger(args.passe1)
    gr = [o for o in p1 if o.get("systeme", "graphrag") == "graphrag"] or p1

    ecrire([{"tau": t / 20, **mesurer(redecider(gr, {**PARAMS, "tau": t / 20}), ex)} for t in range(21)],
           "E1_balayage_tau.csv", "E1 – balayage du seuil")
    ecrire([{"mode": m, **mesurer(redecider(gr, PARAMS, m), ex)}
            for m in ("recherche", "verification", "combine", "complet")],
           "E2_ablation.csv", "E2 – ablation du score")
    if args.rag:
        ecrire([{"systeme": "graphrag", **mesurer(gr, ex)}, {"systeme": "rag", **mesurer(charger(args.rag), ex)}],
               "E3_rag_vs_graphrag.csv", "E3 – RAG classique vs GraphRAG")
    if args.passe2:
        ecrire([{"passe": 1, **mesurer(gr, ex)}, {"passe": 2, **mesurer(charger(args.passe2), ex)}],
               "E4_reutilisation.csv", "E4 – avant / après réutilisation des corrections")
    ecrire(par_groupe(gr, ex, lambda o: ex.q.get(o["id"], {}).get("categorie", "?")),
           "E5_par_categorie.csv", "E5 – par catégorie de question")
    ecrire(par_groupe(gr, ex, lambda o: f"{ex.q.get(o['id'], {}).get('sauts', '?')} saut(s)"),
           "E6_par_sauts.csv", "E6 – 1 saut vs multi-sauts")


if __name__ == "__main__":
    main()