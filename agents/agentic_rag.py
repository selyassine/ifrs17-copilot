"""Agent de recherche avec LangGraph : Agentic RAG + Corrective RAG (D-050).

Pourquoi un agent ici, et seulement ici : la recherche en un coup échoue sur les cas pratiques, parce
qu'il faut d'abord raisonner (« ratio sinistres/primes de 120 % » → « groupe déficitaire » → §57)
avant de chercher (F-013). La réécriture de la question (D-045) et l'adaptation du modèle d'embedding
(D-046) n'ont rien changé : il manque une étape de raisonnement et la possibilité de chercher à nouveau.

Le graphe (LangGraph, StateGraph) :

    START → planifier → chercher → évaluer ─┬─(suffisant ou budget épuisé)→ conclure → END
                            ▲               │
                            └──(nouvelle requête, au plus MAX_ROUNDS fois)┘

- planifier : le LLM identifie le mécanisme d'IFRS 17 en jeu (step-back) et écrit 2-3 requêtes ;
- chercher  : outil de recherche hybride + glossaire (et, si activés, graphe des renvois, index de
              questions, reranker) ; aucun LLM ;
- évaluer   : le LLM note chaque passage (pertinent / partiel / hors sujet) et dit ce qui manque
              (Corrective RAG) ;
- conclure  : les passages pertinents d'abord ; ils sont donnés à l'agent RAG habituel, dont les
              contrôles (citations vérifiées par le code, juge ancré) ne changent pas.

La boucle est bornée (MAX_ROUNDS) : coût et durée maximum connus, comportement auditable (D-036).
Un LLM indisponible ne bloque rien : sans plan, on cherche avec la question ; sans notes, on garde
l'ordre de la recherche.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TypedDict

from core.llm import LLMClient, LLMError
from core.prompts import load_prompt
from rag.retrieve import Hit, Retriever

MAX_ROUNDS = 1          # recherches supplémentaires autorisées après la première
POOL = 10               # passages au plus soumis à l'évaluation
GRADE_CHARS = 500       # longueur d'un extrait montré à l'évaluateur
GRADES = ("pertinent", "partiel", "hors_sujet")


class AgentState(TypedDict, total=False):
    question: str
    situation: str
    mecanismes: list[str]
    pending: list[str]            # requêtes à lancer au prochain passage dans « chercher »
    queries: list[str]            # requêtes déjà lancées
    scores: dict[str, float]      # chunk_id → meilleur 1 / rang obtenu
    grades: dict[str, str]        # chunk_id → pertinence
    sufficient: bool
    missing: str
    next_query: str | None
    round: int
    final: list[str]              # chunk_ids retenus, dans l'ordre
    steps: list[dict]             # journal lisible (interface, rapport)
    llm_calls: int


@dataclass
class AgenticResult:
    hits: list[Hit]
    queries: list[str]
    steps: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    latency_ms: float = 0.0


class AgenticSearch:
    """Les nœuds du graphe. Chaque nœud reçoit l'état et renvoie les clés qu'il modifie."""

    def __init__(self, retriever: Retriever, client: LLMClient, mode: str = "hybrid",
                 k: int = 5, case_id: str = ""):
        self.r, self.client, self.mode, self.k, self.case_id = retriever, client, mode, k, case_id
        self.by_id = {c.chunk_id: c for c in retriever.chunks}

    # ------------------------------------------------------------------ nœuds
    def plan(self, state: AgentState) -> dict:
        spec = load_prompt("agentic_plan")
        q = state["question"]
        calls = state.get("llm_calls", 0) + 1
        try:
            data = self._json(spec, spec.render(question=q), "planifier")
        except LLMError as exc:
            return {"pending": [q], "llm_calls": calls,
                    "steps": [*state.get("steps", []), {"noeud": "planifier", "erreur": str(exc)[:200]}]}
        reqs = [r.strip()[:300] for r in (data.get("requetes") or []) if isinstance(r, str) and r.strip()][:3]
        mec = [m for m in (data.get("mecanismes") or []) if isinstance(m, str)][:4]
        return {"situation": str(data.get("situation") or "")[:300], "mecanismes": mec,
                "pending": [q, *reqs], "llm_calls": calls,
                "steps": [*state.get("steps", []), {"noeud": "planifier", "mecanismes": mec, "requetes": reqs}]}

    def search(self, state: AgentState) -> dict:
        scores = dict(state.get("scores", {}))
        done = list(state.get("queries", []))
        for q in state.get("pending", []):
            for h in self.r.search(q, k=self.k, mode=self.mode, expand=True):
                cid = h.chunk.chunk_id
                scores[cid] = max(scores.get(cid, 0.0), 1.0 / h.rank)
            done.append(q)
        return {"scores": scores, "queries": done, "pending": [],
                "steps": [*state.get("steps", []), {"noeud": "chercher", "requetes": state.get("pending", []),
                                                    "passages": len(scores)}]}

    def grade(self, state: AgentState) -> dict:
        pool = self._pool(state)
        spec = load_prompt("grade_passages")
        extracts = "\n\n".join(
            f"[E{i}] §{', '.join(self.by_id[c].paragraph_ids[:4])} — {self.by_id[c].heading}\n"
            f"{self.by_id[c].text[:GRADE_CHARS]}" for i, c in enumerate(pool, start=1))
        calls = state.get("llm_calls", 0) + 1
        try:
            data = self._json(spec, spec.render(question=state["question"], extraits=extracts), "evaluer")
        except LLMError as exc:
            return {"sufficient": True, "llm_calls": calls,
                    "steps": [*state.get("steps", []), {"noeud": "evaluer", "erreur": str(exc)[:200]}]}
        grades = dict(state.get("grades", {}))
        for n in data.get("notes") or []:
            if not isinstance(n, dict):
                continue
            eid, grade = str(n.get("extrait", "")), str(n.get("pertinence", ""))
            if eid.startswith("E") and eid[1:].isdigit() and 1 <= int(eid[1:]) <= len(pool) and grade in GRADES:
                grades[pool[int(eid[1:]) - 1]] = grade
        nq = data.get("nouvelle_requete")
        nq = nq.strip()[:300] if isinstance(nq, str) and nq.strip() else None
        has_relevant = any(grades.get(c) == "pertinent" for c in pool)
        return {"grades": grades, "sufficient": bool(data.get("suffisant")) and has_relevant,
                "missing": str(data.get("manque") or "")[:300], "next_query": nq, "llm_calls": calls,
                "steps": [*state.get("steps", []), {
                    "noeud": "evaluer", "pertinents": sum(g == "pertinent" for g in grades.values()),
                    "suffisant": bool(data.get("suffisant")), "nouvelle_requete": nq}]}

    def route(self, state: AgentState) -> str:
        """Arête conditionnelle : nouvelle recherche ou conclusion (boucle bornée)."""
        if state.get("sufficient") or not state.get("next_query") or state.get("round", 0) >= MAX_ROUNDS:
            return "conclure"
        return "rechercher"

    def requery(self, state: AgentState) -> dict:
        q = state["next_query"]
        already = {x.lower() for x in state.get("queries", [])}
        return {"pending": [] if q.lower() in already else [q], "round": state.get("round", 0) + 1,
                "next_query": None}

    def finish(self, state: AgentState) -> dict:
        grades = state.get("grades", {})
        order = sorted(state.get("scores", {}), key=lambda c: -state["scores"][c])
        rank = {"pertinent": 0, "partiel": 1, None: 2, "hors_sujet": 3}
        final = sorted(order, key=lambda c: rank.get(grades.get(c), 2))   # tri stable : garde l'ordre de recherche
        if grades and any(grades.get(c) in ("pertinent", "partiel") for c in final):
            final = [c for c in final if grades.get(c) != "hors_sujet"]
        return {"final": final[: self.k],
                "steps": [*state.get("steps", []), {"noeud": "conclure", "retenus": final[: self.k]}]}

    # ------------------------------------------------------------------ outils
    def _pool(self, state: AgentState) -> list[str]:
        sc = state.get("scores", {})
        return sorted(sc, key=lambda c: -sc[c])[:POOL]

    def _json(self, spec, user: str, node: str) -> dict:
        resp = self.client.chat([{"role": "system", "content": spec.system}, {"role": "user", "content": user}],
                                model=spec.params.model, temperature=spec.params.temperature,
                                max_tokens=spec.params.max_tokens, json_mode=True,
                                trace={"agent": "chercheur_rag", "prompt_id": spec.id, "prompt_version": spec.version,
                                       "case_id": self.case_id, "noeud": node})
        data = resp.json()
        if not isinstance(data, dict):
            raise LLMError("la réponse JSON n'est pas un objet")
        return data

    def hits(self, state: AgentState) -> list[Hit]:
        return [Hit(rank=i, score=state["scores"].get(c, 0.0), chunk=self.by_id[c])
                for i, c in enumerate(state.get("final", []), start=1)]


def build_graph(agent: AgenticSearch):
    """Assemble le graphe LangGraph (import local : LangGraph n'est requis que pour ce mode)."""
    from langgraph.graph import END, START, StateGraph

    g = StateGraph(AgentState)
    g.add_node("planifier", agent.plan)
    g.add_node("chercher", agent.search)
    g.add_node("evaluer", agent.grade)
    g.add_node("rechercher", agent.requery)
    g.add_node("conclure", agent.finish)
    g.add_edge(START, "planifier")
    g.add_edge("planifier", "chercher")
    g.add_edge("chercher", "evaluer")
    g.add_conditional_edges("evaluer", agent.route, {"rechercher": "rechercher", "conclure": "conclure"})
    g.add_edge("rechercher", "chercher")
    g.add_edge("conclure", END)
    return g.compile()


def agentic_search(question: str, retriever: Retriever, client: LLMClient | None = None,
                   mode: str = "hybrid", k: int = 5, case_id: str = "") -> AgenticResult:
    t0 = time.perf_counter()
    agent = AgenticSearch(retriever, client or LLMClient(), mode=mode, k=k, case_id=case_id)
    state: AgentState = build_graph(agent).invoke({"question": question, "round": 0, "steps": [], "llm_calls": 0},
                                        {"recursion_limit": 12})
    return AgenticResult(hits=agent.hits(state), queries=state.get("queries", []), steps=state.get("steps", []),
                         llm_calls=state.get("llm_calls", 0), latency_ms=round((time.perf_counter() - t0) * 1000, 1))
