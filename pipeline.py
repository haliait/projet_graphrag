"""Enchaîne : brique 1 (recherche) -> génération -> brique 2 (vérification) -> fichier d'entrée de la brique 3.

  python pipeline.py --systeme graphrag --formulation question
  python pipeline.py --systeme rag --formulation question
  python pipeline.py --systeme graphrag --formulation paraphrase --avec-memoire
Options : --generateur ollama|gabarit   --modele qwen2.5:3b   --limite N (test rapide)
"""
import argparse, json, time
from dataclasses import asdict
from cli import construire
from entites import normaliser
from plans import analyser_question
from rag_classique import RAGClassique
from brique2_verification_regles import Verificateur
from generation import generer, ErreurGeneration
from brique3_validation.config import QUESTIONS, RESULTATS
from brique3_validation.memoire import Memoire, MemoirePourBrique2


def charger_questions():
    d = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    return d["questions"] if isinstance(d, dict) else d


def injecter_synonymes(dico, g, synonymes):
    """Synonymes validés par l'expert -> dictionnaire de la brique 1 (sans modifier son code)."""
    for syn, nid in synonymes.items():
        if nid in g.nom:
            forme = normaliser(syn)
            dico.entrees.setdefault(forme, {})[g.type[nid]] = nid
            dico.longueur_max = max(dico.longueur_max, len(forme.split()))


def plan_pour_verification(ctx, texte, dico):
    """Le RAG classique n'a pas de plan : on analyse la question pour pouvoir vérifier la réponse."""
    if ctx.plan.intention:
        return ctx.plan
    try:
        return analyser_question(texte, dico)
    except Exception:
        return ctx.plan


def base(q, formulation, systeme, texte):
    return {"id": q["id"], "formulation": formulation, "systeme": systeme, "question": texte,
            "sauts": q.get("sauts"), "categorie": q.get("categorie")}


def vers_objet(q, formulation, systeme, texte, payload, plan, reponse, generateur, rapport, g):
    def nom(x, surface):
        return g.nom.get(x, x) if x else (surface or "?")

    p = asdict(plan)
    diag = payload.get("diagnostics") or {}
    score = payload.get("retrieval_score") or 0.0
    if systeme == "rag":                       # le RAG n'a pas de score : disponibilité de passages
        score = 1.0 if payload.get("passages") else 0.0
    return {**base(q, formulation, systeme, texte),
            "intention": p.get("intention"), "emplacements": p.get("emplacements") or {},
            "plan_exact": bool(p.get("exact", True)), "non_lies": p.get("non_lies") or [],
            "statut_recherche": diag.get("status"), "retrieval_score": score,
            "preuves": [{k: e.get(k) for k in ("citation", "source_id", "source_name", "relation",
                                               "target_id", "target_name", "provenance")}
                        for e in payload.get("graph_evidence", [])],
            "passages": [{"citation": x.get("citation"), "source": x.get("source"), "id": x.get("id"),
                          "texte": (x.get("texte") or "")[:1500]} for x in payload.get("passages", [])],
            "reponse": reponse, "generateur": generateur,
            "affirmations": [{"sujet": a.sujet, "relation": a.relation, "objet": a.objet, "nie": a.nie,
                              "sujet_nom": nom(a.sujet, a.textes[0]), "objet_nom": nom(a.objet, a.textes[1]),
                              "phrase": a.phrase, "statut": a.statut, "regle": a.regle,
                              "explication": a.explication, "dans_contexte": a.dans_contexte,
                              "implicite": a.implicite, "exacte": a.exacte,
                              "citations": [str(c) for c in a.citations]} for a in rapport.affirmations],
            "elements": [str(x) for x in rapport.elements],
            "omissions": [g.nom.get(x, str(x)) for x in rapport.omissions],
            "score_verification_b2": rapport.score, "completude": rapport.completude,
            "drapeaux": list(rapport.drapeaux), "abstention": bool(rapport.abstention),
            "oui_non": rapport.oui_non, "erreur": None}


def objet_erreur(q, formulation, systeme, texte, e):
    return {**base(q, formulation, systeme, texte), "intention": None, "emplacements": {},
            "plan_exact": False, "non_lies": [], "statut_recherche": None, "retrieval_score": 0.0,
            "preuves": [], "passages": [], "reponse": "", "generateur": None, "affirmations": [],
            "elements": [], "omissions": [], "score_verification_b2": None, "completude": None,
            "drapeaux": [], "abstention": False, "oui_non": None, "erreur": f"{type(e).__name__}: {e}"}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systeme", choices=["graphrag", "rag"], default="graphrag")
    ap.add_argument("--formulation", choices=["question", "paraphrase"], default="question")
    ap.add_argument("--generateur", choices=["ollama", "gabarit"], default="ollama")
    ap.add_argument("--modele", default="qwen2.5:3b")
    ap.add_argument("--avec-memoire", action="store_true", help="réutilise les corrections de l'expert")
    ap.add_argument("--limite", type=int, default=0, help="ne traite que les N premières questions")
    args = ap.parse_args()

    print("Chargement du graphe et de l'index MedQuAD…")
    g, recherche_graphe = construire(mode="graphrag")
    dico = recherche_graphe.dico
    memoire_b2 = None
    if args.avec_memoire:
        memoire = Memoire()
        injecter_synonymes(dico, g, memoire.d["synonymes"])
        memoire_b2 = MemoirePourBrique2(memoire)
    recherche = recherche_graphe if args.systeme == "graphrag" else RAGClassique(recherche_graphe.index)
    verificateur = Verificateur(g, dico, memoire=memoire_b2)

    questions = charger_questions()
    if args.limite:
        questions = questions[:args.limite]
    objets = []
    for q in questions:
        texte = q["question"] if args.formulation == "question" else q["paraphrase"]
        t0 = time.perf_counter()
        try:
            ctx = recherche.rechercher(texte)
            payload = ctx.exporter(g)
            reponse, generateur = generer(payload, ctx, g, args.generateur, args.modele)
            plan = plan_pour_verification(ctx, texte, dico)
            rapport = verificateur.verifier(reponse, plan, ctx)
            o = vers_objet(q, args.formulation, args.systeme, texte, payload, plan,
                           reponse, generateur, rapport, g)
        except ErreurGeneration:
            raise
        except Exception as e:
            o = objet_erreur(q, args.formulation, args.systeme, texte, e)
        o["duree_s"] = round(time.perf_counter() - t0, 2)
        objets.append(o)
        print(f"{o['id']} | {o['statut_recherche']} | {len(o['affirmations'])} affirmation(s) | "
              f"{o['duree_s']} s | {(o['reponse'] or o['erreur'] or '')[:70]!r}")

    suffixe = ("_memoire" if args.avec_memoire else "") + ("_gabarit" if args.generateur == "gabarit" else "")
    RESULTATS.mkdir(exist_ok=True)
    sortie = RESULTATS / f"pipeline_{args.systeme}_{args.formulation}{suffixe}.json"
    sortie.write_text(json.dumps(objets, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("Écrit :", sortie)


if __name__ == "__main__":
    main()