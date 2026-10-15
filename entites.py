"""Repérage d'entités par dictionnaire de synonymes construit à partir des noms du graphe.

Partagé par les trois briques (recherche, vérification, validation).
Le piège signalé par le sujet : un petit LLM se trompe souvent dans l'extraction d'entités.
On ne lui délègue donc pas cette étape : on fait une correspondance de plus longue chaîne
sur un dictionnaire (noms Hetionet + variantes orthographiques + synonymes usuels documentés).

Point délicat : 207 noms sont partagés entre plusieurs types (« Hypertension » est à la fois
une maladie, un effet indésirable et parfois un symptôme). Le repérage renvoie donc tous les
types possibles ; c'est le contexte (relation demandée) qui tranche.
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

# Synonymes usuels -> (nom exact dans Hetionet, type). Sources : MeSH / MedlinePlus (termes grand public),
# DCI OMS pour les médicaments (aspirine = acide acétylsalicylique, paracétamol = acétaminophène).
SYNONYMES_MANUELS = {
    # maladies
    "high blood pressure": ("hypertension", "Disease"),
    "arterial hypertension": ("hypertension", "Disease"),
    "underactive thyroid": ("hypothyroidism", "Disease"),
    "hypothyroid": ("hypothyroidism", "Disease"),
    "type 2 diabetes": ("type 2 diabetes mellitus", "Disease"),
    "type ii diabetes": ("type 2 diabetes mellitus", "Disease"),
    "diabetes type 2": ("type 2 diabetes mellitus", "Disease"),
    "t2d": ("type 2 diabetes mellitus", "Disease"),
    "type 1 diabetes": ("type 1 diabetes mellitus", "Disease"),
    "alzheimer": ("Alzheimer's disease", "Disease"),
    "alzheimers": ("Alzheimer's disease", "Disease"),
    "alzheimer disease": ("Alzheimer's disease", "Disease"),
    "parkinson": ("Parkinson's disease", "Disease"),
    "parkinson disease": ("Parkinson's disease", "Disease"),
    "crohn disease": ("Crohn's disease", "Disease"),
    "crohns disease": ("Crohn's disease", "Disease"),

    "rheumatoid arthritis": ("rheumatoid arthritis", "Disease"),
    "ra": ("rheumatoid arthritis", "Disease"),
    "lupus": ("systemic lupus erythematosus", "Disease"),
    "epilepsy": ("epilepsy syndrome", "Disease"),
    "seizure disorder": ("epilepsy syndrome", "Disease"),
    "copd": ("chronic obstructive pulmonary disease", "Disease"),
    "aids": ("acquired immunodeficiency syndrome", "Disease"),
    "hiv aids": ("acquired immunodeficiency syndrome", "Disease"),
    "brittle bone disease": ("osteoporosis", "Disease"),
    "bone loss": ("osteoporosis", "Disease"),
    "psoriatic arthritis": ("psoriatic arthritis", "Disease"),
    "coronary heart disease": ("coronary artery disease", "Disease"),
    "hardening of the arteries": ("atherosclerosis", "Disease"),
    # effets indésirables (SIDER utilise l'orthographe britannique MedDRA)
    "liver toxicity": ("Hepatotoxicity", "Side Effect"),
    "liver damage": ("Hepatotoxicity", "Side Effect"),
    "hepatic toxicity": ("Hepatotoxicity", "Side Effect"),
    "bleeding": ("Haemorrhage", "Side Effect"),
    "hemorrhage": ("Haemorrhage", "Side Effect"),
    "slow heart rate": ("Bradycardia", "Side Effect"),
    "slow heartbeat": ("Bradycardia", "Side Effect"),
    "jaw osteonecrosis": ("Osteonecrosis of jaw", "Side Effect"),
    "osteonecrosis of the jaw": ("Osteonecrosis of jaw", "Side Effect"),
    "heart palpitations": ("Palpitations", "Side Effect"),
    "muscle pain": ("Myalgia", "Side Effect"),
    "ringing in the ears": ("Tinnitus", "Side Effect"),
    "lactic acidosis": ("Lactic acidosis", "Side Effect"),
    "low blood sugar": ("Hypoglycaemia", "Side Effect"),
    "hypoglycemia": ("Hypoglycaemia", "Side Effect"),
    "diarrhea": ("Diarrhoea", "Side Effect"),
    "weight gain": ("Weight increased", "Side Effect"),
    "depressed mood": ("Depression", "Side Effect"),
    # médicaments
    "aspirin": ("Acetylsalicylic acid", "Compound"),
    "paracetamol": ("Acetaminophen", "Compound"),
    "mtx": ("Methotrexate", "Compound"),
    "coumadin": ("Warfarin", "Compound"),
    "glucophage": ("Metformin", "Compound"),
    "levothyrox": ("Levothyroxine", "Compound"),
    "ciclosporin": ("Cyclosporine", "Compound"),
    "cyclosporin": ("Cyclosporine", "Compound"),
    "glibenclamide": ("Glyburide", "Compound"),
    "salbutamol": ("Salbutamol", "Compound"),
    "albuterol": ("Salbutamol", "Compound"),
    # classes pharmacologiques
    "prostaglandin analogues": ("Prostaglandins", "Pharmacologic Class"),
    "prostaglandin analogs": ("Prostaglandins", "Pharmacologic Class"),
    "bisphosphonates": ("Diphosphonates", "Pharmacologic Class"),

    "benzodiazepine": ("Benzodiazepines", "Pharmacologic Class"),
}

# variantes orthographiques britannique / américaine
VARIANTES = [("haem", "hem"), ("oedema", "edema"), ("diarrhoea", "diarrhea"), ("oesoph", "esoph"),
             ("aemia", "emia"), ("aemia", "emia")]

MOTS_OUTILS = set("""a an the and or of to for in on by with which what who that are is be can may known
does do did drugs drug medicines medications treat treats used cause causes""".split())

TYPES = ("Disease", "Compound", "Side Effect", "Symptom", "Pharmacologic Class")


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    texte = texte.lower().replace("'s ", " ").replace("'s", "").replace("'", "")
    texte = re.sub(r"[^a-z0-9]+", " ", texte)
    return re.sub(r"\s+", " ", texte).strip()


@dataclass
class Mention:
    debut: int           # position (en mots) dans le texte normalisé
    fin: int
    texte: str
    candidats: dict = field(default_factory=dict)  # type -> id du nœud
    exact: bool = True   # False si obtenu par correspondance approchée

    def id(self, type_=None):
        if type_:
            return self.candidats.get(type_)
        for t in TYPES:  # ordre de préférence par défaut
            if t in self.candidats:
                return self.candidats[t]


class Dictionnaire:
    def __init__(self, g, synonymes=True, approche=False):
        self.g = g
        self.approche = approche
        self.entrees = {}  # forme normalisée -> {type: id}
        for nid, nom in g.nom.items():
            t = g.type[nid]
            for forme in self._formes(nom):
                self.entrees.setdefault(forme, {}).setdefault(t, nid)
        if synonymes:
            index_nom = {(normaliser(n), g.type[i]): i for i, n in g.nom.items()}
            for syn, (nom, t) in SYNONYMES_MANUELS.items():
                nid = index_nom.get((normaliser(nom), t))
                if nid:
                    for forme in self._formes(syn):
                        self.entrees.setdefault(forme, {})[t] = nid
        collisions = {}
        for nid, nom in sorted(g.nom.items()):
            for forme in self._formes(nom):
                collisions.setdefault((forme, g.type[nid]), set()).add(nid)
        self.ambiguites = {f: sorted(ids) for (f, t), ids in collisions.items() if len(ids) > 1}
        for (forme, typ), ids in collisions.items():
            if len(ids) > 1:
                self.entrees.get(forme, {}).pop(typ, None)
        self.longueur_max = max((len(f.split()) for f in self.entrees), default=1)
        self._formes_liste = sorted(f for f in self.entrees if len(f) >= 6)

    @staticmethod
    def _formes(nom):
        base = normaliser(nom)
        formes = {base, normaliser(nom.replace("'s", "s"))}
        for a, b in VARIANTES:
            if a in base:
                formes.add(base.replace(a, b))
        # pluriel simple pour les noms d'une ou deux unités (« beta blockers », « statins »)
        formes |= {f + "s" for f in list(formes) if not f.endswith("s") and len(f.split()) <= 3}
        return formes

    def reperer(self, texte: str, types=None, approche=None):
        """Plus longue correspondance, de gauche à droite. Renvoie une liste de Mention.
        `approche=False` désactive la correspondance approchée (plus rapide, pour les longs passages)."""
        approche = self.approche if approche is None else approche
        mots = normaliser(texte).split()
        res, i = [], 0
        while i < len(mots):
            trouve = None
            for n in range(min(self.longueur_max, len(mots) - i), 0, -1):
                forme = " ".join(mots[i:i + n])
                cands = self.entrees.get(forme)
                if cands and (types is None or set(cands) & set(types)):
                    if n == 1 and len(forme) <= 2 and forme not in ("ms", "ra"):
                        continue  # évite les faux positifs sur des mots très courts
                    trouve = Mention(i, i + n, forme, {t: v for t, v in cands.items() if types is None or t in types})
                    break
            if trouve is None and approche and mots[i] not in MOTS_OUTILS:
                trouve = self._approche(mots, i, types)
            if trouve:
                res.append(trouve)
                i = trouve.fin
            else:
                i += 1
        return res

    def _approche(self, mots, i, types):
        """Correspondance approchée (fautes de frappe) sur 1 à 3 mots, seuil de similarité 0,9."""
        for n in (3, 2, 1):
            if i + n > len(mots):
                continue
            forme = " ".join(mots[i:i + n])
            if len(forme) < 7:
                continue
            proches = difflib.get_close_matches(forme, self._formes_liste, n=1, cutoff=0.9)
            if proches:
                cands = self.entrees[proches[0]]
                if types is None or set(cands) & set(types):
                    return Mention(i, i + n, forme, {t: v for t, v in cands.items() if types is None or t in types}, exact=False)
        return None
