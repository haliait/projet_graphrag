"""Relève les signatures des briques 1 et 2 pour écrire le pipeline. Écrit resultats/sonde.txt."""
import inspect
from pathlib import Path
import cli, plans, entites, rag_classique
import brique1_recherche_graphe as b1
import brique2_verification_regles as b2

morceaux = []


def ajouter(titre, contenu):
    morceaux.append(f"\n===== {titre} =====\n{contenu}")


def source(obj, n=4000):
    try:
        return inspect.getsource(obj)[:n]
    except Exception as e:
        return f"(indisponible : {e})"


ajouter("cli.py", source(cli, 6000))
ajouter("Contexte", source(b1.Contexte))
ajouter("RechercheGraphe.__init__", source(b1.RechercheGraphe.__init__))
ajouter("RechercheGraphe : méthodes", [n for n in dir(b1.RechercheGraphe) if not n.startswith("__")])
ajouter("rag_classique.py", source(rag_classique))
ajouter("plans : fonctions", "\n".join(f"{n}{inspect.signature(f)}" for n, f in
                                       inspect.getmembers(plans, inspect.isfunction) if f.__module__ == "plans"))
ajouter("Dictionnaire.__init__", source(entites.Dictionnaire.__init__, 2000))
ajouter("Verificateur.__init__", source(b2.Verificateur.__init__))
ajouter("Verificateur.verifier_affirmation", source(b2.Verificateur.verifier_affirmation, 3000))
ajouter("Verificateur.verifier", source(b2.Verificateur.verifier, 6000))
ajouter("tests_extraction.py", Path("tests_extraction.py").read_text(encoding="utf-8")[:3000])

Path("resultats/sonde.txt").write_text("".join(morceaux), encoding="utf-8")
print("Écrit : resultats/sonde.txt")