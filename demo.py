"""Démonstration en direct : une question -> brique 1 -> génération -> brique 2 -> brique 3, affiché étape par étape.

  python demo.py "Which drugs that treat rheumatoid arthritis are known to cause hepatotoxicity?"
  python demo.py "Does warfarin cause bleeding?" --file          # envoie la réponse escaladée à l'interface expert
  python demo.py "..." --systeme rag                             # même question avec le RAG classique
  python demo.py "..." --generateur ollama                       # avec un vrai petit LLM (Ollama lancé)
"""
import argparse
import hashlib
import sys

from cli import construire
from entites import Dictionnaire
from generation import generer
from pipeline import plan_pour_verification, vers_objet
from rag_classique import RAGClassique
from brique2_verification_regles import Verificateur
from brique3_validation.confiance import decider
from brique3_validation.config import PARAMS

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ICONES = {"SOUTENUE": "[OK]", "PARTIELLE": "[~ ]", "NON_VERIFIABLE": "[? ]",
          "NON_SOUTENUE": "[--]", "CONTRADICTOIRE": "[XX]"}


def titre(t):
    print("\n" + "=" * 78 + f"\n {t}\n" + "=" * 78)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("question")
    ap.add_argument("--systeme", choices=["graphrag", "rag"], default="graphrag")
    ap.add_argument("--generateur", choices=["gabarit", "ollama"], default="gabarit")
    ap.add_argument("--modele", default="qwen2.5:3b")
    ap.add_argument("--file", action="store_true", help="ajoute la réponse escaladée à la file de l'expert")
    ap.add_argument("--max-preuves", type=int, default=12, help="nombre de triplets affichés")
    args = ap.parse_args()

    print("Chargement du graphe et de l'index MedQuAD…")
    g, rg = construire(mode="graphrag")
    dico = rg.dico
    recherche = rg if args.systeme == "graphrag" else RAGClassique(rg.index)
    verif = Verificateur(g, Dictionnaire(g, approche=True))

    # ---------------- Brique 1 ----------------
    titre(f"BRIQUE 1 — Recherche ({args.systeme})")
    print("Question :", args.question)
    ctx = recherche.rechercher(args.question)
    payload = ctx.exporter(g)
    plan = plan_pour_verification(ctx, args.question, dico)
    print("Intention :", plan.intention or "(aucune : question hors périmètre)")
    for k, v in (plan.emplacements or {}).items():
        print(f"  {k} = {g.nom.get(v, v)} ({g.type.get(v, '?')}, {v})")
    if getattr(plan, "non_lies", None):
        print("  Non reliés :", plan.non_lies)
    diag = payload.get("diagnostics") or {}
    print("Statut :", diag.get("status"), "| score de recherche :", payload.get("retrieval_score"))
    preuves = payload.get("graph_evidence", [])
    print(f"Preuves du graphe : {len(preuves)} triplet(s)")
    for e in preuves[:args.max_preuves]:
        print(f"  {e.get('citation')}  {e.get('source_name')} -{e.get('relation')}-> {e.get('target_name')}"
              f"   ({e.get('provenance') or ''})")
    if len(preuves) > args.max_preuves:
        print(f"  … {len(preuves) - args.max_preuves} autre(s)")
    for p in payload.get("passages", []):
        print(f"  {p.get('citation')}  MedQuAD : {(p.get('texte') or '')[:90]!r}…")

    # ---------------- Génération ----------------
    titre(f"GÉNÉRATION ({args.generateur})")
    reponse, generateur = generer(payload, ctx, g, args.generateur, args.modele, plan, dico)
    print(reponse)

    # ---------------- Brique 2 ----------------
    titre("BRIQUE 2 — Vérification par règles")
    rapport = verif.verifier(reponse, plan, ctx)
    q = {"id": "DEMO", "sauts": None, "categorie": "demo"}
    o = vers_objet(q, "question", args.systeme, args.question, payload, plan, reponse, generateur, rapport, g)
    if not o["affirmations"]:
        print("Aucune affirmation extraite.")
    for a in o["affirmations"]:
        nie = "NOT " if a["nie"] else ""
        print(f"{ICONES.get(a['statut'], '    ')} {a['statut']:<15} {a['regle']:<4} "
              f"{a['sujet_nom']} {nie}{a['relation']} {a['objet_nom']}")
        if a["explication"]:
            print(f"       -> {a['explication']}")
    print("Score de vérification :", o["score_verification_b2"], "| complétude :", o["completude"])
    if o["drapeaux"]:
        print("Drapeaux :", ", ".join(o["drapeaux"]))
    if o["omissions"]:
        print("Omissions (R11) :", ", ".join(o["omissions"][:10]))

    # ---------------- Brique 3 ----------------
    titre("BRIQUE 3 — Décision")
    d = decider(o)
    print(f"Confiance = {PARAMS['alpha']} × {d['score_recherche']} + {1 - PARAMS['alpha']:.1f} × "
          f"{d['score_verification']} = {d['confiance']}   (seuil tau = {PARAMS['tau']})")
    print("Décision :", d["decision"], f"— {d['raison']}" if d["raison"] else "")
    if args.file and d["decision"] == "ESCALADEE":
        from brique3_validation.file_attente import FileAttente
        cle = "DEMO-" + hashlib.sha1(f"{args.systeme}|{args.question}".encode()).hexdigest()[:8]
        o["id"] = cle
        FileAttente().ajouter(d, cle, 1)
        print(f"Ajoutée à la file de l'expert ({cle}) : ouvrir l'interface Streamlit.")


if __name__ == "__main__":
    main()
