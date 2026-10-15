"""Interface expert. Lancer depuis la racine : streamlit run brique3_validation/interface.py"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from brique3_validation.file_attente import FileAttente
from brique3_validation.memoire import Memoire

st.set_page_config(page_title="Validation expert", layout="wide")
ICONES = {"SOUTENUE": "🟢", "PARTIELLE": "🟡", "NON_VERIFIABLE": "⚪", "NON_SOUTENUE": "🟠",
          "CONTRADICTOIRE": "🔴"}
file, memoire = FileAttente(), Memoire()


@st.cache_resource
def expert_simule():
    from hetionet_utils import charger_graphe
    from brique3_validation.expert_simule import ExpertSimule
    return ExpertSimule(charger_graphe())


# ---------- barre latérale ----------
st.sidebar.header("File d'attente")
for statut, n in file.statistiques().items():
    st.sidebar.write(f"**{statut}** : {n}")
if st.sidebar.button("Traiter toute la file avec l'expert simulé"):
    expert = expert_simule()
    for ligne in file.en_attente():
        o = json.loads(ligne["objet"])
        statut, reponse, corrections, temps = expert.traiter(o)
        file.enregistrer(ligne["cle"], statut, reponse, corrections, temps, "expert_simule")
        memoire.enregistrer_correction(o, reponse, corrections)
    st.rerun()

# ---------- réponse à traiter ----------
st.title("Validation des réponses de l'assistant")
ligne = file.prochaine()
if ligne is None:
    st.success("Aucune réponse en attente.")
    st.stop()

o, cle = json.loads(ligne["objet"]), ligne["cle"]
if st.session_state.get("cle") != cle:
    st.session_state["cle"], st.session_state["debut"] = cle, time.time()

st.subheader(f"{o['id']} · {o.get('formulation')} · {o.get('systeme')} · {o.get('sauts', '?')} saut(s)")
c1, c2, c3 = st.columns(3)
c1.metric("Confiance", o["confiance"])
c2.metric("Score de recherche", o["score_recherche"])
c3.metric("Score de vérification", o["score_verification"])
st.warning(f"Raison de l'escalade : {ligne['raison']}")
st.markdown(f"**Question :** {o['question']}")
st.markdown(f"**Réponse de l'assistant** ({o.get('generateur', '?')}) : {o.get('reponse') or '(vide)'}")

st.markdown("### Affirmations extraites (brique 2)")
verdicts = []
for i, a in enumerate(o.get("affirmations", [])):
    g, d = st.columns([4, 2])
    neg = "NON " if a.get("nie") else ""
    g.write(f"{ICONES.get(a.get('statut'), '❔')} **{a.get('sujet_nom') or a.get('sujet')} {neg}{a.get('relation')} {a.get('objet_nom') or a.get('objet')}** "
            f"· {a.get('statut')} ({a.get('regle')})")
    if a.get("explication"):
        g.caption(a["explication"])
    choix = d.radio("Verdict", ["Vraie", "Fausse"],
                    index=1 if a.get("statut") in ("CONTRADICTOIRE", "NON_SOUTENUE") else 0,
                    key=f"{cle}_{i}", horizontal=True, label_visibility="collapsed")
    verdicts.append((a, choix == "Vraie"))
if not o.get("affirmations"):
    st.info("Aucune affirmation extraite.")

with st.expander(f"Preuves du graphe ({len(o.get('preuves', []))})"):
    for p in o.get("preuves", []):
        st.write(f"[{p.get('citation')}] {p.get('source_name')} —{p.get('relation')}→ {p.get('target_name')}")
with st.expander(f"Passages MedQuAD ({len(o.get('passages', []))})"):
    for p in o.get("passages", []):
        st.caption(f"[{p.get('citation')}] {p.get('source')}")
        st.write((p.get("texte") or p.get("text") or "")[:800])

synonymes = {}
if o.get("non_lies"):
    st.markdown("### Entités non reconnues")
    for m in o["non_lies"]:
        texte = m.get("texte") if isinstance(m, dict) else str(m)
        correction = st.text_input(f"Identifiant Hetionet pour « {texte} »", key=f"{cle}_syn_{texte}")
        if correction.strip():
            synonymes[texte] = correction.strip()

reponse_finale = st.text_area("Réponse finale", value=o.get("reponse") or "", key=f"{cle}_rep")
b1, b2, b3 = st.columns(3)
action = ("validee" if b1.button(" Valider") else
          "corrigee" if b2.button("Enregistrer la correction") else
          "rejetee" if b3.button("Rejeter") else None)

if action:
    corrections = {"affirmations": [{"triplet": [a.get("sujet"), a.get("relation"), a.get("objet")],
                                     "vraie": vraie != bool(a.get("nie"))}
                                    for a, vraie in verdicts if a.get("sujet") not in (None, "?")],
                   "synonymes": synonymes}
    temps = round(time.time() - st.session_state["debut"], 1)
    file.enregistrer(cle, action, reponse_finale, corrections, temps, "humain")
    memoire.enregistrer_correction(o, reponse_finale, corrections)
    st.rerun()