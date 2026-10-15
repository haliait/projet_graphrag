"""Local retrieval CLI. No LLM, API key, server, or implicit network request."""
import argparse
import json
from pathlib import Path
from brique1_recherche_graphe import RechercheGraphe
from entites import Dictionnaire
from hetionet_utils import DATA, charger_graphe
from medquad_utils import IndexMedQuAD
from rag_classique import RAGClassique


def construire(data_dir=DATA, mode="graphrag", fuzzy=False):
    data_dir = Path(data_dir)
    index = IndexMedQuAD(data_dir / "medquad_passages.jsonl")
    if mode == "rag":
        return None, RAGClassique(index)
    graph = charger_graphe(data_dir)
    return graph, RechercheGraphe(graph, Dictionnaire(graph, approche=fuzzy), index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--data-dir", type=Path, default=Path(DATA))
    parser.add_argument("--mode", choices=["graphrag", "rag"], default="graphrag")
    parser.add_argument("--fuzzy", action="store_true", help="Experimental approximate linking")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        graph, retriever = construire(args.data_dir, args.mode, args.fuzzy)
        result = retriever.rechercher(args.question).exporter(graph)
        manifest = args.data_dir / "manifest.json"
        result["data_manifest"] = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
            print(str(args.output))
        else:
            print(text)
    except (ValueError, FileNotFoundError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
