"""BRIQUE 2 — Vérification par règles (responsable : Enzo Ferrier).

Entrée : la réponse en texte libre (gabarit, LLM simulé ou vrai LLM) + le plan de la question
+ le contexte fourni au générateur. Sortie : un rapport qui donne, pour chaque affirmation, un
statut, la règle qui l'a établi et une explication (chemin dans le graphe ou raison du doute).

1. Extraction des affirmations (sans LLM) : découpage en phrases, repérage d'entités par le
   dictionnaire de synonymes, déclencheurs lexicaux de relation, appariement sujet / objets selon
   la signature typée de la relation, coordination (« X treats D and can cause E »), négation.
   Quand une phrase cite des entités du type attendu sans relation explicite (liste à puces d'un
   LLM), on reconstruit les affirmations implicites à partir des contraintes de la question.

2. Règles de vérification, appliquées dans l'ordre (la première qui conclut l'emporte) :
   R8  mémoire de l'expert : fait validé -> SOUTENUE ; fait rejeté -> CONTRADICTOIRE
   R6  entité absente du graphe, ou présente sous un autre type -> NON_VERIFIABLE
   R1  arête présente dans le graphe -> SOUTENUE (explication = le triplet et sa source)
   R3  affirmation niée alors que l'arête existe -> CONTRADICTOIRE
   R4  affirmation niée, arête absente -> NON_VERIFIABLE (monde ouvert : on ne prouve pas un « non »)
   R5  couverture : la source n'a aucune arête de ce type pour ce sujet (ex. warfarine sans effet
       indésirable dans SIDER/Hetionet) -> NON_VERIFIABLE, et surtout pas « faux »
   R2  relation voisine : « traite » alors que le graphe dit « soulage » (CpD), ou effet plus
       spécifique qu'un effet présent (« Lactic acidosis » / « Acidosis ») -> PARTIELLE
   R7  entités et relation couvertes, arête absente -> NON_SOUTENUE (absent du graphe ≠ faux)
   Règles au niveau de la réponse :
   R9  fidélité au contexte : l'affirmation est-elle portée par le contexte donné au générateur ?
       une citation [Tn] qui ne correspond pas au triplet est signalée
   R10 conformité à la question : chaque élément de réponse doit satisfaire toutes les contraintes
       (2 sauts : « traite X » ET « provoque Y »)
   R11 complétude : éléments que le graphe donne et que la réponse omet

Sources des règles : schéma et provenance de Hetionet (Himmelstein et al., eLife 2017) — CtD/CpD
issus de PharmacotherapyDB (indications validées par des médecins, « treats » ≠ « palliates »),
CcSE issu de SIDER 4.1 (effets listés dans les notices : couverture incomplète, MedDRA hiérarchique),
DpS/DrD issus de co-occurrences MEDLINE. Monde ouvert : cours IA hybride, séance 1 (chaînage arrière,
hypothèse du monde clos et ses risques en aide à la décision clinique).
Une version ProbLog des mêmes règles est dans brique2_problog.py / regles_verification.pl.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from entites import normaliser
from hetionet_utils import METAEDGES
from plans import INTENTIONS, executer

# --- statuts et poids ---------------------------------------------------------
SOUTENUE, PARTIELLE, NON_SOUTENUE, NON_VERIFIABLE, CONTRADICTOIRE = (
    "SOUTENUE", "PARTIELLE", "NON_SOUTENUE", "NON_VERIFIABLE", "CONTRADICTOIRE")
POIDS = {SOUTENUE: 1.0, PARTIELLE: 0.6, NON_VERIFIABLE: 0.3, NON_SOUTENUE: 0.1, CONTRADICTOIRE: 0.0}

# --- déclencheurs de relation (sur texte normalisé) -----------------------------
# (relation, motif, inverse) ; inverse = le sujet de la relation est à droite du déclencheur
DECLENCHEURS = [
    ("CpD", r"\b(relieves?|relief of|palliates?|alleviates?)\b( the symptoms of)?", False),
    ("DpS", r"\b(is|are) (a |an )?(common )?(symptom|sign|manifestation)s? of\b( both)?", True),
    ("DpS", r"\b(presents?|presenting) with\b|\bhas the symptoms?\b|\bcauses? symptoms such as\b", False),
    ("DrD", r"\b(resembles?|is similar to|similar to)\b", False),
    ("PCiC", r"\b(belongs? to|is a member of|is one of)\b( the)?( class| group)?( of)?", True),
    ("CcSE", r"\b(can |may |is known to |are known to |could |might )?(cause|causes|caused|induce|induces|lead to|leads to|provoke|provokes)\b", False),
    ("CcSE", r"\bside effects? (include|includes|is|are)\b|\b(is|are) associated with\b", False),
    ("CtD", r"\b(treats|treat|treating|is used to treat|are used to treat|is indicated for|are indicated for|is used for|used for|is a treatment for|therapy for)\b( both)?", False),
]
R_NEGATION = re.compile(r"\b(not|no|never|cannot|doesnt|dont|isnt|arent|without)\b")
R_ABSTENTION = re.compile(r"(does not state|do not state|not found|do not answer|does not answer|cannot interpret|"
                          r"cannot identify|no (drug|symptom|disease|answer)\b.*\bfound|i don ?t know|not in the context)")
R_CITATION = re.compile(r"\[([TP])(\d+)\]")


@dataclass
class Affirmation:
    sujet: str | None
    relation: str
    objet: str | None
    nie: bool = False
    phrase: str = ""
    citations: list = field(default_factory=list)
    implicite: bool = False
    exacte: bool = True                      # repérage exact (pas de correspondance approchée)
    textes: tuple = ("", "")                 # surface des mentions
    hors_type: tuple = (None, None)          # mentions repérées mais d'un autre type
    # rempli par la vérification
    statut: str | None = None
    regle: str | None = None
    explication: str = ""
    dans_contexte: bool | None = None

    def cle(self):
        return (self.sujet, self.relation, self.objet)


@dataclass
class RapportVerification:
    affirmations: list
    elements: dict            # élément de réponse -> statut agrégé (min sur ses contraintes)
    omissions: list
    attendus_graphe: set
    score: float
    completude: float
    drapeaux: list
    candidats_proches: list = field(default_factory=list)
    abstention: bool = False
    oui_non: bool | None = None


# ==============================================================================
# 1. Extraction des affirmations
# ==============================================================================
class Extracteur:
    def __init__(self, g, dico):
        self.g, self.dico = g, dico

    def phrases(self, texte):
        texte = re.sub(r"\n\s*[-*•\d.)]+\s*", ". ", texte)   # listes à puces -> phrases
        return [p.strip() for p in re.split(r"(?<=[.!?;])\s+|\n+", texte) if p.strip()]

    def extraire(self, texte, plan):
        affs, abstention, oui_non = [], False, None
        for ph in self.phrases(texte):
            cits = [f"{a}{b}" for a, b in R_CITATION.findall(ph)]
            brute = R_CITATION.sub(" ", ph)
            norm = normaliser(brute)
            if R_ABSTENTION.search(norm):
                abstention = True
                continue
            if re.match(r"(yes)\b", norm):
                oui_non = True
            elif re.match(r"(no)\b", norm):
                oui_non = False
            affs.extend(self._phrase(brute, norm, cits, plan))
        if plan.intention == "causes_yesno" and oui_non is False:
            for a in affs:
                if a.relation == "CcSE":
                    a.nie = True
        return affs, abstention, oui_non

    def _declencheurs(self, norm, mentions):
        trig, occupe = [], set()
        for rel, motif, inverse in DECLENCHEURS:
            for mt in re.finditer(motif, norm):
                d = len(norm[:mt.start()].split())
                f = d + len(mt.group(0).split())
                if any(i in occupe for i in range(d, f)):
                    continue
                if any(m.debut < f and d < m.fin for m in mentions):  # déclencheur inclus dans un nom
                    continue
                occupe |= set(range(d, f))
                trig.append((d, f, rel, inverse))
        return sorted(trig)

    def _phrase(self, brute, norm, cits, plan):
        mots = norm.split()
        mentions = self.dico.reperer(brute)
        trig = self._declencheurs(norm, mentions)
        nie_phrase = bool(R_NEGATION.search(norm))
        res = []
        sujets_prec = []          # sujets du déclencheur précédent (coordination)
        for k, (d, f, rel, inverse) in enumerate(trig):
            t_suj, _, t_obj, _, _ = METAEDGES[rel]
            t_gauche, t_droite = (t_obj, t_suj) if inverse else (t_suj, t_obj)
            debut_zone = trig[k - 1][1] if k > 0 else 0
            fin_zone = trig[k + 1][0] if k + 1 < len(trig) else len(mots)
            zone_g = [m for m in mentions if debut_zone <= m.debut and m.fin <= d]
            droite = [m for m in mentions if f <= m.debut < fin_zone]
            neg = nie_phrase and bool(R_NEGATION.search(" ".join(mots[max(0, d - 4):f])))
            # sujets : mentions du bon type entre le déclencheur précédent et celui-ci (« A and B treat D »),
            # sinon la plus proche à gauche, sinon ceux du déclencheur précédent (« X treats D and can cause E »)
            gauches = [m for m in zone_g if t_gauche in m.candidats]
            if not gauches:
                proche = next((m for m in reversed([m for m in mentions if m.fin <= d]) if t_gauche in m.candidats), None)
                if proche is not None and (k == 0 or proche.fin > trig[k - 1][0]):
                    gauches = [proche]
            if not gauches:
                gauches = [m for m in sujets_prec if t_gauche in m.candidats]
            if not gauches and zone_g:
                gauches = zone_g[-1:]          # mention d'un autre type : conservée pour la règle R6
            droites = [m for m in droite if t_droite in m.candidats] or droite[:1]
            for gm in gauches:
                if not droites:
                    if inverse or t_gauche not in gm.candidats:
                        continue
                    # objet non reconnu (« treats a related disease ») -> affirmation à objet inconnu (R6)
                    reste = " ".join(mots[f:fin_zone]) or "?"
                    res.append(Affirmation(gm.candidats[t_gauche], rel, None, neg, brute.strip(), cits,
                                           exacte=gm.exact, textes=(gm.texte, reste), hors_type=(None, reste)))
                    continue
                for dm in droites:
                    gid, did = gm.candidats.get(t_gauche), dm.candidats.get(t_droite)
                    st, ot = (dm, gm) if inverse else (gm, dm)
                    s, o = (did, gid) if inverse else (gid, did)
                    res.append(Affirmation(s, rel, o, neg, brute.strip(), cits,
                                           exacte=st.exact and ot.exact, textes=(st.texte, ot.texte),
                                           hors_type=(None if s else st.texte, None if o else ot.texte)))
            # le sujet « porteur » pour le déclencheur suivant
            if inverse:
                sujets_prec = [m for m in gauches if t_gauche in m.candidats]
            else:
                sujets_prec = [m for m in gauches if t_gauche in m.candidats]
        # affirmations implicites : entités du type attendu sans relation explicite (liste d'un LLM)
        if not trig and plan.intention and plan.type_reponse:
            for m in mentions:
                x = m.candidats.get(plan.type_reponse)
                if x and x not in plan.emplacements.values():
                    for rel, sens, nom in INTENTIONS[plan.intention][2]:
                        if nom not in plan.emplacements:
                            continue
                        e = plan.emplacements[nom]
                        s, o = (x, e) if sens == "vers" else (e, x)
                        res.append(Affirmation(s, rel, o, nie_phrase, brute.strip(), cits, implicite=True,
                                               exacte=m.exact, textes=(m.texte, "")))
        return res


# ==============================================================================
# 2. Règles
# ==============================================================================
class Verificateur:
    def __init__(self, g, dico, memoire=None, regles_actives=None):
        self.g, self.dico = g, dico
        self.extracteur = Extracteur(g, dico)
        self.memoire = memoire          # brique 3 : corrections de l'expert (peut être None)
        self._cache = {}                # entités repérées par passage MedQuAD
        self.actives = set(regles_actives or ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R12"])

    # --- règles élémentaires, sur une affirmation -----------------------------
    def couverture(self, s, rel):
        """La source couvre-t-elle ce sujet pour cette relation ? (au moins une arête du même type)"""
        if rel == "CtD":  # PharmacotherapyDB : un composé « couvert » a au moins une indication CtD ou CpD
            return self.g.degre(s, "CtD") + self.g.degre(s, "CpD") > 0
        return self.g.degre(s, rel) > 0

    def effet_plus_general(self, s, o):
        """R2 : effets présents pour s dont le nom est contenu dans celui de o (hiérarchie MedDRA approchée)."""
        nom_o = set(normaliser(self.g.nom[o]).split())
        res = []
        for e in self.g.successeurs(s, "CcSE"):
            ne = set(normaliser(self.g.nom[e]).split())
            if ne and ne < nom_o:
                res.append(e)
        return res

    def verifier_affirmation(self, a: Affirmation):
        g = self.g
        on = lambda r: r in self.actives
        lisible = lambda: g.triplet_lisible(a.sujet, a.relation, a.objet)
        # R8 — mémoire de l'expert
        if on("R8") and self.memoire is not None and a.sujet and a.objet:
            verdict = self.memoire.fait(a.sujet, a.relation, a.objet)
            if verdict is not None:
                ok, source = verdict
                if ok != a.nie:
                    return SOUTENUE, "R8", f"validé par l'expert ({source})"
                return CONTRADICTOIRE, "R8", f"contredit par une correction de l'expert ({source})"
        # R6 — entité hors graphe ou d'un autre type
        if a.sujet is None or a.objet is None:
            manquant = a.hors_type[0] or a.hors_type[1] or a.textes[0] or a.textes[1] or "?"
            t_suj, _, t_obj, _, _ = METAEDGES[a.relation]
            if on("R6"):
                return NON_VERIFIABLE, "R6", (f"« {manquant} » n'est pas un nœud de type attendu "
                                              f"({t_suj} -> {t_obj}) dans Hetionet : hors périmètre du graphe")
            return NON_SOUTENUE, "-", "entité non reconnue"
        arete = g.a_arete(a.sujet, a.relation, a.objet)
        source = METAEDGES[a.relation][4]
        # R1 / R3
        if arete and not a.nie:
            return SOUTENUE, "R1", f"{lisible()}  [Hetionet {a.relation}, {source}]"
        if arete and a.nie and on("R3"):
            return CONTRADICTOIRE, "R3", f"la réponse nie un fait présent : {lisible()} [{source}]"
        if a.nie:
            if on("R4"):
                return NON_VERIFIABLE, "R4", "négation sans arête : le graphe ne permet pas de prouver un « non » (monde ouvert)"
            return SOUTENUE, "-", "négation acceptée (monde clos)"
        # R5 — couverture de la source
        if on("R5") and not self.couverture(a.sujet, a.relation):
            return NON_VERIFIABLE, "R5", (f"{g.nom[a.sujet]} n'a aucune arête {a.relation} dans Hetionet "
                                          f"({source} ne le couvre pas) : absence d'information, pas une réfutation")
        # R2 — relation voisine
        if on("R2"):
            if a.relation == "CtD" and g.a_arete(a.sujet, "CpD", a.objet):
                return PARTIELLE, "R2", f"le graphe dit « soulage » et non « traite » : {g.triplet_lisible(a.sujet, 'CpD', a.objet)}"
            if a.relation == "CcSE":
                gen = self.effet_plus_general(a.sujet, a.objet)
                if gen:
                    return PARTIELLE, "R2", (f"seul un effet plus général est présent : "
                                             f"{g.triplet_lisible(a.sujet, 'CcSE', gen[0])} [{source}]")
        # R7 — absence d'arête alors que la source est couverte
        if on("R7"):
            return NON_SOUTENUE, "R7", f"aucune arête {g.nom[a.sujet]} --{METAEDGES[a.relation][1]}--> {g.nom[a.objet]} (absent du graphe ≠ faux)"
        return NON_SOUTENUE, "-", "aucune arête"

    def entites_passage(self, p):
        if p["id"] not in self._cache:
            self._cache[p["id"]] = {v for m in self.dico.reperer(p["focus"] + ". " + p["texte"], approche=False)
                                    for v in m.candidats.values()}
        return self._cache[p["id"]]

    # --- R9 : fidélité au contexte ---------------------------------------------
    def fidelite(self, a: Affirmation, ctx):
        if ctx is None or a.sujet is None or a.objet is None:
            return False
        if ctx.sous_graphe is not None and ctx.sous_graphe.a_arete(a.sujet, a.relation, a.objet):
            return True
        for p in ctx.passages:  # passage qui mentionne les deux entités (ou dont l'une est le focus)
            if a.sujet in self.entites_passage(p) and a.objet in self.entites_passage(p):
                return True
        return False

    # --- vérification d'une réponse complète ------------------------------------
    def verifier(self, texte, plan, ctx=None) -> RapportVerification:
        g = self.g
        affs, abstention, oui_non = self.extracteur.extraire(texte, plan)
        for a in affs:
            a.statut, a.regle, a.explication = self.verifier_affirmation(a)
            if "R9" in self.actives:
                a.dans_contexte = self.fidelite(a, ctx)
        drapeaux = []
        if any(a.statut == CONTRADICTOIRE for a in affs):
            drapeaux.append("contradiction")
        if any(a.statut == NON_VERIFIABLE for a in affs):
            drapeaux.append("non_verifiable")
        if any(a.statut == PARTIELLE for a in affs):
            drapeaux.append("partielle")
        if any(a.statut == NON_SOUTENUE for a in affs):
            drapeaux.append("non_soutenue")
        if "R9" in self.actives and any(a.dans_contexte is False for a in affs):
            drapeaux.append("hors_contexte")

        # R10 — conformité : statut d'un élément = le pire statut de ses contraintes
        elements = {}
        t_rep = plan.type_reponse
        if plan.intention and t_rep:
            for a in affs:
                for x in (a.sujet, a.objet):
                    if x and g.type.get(x) == t_rep and x not in plan.emplacements.values():
                        elements.setdefault(x, []).append(a)
            if "R10" in self.actives:
                contraintes = [c for c in INTENTIONS[plan.intention][2] if c[2] in plan.emplacements]
                for x, l in list(elements.items()):
                    statuts = [a.statut for a in l]
                    if plan.intention == "drugs_for_resembling":
                        manquantes = 0 if any(a.relation == "CtD" for a in l) else 1
                    else:  # chaque contrainte (relation, sens, entité de la question) doit être affirmée
                        manquantes = sum(
                            1 for rel, sens, nom in contraintes
                            if not any(a.relation == rel and (a.sujet, a.objet) == ((x, plan.emplacements[nom]) if sens == "vers"
                                                                                   else (plan.emplacements[nom], x)) for a in l))
                    if manquantes > 0:
                        statuts.append(NON_SOUTENUE)
                        drapeaux.append("element_non_conforme")
                    elements[x] = min(statuts, key=lambda s: POIDS[s])
            else:
                elements = {x: min((a.statut for a in l), key=lambda s: POIDS[s]) for x, l in elements.items()}
        # éléments hors graphe (ex. médicament inconnu) : comptés comme éléments non vérifiables
        hors = [a for a in affs if (a.sujet is None or a.objet is None) and plan.type_reponse]
        for a in hors:
            elements.setdefault("?" + (a.textes[0] or a.textes[1]), NON_VERIFIABLE)

        # R11 — complétude par rapport au graphe complet
        attendus = executer(plan, g) if plan.complet() else set()
        omissions = []
        if "R11" in self.actives and plan.intention and plan.intention != "causes_yesno":
            omissions = sorted(attendus - set(elements))
            if omissions:
                drapeaux.append("omissions")
        completude = 1.0 - len(omissions) / max(1, len(attendus)) if attendus else 1.0
        # R12 — candidats proches : éléments qui satisfont la question avec un effet plus général
        # (« Acidosis » pour « Lactic acidosis ») ; le graphe suggère un oubli possible de la source
        candidats = []
        if "R12" in self.actives and plan.intention == "treat_and_cause" and plan.complet():
            e = plan.emplacements
            for x in g.predecesseurs(e["D"], "CtD") - attendus - set(elements):
                if self.effet_plus_general(x, e["SE"]):
                    candidats.append(x)
            if candidats:
                drapeaux.append("candidats_proches")
                completude *= len(attendus) / (len(attendus) + len(candidats)) if attendus else 0.5

        # cas oui / non sans affirmation : on vérifie la question elle-même
        if plan.intention == "causes_yesno" and not affs and plan.complet():
            a = Affirmation(plan.emplacements["C"], "CcSE", plan.emplacements["SE"], phrase="(question)")
            statut, regle, expl = self.verifier_affirmation(a)
            if statut == SOUTENUE:
                drapeaux.append("omissions"); completude = 0.0
            elif statut in (NON_VERIFIABLE, PARTIELLE):
                drapeaux.append("non_verifiable" if statut == NON_VERIFIABLE else "partielle")
            a.statut, a.regle, a.explication = statut, regle, "question : " + expl
            affs.append(a)
            score = {SOUTENUE: 0.1, PARTIELLE: 0.4, NON_VERIFIABLE: 0.3}.get(statut, 0.7)
        elif not elements and not affs:
            if not plan.complet():
                score = 0.2
            elif attendus:
                score = 0.1
            else:
                score = 0.8   # liste vide cohérente avec le graphe (mais absent ≠ faux)
        else:
            vals = list(elements.values()) or [a.statut for a in affs]
            score = sum(POIDS[s] for s in vals) / len(vals)
        if plan.intention is None:
            drapeaux.append("question_non_comprise")
        elif not plan.complet():
            drapeaux.append("entite_hors_graphe")
        return RapportVerification(affs, elements, omissions, attendus, float(score), float(completude),
                                   sorted(set(drapeaux)), candidats, abstention, oui_non)


# ==============================================================================
# 3. Affichage
# ==============================================================================
SYMBOLES = {SOUTENUE: "✔", PARTIELLE: "≈", NON_SOUTENUE: "?", NON_VERIFIABLE: "∅", CONTRADICTOIRE: "✘"}


def expliquer(rapport: RapportVerification, g, max_lignes=30):
    lignes = []
    for a in rapport.affirmations[:max_lignes]:
        s = g.nom.get(a.sujet, a.textes[0] or "?")
        o = g.nom.get(a.objet, a.textes[1] or "?")
        neg = "NON " if a.nie else ""
        ctx = "" if a.dans_contexte is None else (" [dans le contexte]" if a.dans_contexte else " [hors contexte]")
        lignes.append(f"  {SYMBOLES[a.statut]} {a.statut:<15} {a.regle:<3} {neg}{s} --{METAEDGES[a.relation][1]}--> {o}{ctx}\n"
                      f"      {a.explication}")
    if rapport.omissions:
        lignes.append(f"  Omissions (R11) : {', '.join(g.nom[x] for x in rapport.omissions[:15])}"
                      + (" …" if len(rapport.omissions) > 15 else ""))
    if rapport.candidats_proches:
        lignes.append(f"  Candidats proches (R12) : {', '.join(g.nom[x] for x in rapport.candidats_proches)}")
    lignes.append(f"  Score de vérification {rapport.score:.2f} · complétude {rapport.completude:.2f} · drapeaux {rapport.drapeaux}")
    return "\n".join(lignes)
