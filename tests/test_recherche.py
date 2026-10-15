import json
import unittest
import pandas as pd
from brique1_recherche_graphe import RechercheGraphe
from entites import Dictionnaire
from hetionet_utils import Graphe
from medquad_utils import BM25, IndexMedQuAD, decouper
from plans import analyser_question
from rag_classique import RAGClassique


def fixture():
    nodes = pd.DataFrame([
        ("d1", "gout", "Disease"), ("d2", "arthritis", "Disease"),
        ("c1", "DrugAlpha", "Compound"), ("c2", "DrugBeta", "Compound"),
        ("se", "Hepatotoxicity", "Side Effect"), ("s", "Pain", "Symptom")],
        columns=["id", "name", "kind"])
    edges = pd.DataFrame([("c1", "CtD", "d1"), ("c2", "CpD", "d1"),
        ("c1", "CcSE", "se"), ("d1", "DrD", "d2"), ("d1", "DpS", "s")],
        columns=["source", "metaedge", "target"])
    graph = Graphe(nodes, edges)
    passages = [dict(id="synthetic-1", source="synthetic fixture", url="https://example.org/fixture",
                     focus="gout", synonymes=[], question="What is gout?", texte="Gout synthetic evidence.")]
    return graph, Dictionnaire(graph), IndexMedQuAD(passages=passages)


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.g, self.d, self.i = fixture()
        self.r = RechercheGraphe(self.g, self.d, self.i)

    def test_atomic_two_hop(self):
        q = "Which drugs treat gout and cause hepatotoxicity?"
        result = self.r.rechercher(q)
        self.assertEqual(set(result.triplets), {("c1", "CtD", "d1"), ("c1", "CcSE", "se")})
        small = RechercheGraphe(self.g, self.d, self.i, budget_triplets=1).rechercher(q)
        self.assertEqual(small.triplets, [])
        self.assertIn("graph_budget_truncated", small.details["warnings"])

    def test_treats_not_palliates(self):
        self.assertEqual(self.r.rechercher("What drugs treat gout?").triplets, [("c1", "CtD", "d1")])

    def test_open_world(self):
        c = self.r.rechercher("Does DrugBeta cause hepatotoxicity?")
        self.assertEqual(c.details["status"], "not_documented_in_retrieved_graph")
        self.assertEqual(c.score, 0)

    def test_symmetry_and_direction(self):
        self.assertTrue(self.g.a_arete("d2", "DrD", "d1"))
        self.assertFalse(self.g.a_arete("d1", "CtD", "c1"))
        self.assertEqual(self.g.chemins("d1", "se"), [[("c1", "CtD", "d1"), ("c1", "CcSE", "se")]])

    def test_unsupported_constraint(self):
        for q in ["What drugs treat gout without hepatotoxicity?", "What drugs treat gout or arthritis?",
                  "Which drugs treat gout and cause xyzunknown?", "Quels medicaments traitent la goutte?"]:
            self.assertIsNone(analyser_question(q, self.d).intention, q)

    def test_boundaries(self):
        self.assertEqual(self.d.reperer("goutish"), [])
        for q in ["", "x" * 2001]:
            with self.assertRaises(ValueError):
                self.r.rechercher(q)

    def test_context_contract(self):
        c = self.r.rechercher("What drugs treat gout?")
        payload = json.loads(json.dumps(c.exporter(self.g)))
        self.assertEqual(payload["schema_version"], "1.0")
        self.assertFalse(payload["score_is_probability"])
        self.assertEqual(payload["graph_evidence"][0]["citation"], "T1")
        self.assertEqual(payload["passages"][0]["citation"], "P1")
        self.assertLessEqual(len(payload["context"]), 12000)

    def test_non_hybrid(self):
        c = RAGClassique(self.i).rechercher("What drugs treat gout?")
        self.assertIsNone(c.plan.intention)
        self.assertEqual(c.triplets, [])
        self.assertTrue(c.passages)

    def test_empty_bm25(self):
        self.assertEqual(BM25([]).scores("gout").tolist(), [])
        self.assertEqual(BM25([""]).scores("gout").tolist(), [0])

    def test_limits(self):
        self.assertEqual(self.g.voisinage(["d1"], max_par_noeud=0), set())
        with self.assertRaises(ValueError):
            self.g.chemins("d1", "se", longueur_max=3)
        with self.assertRaises(ValueError):
            decouper("abc", taille=2, recouvrement=2)

    def test_invalid_edge(self):
        with self.assertRaises(ValueError):
            self.g.ajouter("d1", "CtD", "c1")

    def test_no_ignored_compound(self):
        self.assertIsNone(analyser_question("Does DrugAlpha treat gout?", self.d).intention)
        self.assertIsNone(analyser_question("What drugs treat both gout and xyzunknown?", self.d).intention)

    def test_expansion_limit(self):
        with self.assertRaises(ValueError):
            self.g.chemins("d1", "se", max_expansions=1)

    def test_duplicate_passage(self):
        with self.assertRaises(ValueError):
            IndexMedQuAD(passages=self.i.passages * 2)

    def test_same_type_ambiguity(self):
        nodes = pd.DataFrame([("a", "Gout", "Disease"), ("b", "Gout", "Disease")], columns=["id", "name", "kind"])
        g = Graphe(nodes, pd.DataFrame([], columns=["source", "metaedge", "target"]))
        d = Dictionnaire(g)
        self.assertEqual(d.reperer("gout"), [])
        self.assertIn("gout", d.ambiguites)

    def test_repeatability(self):
        q = "Which drugs treat gout and cause hepatotoxicity?"
        self.assertEqual(self.r.rechercher(q).texte(self.g), self.r.rechercher(q).texte(self.g))


if __name__ == "__main__":
    unittest.main()
