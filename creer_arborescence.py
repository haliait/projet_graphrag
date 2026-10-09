from pathlib import Path

dossiers = ["data", "commun", "donnees_projet", "scripts", "brique1_recherche",
            "brique2_verification", "brique3_validation", "resultats", "docs"]
for d in dossiers:
    Path(d).mkdir(exist_ok=True)

# Git ignore les dossiers vides : on y met un fichier .gitkeep
for d in ["brique1_recherche", "brique2_verification", "brique3_validation", "resultats", "docs"]:
    Path(d, ".gitkeep").touch()

Path("commun/__init__.py").touch()
Path("donnees_projet/synonymes_expert.json").write_text("{}", encoding="utf-8")
Path("requirements.txt").write_text(
    "rapidfuzz>=3.0\nrank-bm25>=0.2.2\nrequests>=2.31\nstreamlit>=1.30\nrich>=13.0\n", encoding="utf-8")
Path(".gitignore").write_text(
    "data/\n.venv/\n__pycache__/\nresultats/*.json\n", encoding="utf-8")
print("Arborescence créée.")