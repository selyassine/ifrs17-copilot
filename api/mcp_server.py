"""Serveur MCP (Model Context Protocol) d'IFRS 17 Copilot (D-062).

    python -m api.mcp_server            # transport stdio : lancé par le client MCP

Un client MCP (Claude Desktop, un IDE, un autre agent) branche ce serveur et obtient, sans écrire de
code, ce que le Copilot sait faire sur les dossiers :

- **outils** (lecture seule) : lister et lire les dossiers du registre, recalculer un scénario, les
  sensibilités, le niveau de confiance de l'ajustement pour risque, la projection du résultat,
  calculer la marge d'un portefeuille quelconque, chercher dans le règlement (sans modèle de
  langage), vérifier l'intégrité de la piste d'audit ;
- **ressources** : la note de chaque dossier (Markdown) et chaque paragraphe du règlement ;
- **prompts** : « analyser un dossier » et « répondre sur la norme avec citations ».

Aucun outil n'écrit : pas de validation, pas d'e-mail, pas de modification du registre. Le calcul
reste au moteur (D-005) ; l'agent client choisit seulement quoi demander.

Implémentation sans dépendance : JSON-RPC 2.0, un message JSON par ligne sur l'entrée et la sortie
standard (transport stdio de la spécification), poignée de main ``initialize`` des révisions
2024-11-05 à 2025-11-25. Vérifiée avec le client officiel du SDK Python MCP (tests/test_mcp_server.py
pour le protocole, et un essai de bout en bout avec ``mcp.client.stdio``). Rien n'est écrit sur la
sortie standard en dehors du protocole : les journaux vont sur l'erreur standard.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agents.copilot import DossierTools, LevelArgs, NoArgs, ScenarioArgs
from agents.schemas import PortfolioData
from core.config import ROOT, Settings, get_settings
from core.registry import Registry, get_registry
from core.version import VERSION
from engine.csm import compute_csm

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")   # du plus récent au plus ancien
SERVER_INFO = {"name": "ifrs17-copilot", "title": "IFRS 17 Copilot", "version": VERSION}
INSTRUCTIONS = ("Outils en lecture seule sur les dossiers IFRS 17 d'une équipe actuarielle. Tous les montants viennent "
                "du moteur de calcul : recopiez-les tels quels. Pour une règle, utilisez chercher_dans_la_norme et "
                "citez le paragraphe renvoyé. Données de démonstration fictives.")


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- #
# Arguments des outils (schémas JSON exposés au client)
# --------------------------------------------------------------------------- #
class _A(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListArgs(_A):
    statut: str = Field("", description="note_prete, validation_humaine, validee, rejetee, document_illisible, erreur ; vide = tous")
    recherche: str = Field("", max_length=100, description="référence, groupe de contrats, déposant ou fichier")
    limite: int = Field(20, ge=1, le=100)


class CaseArgs(_A):
    dossier: str = Field(..., min_length=1, max_length=80, description="référence du dossier, ex. D-2026-1040")


class CaseScenarioArgs(CaseArgs, ScenarioArgs):
    pass


class CaseLevelArgs(CaseArgs, LevelArgs):
    pass


class PortfolioArgs(_A):
    portefeuille: PortfolioData = Field(..., description="données d'un groupe de contrats (modèle général)")


class NormSearchArgs(_A):
    question: str = Field(..., min_length=3, max_length=300, description="question ou mots-clés, en français")
    k: int = Field(5, ge=1, le=10, description="nombre de passages")


@dataclass
class McpTool:
    name: str
    title: str
    description: str
    args: type[BaseModel]
    run: Callable[..., Any]


def _schema(model: type[BaseModel]) -> dict:
    s = model.model_json_schema()
    s.pop("title", None)
    s.setdefault("properties", {})
    s["additionalProperties"] = False
    return s


# --------------------------------------------------------------------------- #
# Le serveur
# --------------------------------------------------------------------------- #
class IFRS17McpServer:
    def __init__(self, settings: Settings | None = None, registry: Registry | None = None):
        self.settings = settings or get_settings()
        self._registry = registry
        self.protocol: str | None = None
        self.tools = {t.name: t for t in self._tools()}

    @property
    def registry(self) -> Registry:
        if self._registry is None:
            self._registry = get_registry(self.settings.registry_path)
        return self._registry

    # -------------------------------------------------------------- outils
    def _tools(self) -> list[McpTool]:
        return [
            McpTool("lister_dossiers", "Lister les dossiers", "Dossiers du registre, du plus récent au plus ancien : référence, "
                    "groupe de contrats, statut, CSM ou perte à l'origine, canal, déposant.", ListArgs, self.list_cases),
            McpTool("lire_dossier", "Lire un dossier", "Un dossier complet : statut, données du portefeuille, résultats "
                    "centraux, contrôles non passés, décision du valideur.", CaseArgs, self.read_case),
            McpTool("evaluer_scenario", "Évaluer un scénario", "Recalcule le groupe d'un dossier avec des hypothèses modifiées "
                    "(sinistres et frais, primes, taux en points de base, ajustement pour risque) et compare au scénario central.",
                    CaseScenarioArgs, lambda dossier, **kw: self._dossier_tools(dossier).scenario(**kw)),
            McpTool("sensibilites", "Sensibilités", "Les 6 chocs standard d'un dossier et les seuils de bascule (variation des "
                    "sinistres ou des taux qui annule la marge).", CaseArgs, lambda dossier: self._dossier_tools(dossier).sensitivities()),
            McpTool("niveau_de_confiance", "Niveau de confiance", "Ajustement pour risque exigé à un niveau de confiance donné, "
                    "son effet sur la CSM, et le niveau de confiance de l'ajustement retenu (§119).", CaseLevelArgs,
                    lambda dossier, niveau: self._dossier_tools(dossier).confidence(niveau)),
            McpTool("projection_resultat", "Projection du résultat", "Compte de résultat IFRS 17 attendu par période "
                    "(produits, résultat des services, charges financières) d'un dossier.", CaseArgs,
                    lambda dossier: self._dossier_tools(dossier).projection()),
            McpTool("calculer_csm", "Calculer la marge", "Calcule la marge sur services contractuels (ou la composante de perte) "
                    "et son écoulement pour un portefeuille fourni, sans l'enregistrer.", PortfolioArgs, self.compute),
            McpTool("chercher_dans_la_norme", "Chercher dans la norme", "Passages du règlement (UE) 2021/2036 (IFRS 17) les "
                    "plus pertinents pour une question, avec leurs numéros de paragraphe. Recherche seule, sans modèle de langage.",
                    NormSearchArgs, self.norm_search),
            McpTool("verifier_piste_audit", "Vérifier la piste d'audit", "Recalcule la chaîne d'empreintes SHA-256 du registre : "
                    "intacte, ou premier événement modifié.", NoArgs, lambda: self.registry.verify_chain()),
        ]

    def _case(self, dossier: str) -> dict:
        case = self.registry.get_case(dossier)
        if case is None:
            raise ValueError(f"dossier inconnu : {dossier}")
        return case

    def _dossier_tools(self, dossier: str) -> DossierTools:
        case = self._case(dossier)
        if not case.get("portfolio"):
            raise ValueError(f"le dossier {dossier} n'a pas de données exploitables ({case['status']})")
        return DossierTools(PortfolioData(**case["portfolio"]), ra_cv=self.settings.ra_cv)

    def list_cases(self, statut: str = "", recherche: str = "", limite: int = 20) -> dict:
        rows, total = self.registry.list_cases(status=statut, q=recherche, limit=limite)
        return {"total": total, "dossiers": [
            {"dossier": c["case_id"], "groupe": c["group_id"], "statut": c["status"], "deficitaire": c["onerous"],
             "csm_initiale": c["csm"], "perte_initiale": c["loss"], "monnaie": c["currency"], "unite": c["unit"],
             "canal": c["source"], "deposant": c["submitter"], "mis_a_jour": c["updated_at"]} for c in rows]}

    def read_case(self, dossier: str) -> dict:
        c = self._case(dossier)
        out = {"dossier": c["case_id"], "statut": c["status"], "groupe": c["group_id"], "canal": c["source"],
               "deposant": c["submitter"], "document": c["filename"], "empreinte_document": c["sha256"],
               "depose_le": c["created_at"], "controles_non_passes": c["controls"],
               "decision": {"par": c["validated_by"], "le": c["validated_at"], "commentaire": c["decision_comment"]}
               if c["validated_by"] else None, "note_disponible": c["has_note"],
               "note": f"ifrs17://dossiers/{c['case_id']}/note" if c["has_note"] else None}
        if c.get("portfolio"):
            out["portefeuille"] = c["portfolio"]
            out["resultats_centraux"] = DossierTools(PortfolioData(**c["portfolio"]), ra_cv=self.settings.ra_cv).dossier()
        return out

    def compute(self, portefeuille: PortfolioData) -> dict:
        r = compute_csm(portefeuille)
        return r.model_dump(mode="json")

    def norm_search(self, question: str, k: int = 5) -> dict:
        from rag.service import IndexMissing, get_retriever, retrieval_options

        s = self.settings
        mode = s.rag_mode if s.rag_embed_model or s.rag_mode == "bm25" else "bm25"
        model = s.rag_embed_model if mode in ("dense", "hybrid") else ""
        try:
            retriever = get_retriever(s.rag_strategy, model, **retrieval_options(s))
        except IndexMissing as exc:
            raise ValueError(str(exc)) from exc
        hits = retriever.search(question, k=k, mode=mode, expand=s.rag_glossary)
        return {"mode": mode, "passages": [{"rang": h.rank, "paragraphes": h.chunk.paragraph_ids, "titre": h.chunk.heading,
                                            "texte": h.chunk.text, "ressource": f"ifrs17://norme/paragraphes/{h.chunk.paragraph_ids[0]}"
                                            if h.chunk.paragraph_ids else None} for h in hits]}

    # -------------------------------------------------------------- ressources
    def resources(self) -> list[dict]:
        rows, _ = self.registry.list_cases(limit=100)
        return [{"uri": f"ifrs17://dossiers/{c['case_id']}/note", "name": f"note-{c['case_id']}",
                 "title": f"Note IFRS 17 · {c['group_id'] or c['case_id']}", "mimeType": "text/markdown",
                 "description": f"Note actuarielle du dossier {c['case_id']} ({c['status']})"} for c in rows if c["has_note"]]

    @staticmethod
    def resource_templates() -> list[dict]:
        return [{"uriTemplate": "ifrs17://norme/paragraphes/{paragraphe}", "name": "paragraphe-ifrs17",
                 "title": "Paragraphe du règlement IFRS 17", "mimeType": "text/plain",
                 "description": "Texte d'un paragraphe : 44, B119, C5, art-2…"},
                {"uriTemplate": "ifrs17://dossiers/{dossier}/note", "name": "note-dossier", "title": "Note d'un dossier",
                 "mimeType": "text/markdown", "description": "Note actuarielle IFRS 17 d'un dossier du registre"}]

    def read_resource(self, uri: str) -> dict:
        if uri.startswith("ifrs17://dossiers/") and uri.endswith("/note"):
            cid = uri[len("ifrs17://dossiers/"):-len("/note")]
            case = self.registry.get_case(cid, with_note=True)
            if not case or not case.get("note_markdown"):
                raise RpcError(-32002, f"ressource introuvable : {uri}")
            return {"uri": uri, "mimeType": "text/markdown", "text": case["note_markdown"]}
        if uri.startswith("ifrs17://norme/paragraphes/"):
            pid = uri.rsplit("/", 1)[1]
            unit = paragraphs().get(pid)
            if unit is None:
                raise RpcError(-32002, f"paragraphe inconnu : {pid}")
            return {"uri": uri, "mimeType": "text/plain", "text": f"{unit.get('heading', '')}\n\n{unit['text']}".strip()}
        raise RpcError(-32002, f"ressource introuvable : {uri}")

    # -------------------------------------------------------------- prompts
    PROMPTS = {
        "analyser_un_dossier": {
            "title": "Analyser un dossier IFRS 17",
            "description": "Revue d'un dossier : résultats, contrôles, sensibilités, avec citations de la norme.",
            "arguments": [{"name": "dossier", "description": "référence du dossier", "required": True}]},
        "question_sur_la_norme": {
            "title": "Répondre sur IFRS 17 avec citations",
            "description": "Répondre à une question sur la norme en citant les paragraphes trouvés.",
            "arguments": [{"name": "question", "description": "la question", "required": True}]},
    }

    def get_prompt(self, name: str, arguments: dict) -> dict:
        if name == "analyser_un_dossier":
            d = str(arguments.get("dossier") or "").strip()
            if not d:
                raise RpcError(-32602, "argument requis : dossier")
            text = (f"Fais la revue du dossier IFRS 17 {d}. Lis-le avec lire_dossier, puis appelle sensibilites. "
                    "Rédige une synthèse de 5 à 8 phrases : statut, CSM ou perte à l'origine, contrôles non passés, "
                    "hypothèse la plus sensible et seuil de bascule. Recopie les montants tels que les outils les donnent, "
                    "avec leur unité ; pour chaque règle invoquée, appelle chercher_dans_la_norme et cite le paragraphe.")
        elif name == "question_sur_la_norme":
            q = str(arguments.get("question") or "").strip()
            if not q:
                raise RpcError(-32602, "argument requis : question")
            text = (f"Question sur IFRS 17 : {q}\nAppelle chercher_dans_la_norme, puis réponds uniquement à partir des "
                    "passages renvoyés, en citant chaque paragraphe entre crochets, ex. [§44]. Si aucun passage ne répond, "
                    "dis-le plutôt que d'inventer.")
        else:
            raise RpcError(-32602, f"prompt inconnu : {name}")
        return {"description": self.PROMPTS[name]["description"],
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}]}

    # -------------------------------------------------------------- JSON-RPC
    def call_tool(self, name: str, arguments: dict) -> dict:
        tool = self.tools.get(name)
        if tool is None:
            raise RpcError(-32602, f"outil inconnu : {name}")
        try:
            args = tool.args.model_validate(arguments or {})
            result = tool.run(**{k: getattr(args, k) for k in type(args).model_fields})
        except ValidationError as exc:
            msg = "arguments invalides : " + "; ".join(f"{'.'.join(map(str, e['loc']))} {e['msg']}" for e in exc.errors())
            return {"content": [{"type": "text", "text": msg[:800]}], "isError": True}
        except ValueError as exc:
            return {"content": [{"type": "text", "text": str(exc)[:800]}], "isError": True}
        if isinstance(result, dict) and "erreur" in result:
            return {"content": [{"type": "text", "text": str(result["erreur"])}], "isError": True}
        out = {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]}
        if isinstance(result, dict) and self.protocol and self.protocol >= "2025-06-18":
            out["structuredContent"] = json.loads(json.dumps(result, default=str))
        return out

    def handle(self, msg: dict) -> dict | None:
        """Traite un message JSON-RPC ; renvoie la réponse, ou None pour une notification."""
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method is None:          # réponse du client à une requête du serveur : rien à faire
            return None
        try:
            result = self._dispatch(method, params)
        except RpcError as exc:
            return None if mid is None else {"jsonrpc": "2.0", "id": mid, "error": {"code": exc.code, "message": str(exc)}}
        except Exception as exc:  # noqa: BLE001 — un outil ne doit jamais faire tomber le serveur
            print(f"[mcp] erreur interne sur {method} : {exc!r}", file=sys.stderr)
            return None if mid is None else {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": "erreur interne"}}
        return None if mid is None else {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, params: dict) -> Any:
        if method == "initialize":
            asked = str(params.get("protocolVersion") or "")
            self.protocol = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
            return {"protocolVersion": self.protocol, "serverInfo": SERVER_INFO, "instructions": INSTRUCTIONS,
                    "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False},
                                     "prompts": {"listChanged": False}, "logging": {}}}
        if method.startswith("notifications/"):
            return None
        if method == "ping":
            return {}
        if method == "logging/setLevel":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": t.name, "title": t.title, "description": t.description, "inputSchema": _schema(t.args),
                               "annotations": {"title": t.title, "readOnlyHint": True, "destructiveHint": False,
                                               "idempotentHint": True, "openWorldHint": False}} for t in self.tools.values()]}
        if method == "tools/call":
            return self.call_tool(str(params.get("name", "")), params.get("arguments") or {})
        if method == "resources/list":
            return {"resources": self.resources()}
        if method == "resources/templates/list":
            return {"resourceTemplates": self.resource_templates()}
        if method == "resources/read":
            return {"contents": [self.read_resource(str(params.get("uri", "")))]}
        if method == "prompts/list":
            return {"prompts": [{"name": k, **v} for k, v in self.PROMPTS.items()]}
        if method == "prompts/get":
            return self.get_prompt(str(params.get("name", "")), params.get("arguments") or {})
        raise RpcError(-32601, f"méthode inconnue : {method}")

    def serve(self, stdin=None, stdout=None) -> None:
        stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON invalide"}}
            else:
                batch = msg if isinstance(msg, list) else [msg]
                replies = [r for r in (self.handle(m) for m in batch if isinstance(m, dict)) if r is not None]
                reply = (replies if isinstance(msg, list) else replies[0]) if replies else None
            if reply is not None:
                stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
                stdout.flush()


@lru_cache
def paragraphs() -> dict[str, dict]:
    path = ROOT / "data" / "processed" / "C002_units.jsonl"
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            u = json.loads(line)
            out[str(u.get("paragraph_id"))] = u
    return out


def main() -> None:
    # sortie standard réservée au protocole : UTF-8 sans tampon de lignes perdues sous Windows
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    print(f"[mcp] IFRS 17 Copilot {VERSION} prêt (stdio)", file=sys.stderr)
    IFRS17McpServer().serve()


if __name__ == "__main__":
    main()
