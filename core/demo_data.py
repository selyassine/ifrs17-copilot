"""Registre de démonstration pour la soutenance et la vidéo (D-060).

    python -m core.demo_data data/demo.db
    puis, dans .env : REGISTRY_PATH=data/demo.db  (relancer l'API)

Dix-neuf dossiers des jeux synthétiques du projet (données fictives), calculés par le vrai moteur ;
notes produites par le rédacteur avec une synthèse fixe (aucun appel à un modèle) ; dates étalées sur
30 jours ; trois comptes : admin / admin-demo-1, claire / valideur-demo, karim / analyste-demo.
Refuse d'écraser un registre existant : ne jamais l'utiliser sur le registre de production."""
import json
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import core.registry as R
from agents.orchestrator import run_case
from agents.schemas import PortfolioData
from core.config import Settings
from core.llm import LLMClient

ROOT = Path(__file__).resolve().parent.parent
if len(sys.argv) != 2:
    raise SystemExit("usage : python -m core.demo_data data/demo.db")
OUT = Path(sys.argv[1])
if OUT.exists():
    raise SystemExit(f"{OUT} existe déjà : choisissez un autre fichier (ce script ne remplace jamais un registre).")
OUT.parent.mkdir(parents=True, exist_ok=True)
random.seed(17)
clock = {"t": datetime.now(UTC) - timedelta(days=29, hours=5)}
R.now = lambda: clock["t"].isoformat(timespec="seconds")


def advance(**kw):
    clock["t"] += timedelta(**kw)


def respond(messages, model):
    system = messages[0]["content"]
    if "note actuarielle IFRS 17" in system:
        return json.dumps({"synthese": "Le groupe est évalué selon le modèle général ; la marge est libérée en résultat au rythme des unités de couverture.",
                           "commentaire_sensibilites": ""}, ensure_ascii=False)
    return json.dumps({"answer": "", "citations": [], "refused": True, "refusal_reason": "démo"})


s = Settings(llm_provider="fake", llm_max_retries=0, trace_path=OUT.parent / "demo_trace.jsonl", rag_mode="bm25",
             norm_reference_path=OUT.parent / "demo_noref.json", registry_path=OUT)
client = LLMClient(s, fake_responder=respond)
reg = R.Registry(OUT)
reg.add_user("admin", "admin-demo-1", "admin", "Inès Gharbi")
reg.add_user("claire", "valideur-demo", "valideur", "Claire Martin")
reg.add_user("karim", "analyste-demo", "analyste", "Karim Haddad")

cases = [json.loads(line) for line in (ROOT / "eval/extraction_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
hard = [json.loads(line) for line in (ROOT / "eval/extraction_hard_cases.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
SUB = {"site": ["Karim Haddad", "Claire Martin"], "n8n-email": ["actuariat@assureur-fictif.fr", "s.benali@assureur-fictif.fr", "reporting@mutuelle-demo.fr"],
       "n8n-formulaire": ["l.moreau@assureur-fictif.fr", "finance@mutuelle-demo.fr"], "api": ["batch-cloture-T3"]}
plan = (["note_prete"] * 9 + ["validee"] * 4 + ["validation_humaine"] * 3 + ["rejetee", "document_illisible", "erreur"])
random.shuffle(plan)
srcs = ["site", "n8n-email", "site", "n8n-formulaire", "n8n-email", "site", "api", "n8n-email", "site", "n8n-formulaire"]
pool = cases + [h for h in hard if h.get("truth")]
CONTROLS = ["extraction : taux de la période 4 introuvable dans le document",
            "extraction : deux groupes de contrats dans le document, groupe retenu à confirmer",
            "extraction : unité des montants ambiguë (milliers ou unités)"]

for i, status in enumerate(plan):
    c = pool[i % len(pool)]
    truth = dict(c["truth"])
    cid = f"D-2026-{1040 + i:04d}"
    src = srcs[i % len(srcs)]
    sub = random.choice(SUB[src])
    advance(hours=random.randint(18, 40), minutes=random.randint(0, 59))
    if clock["t"] > datetime.now(UTC) - timedelta(hours=2):
        clock["t"] = datetime.now(UTC) - timedelta(hours=random.randint(3, 6))
    fname = Path(c.get("pdf") or f"{c['id']}.pdf").name
    reg.open_case(cid, src, "systeme" if src.startswith("n8n") or src == "api" else "karim", submitter=sub, filename=fname,
                  sha256=R._sha(cid + fname) if hasattr(R, "_sha") else "")
    usage = {"llm_calls": random.choice([5, 6, 6, 7, 8]), "tokens": random.randint(8200, 14600), "cost_usd": 0.0}
    advance(seconds=random.randint(55, 120))
    if status in ("document_illisible", "erreur"):
        reg.record_outcome(cid, "systeme", status, action="echec",
                           controls=["document illisible : aucune donnée de portefeuille reconnue sur la page" if status == "document_illisible"
                                     else "LLM indisponible : quota du fournisseur dépassé (429)"], duration_ms=random.randint(8000, 30000), usage=usage)
        continue
    p = PortfolioData(**truth)
    out = run_case(b"", "", s, lambda: client, lambda: client, None, cid, portfolio=p, source_name=fname)
    first = "validation_humaine" if status in ("validee", "validation_humaine", "rejetee") else "note_prete"
    ctrl = [random.choice(CONTROLS)] if first == "validation_humaine" else []
    reg.record_outcome(cid, "systeme", first, portfolio=p.model_dump(mode="json"), csm=out.csm.model_dump(mode="json"),
                       controls=ctrl, note_html=out.note.html, note_markdown=out.note.markdown,
                       duration_ms=random.randint(52000, 118000), usage=usage)
    if first == "validation_humaine":
        reg.add_event(cid, "systeme", "email_validation", {"envoyee": True, "detail": "e-mail de validation envoyé par n8n"})
    elif src.startswith("n8n"):
        reg.add_event(cid, "systeme", "email_note_envoyee", {"a": sub, "canal": src})
    if status == "validee":
        advance(hours=random.randint(2, 20))
        reg.add_event(cid, "claire", "validation_approuvee", {"valideur": "claire", "commentaire": "Taux vérifié dans l'annexe du document."})
        reg.record_outcome(cid, "claire", "validee", action="analyse_apres_validation", portfolio=p.model_dump(mode="json"),
                           csm=out.csm.model_dump(mode="json"), controls=[], note_html=out.note.html, note_markdown=out.note.markdown,
                           duration_ms=random.randint(40000, 70000), usage=usage, validated_by="claire", comment="Taux vérifié dans l'annexe du document.")
    if status == "rejetee":
        advance(hours=random.randint(3, 12))
        reg.record_outcome(cid, "claire", "rejetee", action="validation_rejetee", validated_by="claire",
                           comment="Deux groupes de contrats mélangés dans le même état : à redéposer séparément.")
    if i % 3 == 0:
        advance(minutes=random.randint(10, 300))
        reg.add_event(cid, random.choice(["claire", "karim"]), "note_consultee", {})
print("dossiers :", reg.list_cases(limit=1)[1])
print(json.dumps(reg.verify_chain(), ensure_ascii=False))
