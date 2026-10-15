"""Tests de l'extraction d'affirmations (brique 2) sur des réponses en texte libre, du type de
celles d'un petit LLM. Lancer : python tests_extraction.py"""
from hetionet_utils import charger_graphe
from entites import Dictionnaire
from plans import analyser_question
from brique2_verification_regles import Extracteur

CAS = [
    # (question, réponse, affirmations attendues (sujet, relation, objet, nié))
    ("Which drugs that treat rheumatoid arthritis are known to cause hepatotoxicity?",
     "Methotrexate and leflunomide both treat rheumatoid arthritis and may cause hepatotoxicity [T1].",
     {("Methotrexate", "CtD", "rheumatoid arthritis", False), ("Leflunomide", "CtD", "rheumatoid arthritis", False),
      ("Methotrexate", "CcSE", "Hepatotoxicity", False), ("Leflunomide", "CcSE", "Hepatotoxicity", False)}),
    ("Which drugs that treat rheumatoid arthritis are known to cause hepatotoxicity?",
     "The drugs are:\n- Methotrexate\n- Azathioprine",
     {("Methotrexate", "CtD", "rheumatoid arthritis", False), ("Methotrexate", "CcSE", "Hepatotoxicity", False),
      ("Azathioprine", "CtD", "rheumatoid arthritis", False), ("Azathioprine", "CcSE", "Hepatotoxicity", False)}),
    ("Does warfarin cause bleeding?", "No, warfarin does not cause bleeding.",
     {("Warfarin", "CcSE", "Haemorrhage", True)}),
    ("Does methotrexate cause hepatotoxicity?", "Yes. Methotrexate is associated with liver damage.",
     {("Methotrexate", "CcSE", "Hepatotoxicity", False)}),
    ("What are the symptoms of gout?", "Gout presents with pain, fever and edema.",
     {("gout", "DpS", "Pain", False), ("gout", "DpS", "Fever", False), ("gout", "DpS", "Edema", False)}),
    ("Which symptoms are shared by gout and rheumatoid arthritis?", "Fever is a symptom of both gout and rheumatoid arthritis.",
     {("gout", "DpS", "Fever", False), ("rheumatoid arthritis", "DpS", "Fever", False)}),
    ("Which drugs used for hypothyroidism may cause palpitations?",
     "Levothyroxine, which is used to treat hypothyroidism, can cause palpitations.",
     {("Levothyroxine", "CtD", "hypothyroidism", False), ("Levothyroxine", "CcSE", "Palpitations", False)}),
    ("Which prostaglandins treat glaucoma?", "Latanoprost belongs to the class Prostaglandins and treats glaucoma.",
     {("Prostaglandins", "PCiC", "Latanoprost", False), ("Latanoprost", "CtD", "glaucoma", False)}),
    ("Which drugs treat a disease that resembles Creutzfeldt-Jakob disease?",
     "Donepezil treats Alzheimer's disease, which resembles Creutzfeldt-Jakob disease.",
     {("Donepezil", "CtD", "Alzheimer's disease", False), ("Alzheimer's disease", "DrD", "Creutzfeldt-Jakob disease", False)}),
    ("Which drugs relieve the symptoms of migraine?", "Sumatriptan relieves the symptoms of migraine; ibuprofen too.",
     {("Sumatriptan", "CpD", "migraine", False), ("Ibuprofen", "CpD", "migraine", False)}),  # ellipse : relation implicite
    ("Which drugs for Alzheimer's disease can cause bradycardia?", "Donepzil treats Alzheimers disease and can cause slow heart rate.",
     {("Donepezil", "CtD", "Alzheimer's disease", False), ("Donepezil", "CcSE", "Bradycardia", False)}),
]

if __name__ == "__main__":
    g = charger_graphe(); d = Dictionnaire(g, approche=True); ex = Extracteur(g, d)  # comme pipeline.py
    ok = tot_att = tot_trouve = vp = 0
    for q, rep, attendu in CAS:
        affs, _, _ = ex.extraire(rep, analyser_question(q, d))
        trouve = {(g.nom.get(a.sujet, "?"), a.relation, g.nom.get(a.objet, "?"), a.nie) for a in affs}
        vp += len(trouve & attendu); tot_att += len(attendu); tot_trouve += len(trouve)
        statut = "OK " if trouve == attendu else "ÉCART"
        ok += trouve == attendu
        print(statut, rep)
        if trouve != attendu:
            print("     manquantes :", attendu - trouve, "\n     en trop :", trouve - attendu)
    print(f"\n{ok}/{len(CAS)} réponses parfaitement extraites · précision {vp/tot_trouve:.2f} · rappel {vp/tot_att:.2f}")
