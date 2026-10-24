"""Serveur MCP (D-062) : poignée de main, outils en lecture seule, ressources, prompts, erreurs."""

import io
import json

from agents.schemas import PortfolioData
from api.mcp_server import IFRS17McpServer
from core.config import get_settings
from core.registry import Registry
from engine.csm import compute_csm

P = PortfolioData(group_id="G-MCP", premiums=[100, 0, 0], outflows=[30, 30, 30], coverage_units=[1, 1, 1],
                  discount_rates=0.02, risk_adjustment_pct=0.05)


def server(tmp_path):
    reg = Registry(tmp_path / "reg.db")
    reg.open_case("D-1", "site", "karim", submitter="Karim", filename="g.pdf")
    reg.record_outcome("D-1", "systeme", "note_prete", portfolio=P.model_dump(mode="json"),
                       csm=compute_csm(P).model_dump(mode="json"), note_html="<p>n</p>", note_markdown="# Note G-MCP")
    return IFRS17McpServer(get_settings(), reg)


def rpc(srv, method, params=None, mid=1):
    return srv.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def test_poignee_de_main_et_capacites(tmp_path):
    srv = server(tmp_path)
    r = rpc(srv, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}})
    assert r["result"]["protocolVersion"] == "2025-06-18"
    assert set(r["result"]["capabilities"]) >= {"tools", "resources", "prompts"}
    assert rpc(srv, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == "2025-11-25"
    assert srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert rpc(srv, "ping")["result"] == {}
    assert rpc(srv, "inexistante")["error"]["code"] == -32601


def test_outils_en_lecture_seule_et_resultats_du_moteur(tmp_path):
    srv = server(tmp_path)
    rpc(srv, "initialize", {"protocolVersion": "2025-11-25"})
    tools = rpc(srv, "tools/list")["result"]["tools"]
    assert all(t["annotations"]["readOnlyHint"] and not t["annotations"]["destructiveHint"] for t in tools)
    scen = next(t for t in tools if t["name"] == "evaluer_scenario")
    assert {"dossier", "sorties_pct"} <= set(scen["inputSchema"]["properties"]) and "dossier" in scen["inputSchema"]["required"]
    r = rpc(srv, "tools/call", {"name": "lire_dossier", "arguments": {"dossier": "D-1"}})["result"]
    data = json.loads(r["content"][0]["text"])
    assert data["groupe"] == "G-MCP" and data["resultats_centraux"]["csm_initiale"] and r["structuredContent"]["dossier"] == "D-1"
    r = rpc(srv, "tools/call", {"name": "lister_dossiers", "arguments": {}})["result"]
    assert json.loads(r["content"][0]["text"])["total"] == 1


def test_erreurs_d_outil_renvoyees_au_client(tmp_path):
    srv = server(tmp_path)
    r = rpc(srv, "tools/call", {"name": "lire_dossier", "arguments": {"dossier": "X"}})["result"]
    assert r["isError"] and "inconnu" in r["content"][0]["text"]
    r = rpc(srv, "tools/call", {"name": "evaluer_scenario", "arguments": {"dossier": "D-1", "sorties_pct": 5000}})["result"]
    assert r["isError"] and "invalides" in r["content"][0]["text"]
    assert rpc(srv, "tools/call", {"name": "effacer", "arguments": {}})["error"]["code"] == -32602


def test_ressources_prompts_et_transport_stdio(tmp_path):
    srv = server(tmp_path)
    res = rpc(srv, "resources/list")["result"]["resources"]
    assert res[0]["uri"] == "ifrs17://dossiers/D-1/note"
    assert rpc(srv, "resources/read", {"uri": res[0]["uri"]})["result"]["contents"][0]["text"] == "# Note G-MCP"
    assert rpc(srv, "resources/read", {"uri": "ifrs17://dossiers/X/note"})["error"]["code"] == -32002
    assert {p["name"] for p in rpc(srv, "prompts/list")["result"]["prompts"]} == {"analyser_un_dossier", "question_sur_la_norme"}
    assert "D-1" in rpc(srv, "prompts/get", {"name": "analyser_un_dossier", "arguments": {"dossier": "D-1"}})[
        "result"]["messages"][0]["content"]["text"]
    out = io.StringIO()
    srv.serve(io.StringIO('{"jsonrpc":"2.0","id":7,"method":"ping"}\n{"jsonrpc":"2.0","method":"notifications/initialized"}\nnot json\n'), out)
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert lines[0] == {"jsonrpc": "2.0", "id": 7, "result": {}} and lines[1]["error"]["code"] == -32700 and len(lines) == 2
