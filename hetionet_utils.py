"""Chargement et exploration de Hetionet v1.0 (sous-graphe clinique du sujet 5).

Hetionet : Himmelstein et al., eLife 2017, https://github.com/hetio/hetionet (CC0).
Le module fourni par l'enseignant n'étant pas dans le dossier, ce module en reprend
les fonctions utiles : chargement, sous-graphe, voisinage, chemins.

On ne garde que les métarelations utiles à la question clinique :
    DpS  Disease  -presents->      Symptom      (co-occurrence MEDLINE)
    CtD  Compound -treats->        Disease      (PharmacotherapyDB, indications validées)
    CpD  Compound -palliates->     Disease      (PharmacotherapyDB, traitement symptomatique)
    CcSE Compound -causes->        Side Effect  (SIDER 4.1, notices de médicaments)
    DrD  Disease  -resembles-      Disease      (co-occurrence MEDLINE, symétrique)
    PCiC Pharmacologic Class -includes-> Compound (DrugCentral / NDF-RT)
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path
from collections import defaultdict, deque

import pandas as pd

ICI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ICI, "data")

TYPES_UTILES = ["Disease", "Symptom", "Compound", "Side Effect", "Pharmacologic Class"]

# métarelation -> (type source, nom lisible, type cible, symétrique ?, source de la donnée)
METAEDGES = {
    "DpS": ("Disease", "presents", "Symptom", False, "MEDLINE (co-occurrence MeSH)"),
    "CtD": ("Compound", "treats", "Disease", False, "PharmacotherapyDB v1.0"),
    "CpD": ("Compound", "palliates", "Disease", False, "PharmacotherapyDB v1.0"),
    "CcSE": ("Compound", "causes", "Side Effect", False, "SIDER 4.1"),
    "DrD": ("Disease", "resembles", "Disease", True, "MEDLINE (co-occurrence)"),
    "PCiC": ("Pharmacologic Class", "includes", "Compound", False, "DrugCentral / NDF-RT"),
}


class Graphe:
    """Graphe orienté étiqueté, stocké en listes d'adjacence (sortantes et entrantes)."""

    def __init__(self, noeuds: pd.DataFrame, aretes: pd.DataFrame):
        if noeuds["id"].duplicated().any() or noeuds[["id", "name", "kind"]].isna().any().any():
            raise ValueError("Noeuds invalides ou dupliques")
        self.nom = dict(zip(noeuds["id"], noeuds["name"]))
        self.type = dict(zip(noeuds["id"], noeuds["kind"]))
        self.par_type = defaultdict(list)
        for i, k in self.type.items():
            self.par_type[k].append(i)
        self.sortant = defaultdict(lambda: defaultdict(set))  # sortant[u][rel] = {v}
        self.entrant = defaultdict(lambda: defaultdict(set))  # entrant[v][rel] = {u}
        self.n_aretes = 0
        for u, rel, v in aretes[["source", "metaedge", "target"]].itertuples(index=False):
            self.ajouter(u, rel, v)

    @classmethod
    def depuis_triplets(cls, g_parent, triplets):
        """Sous-graphe (même interface) restreint à une liste de triplets : c'est le « contexte »."""
        ids = {x for u, _, v in triplets for x in (u, v)}
        noeuds = pd.DataFrame({"id": list(ids), "name": [g_parent.nom[i] for i in ids],
                               "kind": [g_parent.type[i] for i in ids]})
        aretes = pd.DataFrame(list(triplets), columns=["source", "metaedge", "target"])
        return cls(noeuds, aretes)

    # --- construction -------------------------------------------------
    def ajouter(self, u, rel, v):
        if rel not in METAEDGES or u not in self.nom or v not in self.nom:
            raise ValueError("Arete inconnue ou noeud absent")
        if (self.type[u], self.type[v]) != (METAEDGES[rel][0], METAEDGES[rel][2]):
            raise ValueError("Types incompatibles avec la relation")
        if self.a_arete(u, rel, v):
            return
        self.sortant[u][rel].add(v)
        self.entrant[v][rel].add(u)
        self.n_aretes += 1
        if METAEDGES[rel][3]:  # relation symétrique : on stocke les deux sens
            self.sortant[v][rel].add(u)
            self.entrant[u][rel].add(v)

    # --- requêtes élémentaires ----------------------------------------
    def a_arete(self, u, rel, v) -> bool:
        return v in self.sortant.get(u, {}).get(rel, set())

    def successeurs(self, u, rel):
        return set(self.sortant.get(u, {}).get(rel, set()))

    def predecesseurs(self, v, rel):
        return set(self.entrant.get(v, {}).get(rel, set()))

    def degre(self, u, rel, sens="out"):
        d = self.sortant if sens == "out" else self.entrant
        return len(d.get(u, {}).get(rel, ()))

    def voisins(self, u):
        """Tous les voisins (relation, sens, voisin)."""
        for rel, vs in sorted(self.sortant.get(u, {}).items()):
            for v in sorted(vs):
                yield rel, "->", v
        for rel, vs in sorted(self.entrant.get(u, {}).items()):
            if METAEDGES[rel][3]:
                continue  # déjà vu dans le sens sortant
            for v in sorted(vs):
                yield rel, "<-", v

    def triplet_lisible(self, u, rel, v):
        return f"{self.nom[u]} --{METAEDGES[rel][1]}--> {self.nom[v]}"

    # --- sous-graphe et chemins ---------------------------------------
    def voisinage(self, graines, rels=None, profondeur=1, max_par_noeud=60):
        """Triplets (u, rel, v) à au plus `profondeur` sauts des graines.
        `max_par_noeud` borne la taille du contexte (les composés ont des centaines d'effets)."""
        if not 0 <= profondeur <= 2 or max_par_noeud < 0:
            raise ValueError("Profondeur 0..2 et budget positif requis")
        if max_par_noeud == 0:
            return set()
        vus, triplets = set(graines), set()
        frontiere = sorted(set(graines))
        for _ in range(profondeur):
            suivante = []
            for u in frontiere:
                n = 0
                for rel, sens, v in self.voisins(u):
                    if rels and rel not in rels:
                        continue
                    t = (u, rel, v) if sens == "->" else (v, rel, u)
                    triplets.add(t)
                    n += 1
                    if v not in vus:
                        vus.add(v)
                        suivante.append(v)
                    if n >= max_par_noeud:
                        break
            frontiere = suivante
        return triplets

    def chemins(self, a, b, longueur_max=2, rels=None, max_chemins=10, max_expansions=100000):
        """Chemins simples non orientés de a vers b (BFS), sous forme de listes de triplets."""
        if not 0 <= longueur_max <= 2 or max_chemins < 0:
            raise ValueError("Chemins limites a deux sauts")
        res = []
        expansions = 0
        file = deque([(a, [])])
        while file and len(res) < max_chemins:
            u, chemin = file.popleft()
            if len(chemin) >= longueur_max:
                continue
            noeuds_chemin = {a} | {x for t in chemin for x in (t[0], t[2])}
            for rel, sens, v in self.voisins(u):
                expansions += 1
                if expansions > max_expansions:
                    raise ValueError("Budget d'exploration depasse; restreindre les relations")
                if rels and rel not in rels:
                    continue
                if v in noeuds_chemin:
                    continue
                t = (u, rel, v) if sens == "->" else (v, rel, u)
                if v == b:
                    res.append(chemin + [t])
                    if len(res) >= max_chemins:
                        return res
                elif self.type[v] not in ("Side Effect",):  # les effets ne servent pas de relais
                    file.append((v, chemin + [t]))
        return res


def charger_graphe(data_dir=DATA) -> Graphe:
    """Charge uniquement TSV/GZIP, jamais le cache pickle fourni."""
    dossier = Path(data_dir)
    noeuds = pd.read_csv(dossier / "hetionet-v1.0-nodes.tsv", sep="\t", dtype=str)
    aretes = pd.read_csv(dossier / "hetionet-v1.0-edges.sif.gz", sep="\t", dtype=str)
    noeuds = noeuds[noeuds["kind"].isin(TYPES_UTILES)].reset_index(drop=True)
    aretes = aretes[aretes["metaedge"].isin(METAEDGES)].reset_index(drop=True)
    return Graphe(noeuds, aretes)


def resume(g: Graphe):
    print({k: len(v) for k, v in g.par_type.items()})
    print("arêtes :", g.n_aretes)


if __name__ == "__main__":
    g = charger_graphe()
    resume(g)
    met = next(i for i, n in g.nom.items() if n == "Metformin")
    print(sorted(g.nom[d] for d in g.successeurs(met, "CtD")))
