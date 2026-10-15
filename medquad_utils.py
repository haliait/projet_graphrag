"""Corpus MedQuAD (Ben Abacha & Demner-Fushman, BMC Bioinformatics 2019, github.com/abachaa/MedQuAD).

On utilise les sous-collections 1 à 9. Les sous-collections 10 à 12 (MedlinePlus ADAM, Drugs,
Herbs) ont des réponses vides (retirées pour raisons de droits) : elles sont ignorées.

Chaque paire question-réponse est découpée en passages d'environ 120 mots, indexés par BM25
(même formule que le notebook S2_demo_RAG : k1 = 1,5 ; b = 0,75), implémenté en matrices creuses.
"""
from __future__ import annotations

import glob
import json
import math
import os
import re
from defusedxml import ElementTree as ET
from entites import normaliser

import numpy as np
from scipy import sparse

ICI = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ICI, "data")
FICHIER_PASSAGES = os.path.join(DATA, "medquad_passages.jsonl")
COLLECTIONS = ["1_CancerGov_QA", "2_GARD_QA", "3_GHR_QA", "4_MPlus_Health_Topics_QA", "5_NIDDK_QA",
               "6_NINDS_QA", "7_SeniorHealth_QA", "8_NHLBI_QA_XML", "9_CDC_QA"]

STOP = set("""a an the of and or in on to for with by is are was were be been being it its this that these those
as at from what which who whom how why when where do does did can could may might should would will shall
i you he she we they my your our their me him her them not no yes about into than then there here also such
some any all each other more most many much very so if but s t""".split())


def tokeniser(texte: str):
    return [m for m in re.findall(r"[a-z0-9]+", texte.lower()) if m not in STOP and len(m) > 1]


# ---------------------------------------------------------------------------
# Préparation du corpus (une seule fois)
# ---------------------------------------------------------------------------
def decouper(texte, taille=120, recouvrement=20):
    if taille <= 0 or not 0 <= recouvrement < taille:
        raise ValueError("Decoupage invalide")
    mots = texte.split()
    if len(mots) <= taille:
        return [texte]
    pas = taille - recouvrement
    return [" ".join(mots[i:i + taille]) for i in range(0, max(1, len(mots) - recouvrement), pas)]


def preparer_passages(racine=os.path.join(DATA, "MedQuAD"), sortie=FICHIER_PASSAGES):
    passages = []
    for col in COLLECTIONS:
        for f in sorted(glob.glob(os.path.join(racine, col, "*.xml"))):
            try:
                doc = ET.parse(f).getroot()
            except ET.ParseError as error:
                raise ValueError(f"XML MedQuAD invalide: {f}") from error
            focus = (doc.findtext("Focus") or "").strip()
            synonymes = [s.text.strip() for s in doc.iter("Synonym") if s.text]
            for qa in doc.iter("QAPair"):
                q = (qa.findtext("Question") or "").strip()
                rep = re.sub(r"\s+", " ", (qa.findtext("Answer") or "")).strip()
                if not rep:
                    continue
                for k, morceau in enumerate(decouper(rep)):
                    passages.append({
                        "id": f"{col}/{os.path.basename(f)}/{qa.get('pid')}/{k}",
                        "source": doc.get("source"), "url": doc.get("url"), "focus": focus,
                        "synonymes": synonymes, "qtype": qa.find("Question").get("qtype") if qa.find("Question") is not None else "",
                        "question": q, "texte": morceau,
                    })
    temporaire = str(sortie) + ".part"
    with open(temporaire, "w", encoding="utf-8") as out:
        for p in passages:
            out.write(json.dumps(p, ensure_ascii=False) + "\n")
    os.replace(temporaire, sortie)
    return passages


def charger_passages(chemin=FICHIER_PASSAGES):
    if not os.path.exists(chemin):
        raise FileNotFoundError("MedQuAD absent : executer preparer_donnees.py")
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f]


# ---------------------------------------------------------------------------
# BM25 en matrices creuses
# ---------------------------------------------------------------------------
class BM25:
    def __init__(self, textes, k1=1.5, b=0.75):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("Parametres BM25 invalides")
        self.k1, self.b = k1, b
        self.vocab = {}
        lignes, cols, vals = [], [], []
        longueurs = np.zeros(len(textes))
        for i, t in enumerate(textes):
            toks = tokeniser(t)
            longueurs[i] = len(toks)
            compte = {}
            for w in toks:
                j = self.vocab.setdefault(w, len(self.vocab))
                compte[j] = compte.get(j, 0) + 1
            for j, c in compte.items():
                lignes.append(i); cols.append(j); vals.append(c)
        tf = sparse.csr_matrix((vals, (lignes, cols)), shape=(len(textes), len(self.vocab)), dtype=np.float32)
        N = len(textes)
        df = np.bincount(tf.indices, minlength=len(self.vocab))
        self.idf = np.log(1 + (N - df + 0.5) / (df + 0.5)).astype(np.float32)
        norm = k1 * (1 - b + b * longueurs / (longueurs.mean() if len(longueurs) and longueurs.mean() else 1.0))
        tf = tf.tocoo()
        poids = tf.data * (k1 + 1) / (tf.data + norm[tf.row])
        self.M = sparse.csc_matrix((poids, (tf.row, tf.col)), shape=tf.shape)  # colonnes = termes

    def scores(self, requete: str):
        ids = [self.vocab[w] for w in tokeniser(requete) if w in self.vocab]
        if not ids:
            return np.zeros(self.M.shape[0], dtype=np.float32)
        return np.asarray(self.M[:, ids] @ self.idf[ids]).ravel()


class IndexMedQuAD:
    def __init__(self, chemin=FICHIER_PASSAGES, passages=None):
        self.passages = charger_passages(chemin) if passages is None else passages
        ids = [p["id"] for p in self.passages]
        if len(set(ids)) != len(ids):
            raise ValueError("Identifiants MedQuAD dupliques : regenerer depuis XML")
        self.bm25 = BM25([f"{p['focus']} {p['question']} {p['texte']}" for p in self.passages])
        self.par_focus = {}
        for i, p in enumerate(self.passages):
            for nom in [p["focus"]] + p["synonymes"]:
                self.par_focus.setdefault(normaliser(nom), []).append(i)

    def rechercher(self, requete, k=5, filtre=None):
        if k < 0:
            raise ValueError("k doit etre positif")
        s = self.bm25.scores(requete)
        if filtre is not None:  # restreint aux passages dont le focus est une entité repérée
            masque = np.full(len(s), -np.inf)
            masque[list(filtre)] = 0
            s = s + masque
        ordre = np.argsort(-s, kind="stable")[:k]
        return [(int(i), float(s[i])) for i in ordre if np.isfinite(s[i]) and s[i] > 0]


if __name__ == "__main__":
    ps = preparer_passages()
    print(len(ps), "passages")
    idx = IndexMedQuAD()
    for i, s in idx.rechercher("drugs that treat gout", 3):
        print(round(s, 2), idx.passages[i]["focus"], "|", idx.passages[i]["texte"][:120])
