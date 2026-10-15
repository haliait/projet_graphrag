"""Non-hybrid reference: BM25 only. No graph, dictionary or graph-derived plan."""
import time
from brique1_recherche_graphe import Contexte, valider_question
from plans import Plan


class RAGClassique:
    def __init__(self, index_medquad, k=3, budget_caracteres=12000):
        if not 0 <= k <= 20 or not 500 <= budget_caracteres <= 100000:
            raise ValueError("Budgets invalides")
        self.index, self.k, self.budget = index_medquad, k, budget_caracteres

    def rechercher(self, question):
        valider_question(question)
        t0 = time.perf_counter()
        ctx = Contexte(question, Plan(None), systeme="rag")
        for i, s in self.index.rechercher(question, self.k):
            ctx.passages.append(dict(self.index.passages[i], score_bm25=s, retrieval_mode="global_bm25"))
            if len(ctx.texte(None)) > self.budget:
                ctx.passages.pop()
        ctx.details = {"status": "text_evidence_only" if ctx.passages else "no_evidence",
                       "warnings": [], "open_world": True, "n_passages": len(ctx.passages),
                       "context_characters": len(ctx.texte(None)), "context_budget_characters": self.budget}
        ctx.duree = time.perf_counter() - t0
        return ctx
