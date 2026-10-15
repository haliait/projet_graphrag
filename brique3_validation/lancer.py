"""Brique 3 : décision, file d'attente et, en option, traitement par l'expert simulé.
  python -m brique3_validation.lancer --entree resultats/FICHIER.json [--passe 1|2] [--expert auto] [--reinitialiser]
"""
import argparse, json
from collections import Counter
from pathlib import Path
from brique3_validation.config import PARAMS, RESULTATS
from brique3_validation.confiance import decider
from brique3_validation.file_attente import FileAttente
from brique3_validation.memoire import Memoire


def cle(o, passe):
    return f"{o.get('systeme', 'graphrag')}|{o['id']}|{o.get('formulation', 'question')}|{passe}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entree", required=True)
    ap.add_argument("--passe", type=int, default=1, help="1 = sans mémoire ; 2 = avec réutilisation")
    ap.add_argument("--expert", choices=["aucun", "auto"], default="aucun")
    ap.add_argument("--reinitialiser", action="store_true", help="vide la file et la mémoire")
    args = ap.parse_args()

    objets = json.loads(Path(args.entree).read_text(encoding="utf-8"))
    file, memoire = FileAttente(), Memoire()
    if args.reinitialiser:
        file.vider()
        memoire.reinitialiser()

    escaladees = []
    for o in objets:
        o.setdefault("systeme", "graphrag")
        o.setdefault("formulation", "question")
        if args.passe >= 2:
            memoire.reverifier(o)
            if memoire.appliquer(o):
                continue
        decider(o, PARAMS)
        if o["decision"] == "ESCALADEE":
            file.ajouter(o, cle(o, args.passe), args.passe)
            escaladees.append(o)

    if args.expert == "auto" and escaladees:
        from hetionet_utils import charger_graphe
        from brique3_validation.expert_simule import ExpertSimule
        expert = ExpertSimule(charger_graphe())
        for o in escaladees:
            statut, reponse, corrections, temps = expert.traiter(o)
            file.enregistrer(cle(o, args.passe), statut, reponse, corrections, temps, "expert_simule")
            memoire.enregistrer_correction(o, reponse, corrections)
            o["validation"] = {"statut": statut, "reponse_finale": reponse, "temps_expert_s": temps}

    RESULTATS.mkdir(exist_ok=True)
    sortie = RESULTATS / f"b3_{Path(args.entree).stem}_passe{args.passe}.json"
    sortie.write_text(json.dumps(objets, ensure_ascii=False, indent=2), encoding="utf-8")

    n = len(objets)
    print(f"{n} réponses | livrées : {n - len(escaladees)} | escaladées : {len(escaladees)} "
          f"({len(escaladees) / max(n, 1):.0%}) | depuis la mémoire : {sum(o.get('source') == 'memoire' for o in objets)}")
    for raison, k in Counter(o["raison"].split(" (")[0] for o in escaladees).most_common():
        print(f"   - {raison} : {k}")
    for o in objets:
        print(f"   {o['id']} {o['formulation']:11s} {o['systeme']:8s} C={o['confiance']!s:5s} "
              f"{o['decision']:9s} {o['raison'] or ''}")
    print("Résultats :", sortie)


if __name__ == "__main__":
    main()