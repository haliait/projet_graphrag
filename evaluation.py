"""Retrieval evaluation, NOT a clinical answer evaluation. No generated gold labels."""
import argparse
import csv
import json
from pathlib import Path
import statistics
import time
from brique1_recherche_graphe import RechercheGraphe
from entites import Dictionnaire
from hetionet_utils import DATA, charger_graphe
from medquad_utils import IndexMedQuAD
from rag_classique import RAGClassique


def reference_edges(question, graph):
    """Independent oracle from hand-authored canonical slots, never predicted plan."""
    p = question["plan"]
    lookup = {(graph.type[n], name): n for n, name in graph.nom.items()}
    e = {key: lookup[tuple(value)] for key, value in p.items() if key != "intention"}
    if question.get("hors_graphe"):
        return set(), e
    it = p["intention"]
    edges = set()
    if it == "causes_yesno":
        if graph.a_arete(e["C"], "CcSE", e["SE"]):
            edges.add((e["C"], "CcSE", e["SE"]))
    elif it in ("treat_disease", "palliates"):
        r = "CtD" if it == "treat_disease" else "CpD"
        edges = {(c, r, e["D"]) for c in graph.predecesseurs(e["D"], r)}
    elif it in ("symptoms_of", "resembles"):
        r = "DpS" if it == "symptoms_of" else "DrD"
        edges = {(e["D"], r, x) for x in graph.successeurs(e["D"], r)}
    elif it == "drugs_for_resembling":
        for d in graph.successeurs(e["D"], "DrD"):
            for c in graph.predecesseurs(d, "CtD"):
                edges.update([(e["D"], "DrD", d), (c, "CtD", d)])
    elif it == "shared_symptoms":
        for x in graph.successeurs(e["D"], "DpS") & graph.successeurs(e["D2"], "DpS"):
            edges.update([(e["D"], "DpS", x), (e["D2"], "DpS", x)])
    elif it in ("treat_and_cause", "treat_both", "class_treat"):
        for c in graph.predecesseurs(e["D"], "CtD"):
            other = ((c, "CcSE", e["SE"]) if it == "treat_and_cause" else
                     (c, "CtD", e["D2"]) if it == "treat_both" else (e["P"], "PCiC", c))
            if graph.a_arete(*other):
                edges.update([(c, "CtD", e["D"]), other])
    else:
        raise ValueError(f"Oracle not implemented: {it}")
    return edges, e


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(DATA))
    parser.add_argument("--output-dir", type=Path, default=Path("resultats"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    g = charger_graphe(args.data_dir)
    idx = IndexMedQuAD(args.data_dir / "medquad_passages.jsonl")
    d = Dictionnaire(g)
    setup = time.perf_counter() - start
    systems = {"graphrag": RechercheGraphe(g, d, idx), "rag": RAGClassique(idx),
               "sans_synonymes": RechercheGraphe(g, Dictionnaire(g, synonymes=False), idx),
               "un_saut": RechercheGraphe(g, d, idx, longueur_chemin=1)}
    questions = json.loads(Path(__file__).with_name("questions.json").read_text(encoding="utf-8"))["questions"]
    rows, outputs, judgments = [], [], []
    for q in questions:
        gold, slots = reference_edges(q, g)
        for variant in ("question", "paraphrase"):
            for name, system in systems.items():
                ctx = system.rechercher(q[variant])
                actual = set(ctx.triplets)
                row = {"id": q["id"], "variant": variant, "system": name, "hops": q["sauts"],
                       "category": q["categorie"], "status": ctx.details["status"],
                       "plan_correct": (ctx.plan.intention == q["plan"]["intention"] and ctx.plan.emplacements == slots) if name != "rag" else None,
                       "graph_evidence_recall": len(actual & gold) / len(gold) if gold and name != "rag" else None,
                       "graph_trace_valid": all(g.a_arete(*t) for t in ctx.triplets) if ctx.triplets else None,
                       "triplets": len(ctx.triplets), "passages": len(ctx.passages),
                       "context_characters": len(ctx.texte(g)), "latency_ms": ctx.duree * 1000,
                       "warnings": ";".join(ctx.details["warnings"])}
                rows.append(row)
                payload = ctx.exporter(g)
                outputs.append(dict(id=q["id"], variant=variant, system=name, result=payload))
                if name in ("rag", "graphrag") and variant == "question":
                    for p in payload["passages"]:
                        judgments.append({"question_id": q["id"], "system": name, "passage_id": p["id"],
                                          "url": p.get("url"), "relevant_0_or_1": "", "supports_answer_0_or_1": "", "reviewer": ""})
    for name, records in [("retrieval.csv", rows), ("passage_judgments.csv", judgments)]:
        with (args.output_dir / name).open("w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    with (args.output_dir / "contexts.jsonl").open("w", encoding="utf-8") as out:
        for item in outputs:
            out.write(json.dumps(item, ensure_ascii=False) + "\n")
    summary = {"questions": len(questions), "multi_hop": sum(q["sauts"] >= 2 for q in questions),
               "runs": len(rows), "setup_seconds": setup, "scope": "retrieval_only_not_clinical_accuracy", "systems": {}}
    for name in systems:
        subset = [r for r in rows if r["system"] == name]
        summary["systems"][name] = {}
        for metric in ["plan_correct", "graph_evidence_recall", "graph_trace_valid", "latency_ms", "context_characters"]:
            values = [r[metric] for r in subset if r[metric] is not None]
            summary["systems"][name][metric] = {"mean": statistics.mean(values) if values else None, "n": len(values)}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
