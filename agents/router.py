"""Agent Routeur.

Deux implémentations, comparées sur le même jeu de test (eval/router_cases.jsonl) :
- ``route_heuristic`` : règles par mots-clés. Base de référence gratuite et déterministe.
- ``route_llm`` : prompt ``prompts/router/route.vN.yaml``. Repli sur l'heuristique si
  la sortie du LLM ne passe pas la validation Pydantic.

Le gain du LLM sur l'heuristique est une mesure à mettre dans le rapport.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import ValidationError

from agents.schemas import AgentName, Intent, Plan
from core.llm import LLMClient, LLMError
from core.prompts import load_prompt

STEPS_BY_INTENT: dict[Intent, list[AgentName]] = {
    Intent.NORM_QUESTION: [AgentName.RAG, AgentName.VERIFIER, AgentName.WRITER],
    Intent.DOCUMENT: [AgentName.EXTRACTOR, AgentName.CALCULATOR, AgentName.RAG,
                      AgentName.VERIFIER, AgentName.WRITER],
    Intent.CALCULATION: [AgentName.CALCULATOR, AgentName.VERIFIER, AgentName.WRITER],
    Intent.OUT_OF_SCOPE: [],
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


_DOMAIN = re.compile(
    r"ifrs|csm|marge sur services|contractual service|contrat[s]? d.assurance|insurance contract"
    r"|unites? de couverture|coverage unit|ajustement pour risque|risk adjustment|onereu"
    r"|composante perte|loss component|vfa|paa|bba|modele general|actualisation|discount"
    r"|flux de tresorerie|cash flow|reassurance|reinsurance|roll.?forward|liberation"
    r"|\bias\b|\bb\d{2,3}\b|paragraphe|§"
)
_CALC = re.compile(r"calcul|compute|combien|montant|chiffre|simul|projet(te|er)|roll.?forward")
_DOC = re.compile(r"pdf|document|fichier|piece jointe|ci.joint|scan|image|tableau|etat financier")


def route_heuristic(request: str, has_attachment: bool = False) -> Plan:
    t = _norm(request)
    in_domain = bool(_DOMAIN.search(t))
    wants_calc = bool(_CALC.search(t))
    mentions_doc = bool(_DOC.search(t))

    if has_attachment:
        intent, conf = Intent.DOCUMENT, 0.85
        why = "un fichier est joint"
    elif not in_domain:
        intent, conf = Intent.OUT_OF_SCOPE, 0.6
        why = "aucun terme IFRS 17 détecté"
    elif wants_calc and not mentions_doc:
        intent, conf = Intent.CALCULATION, 0.6
        why = "demande de calcul sans document"
    elif mentions_doc:
        intent, conf = Intent.DOCUMENT, 0.5
        why = "un document est mentionné mais non joint"
    else:
        intent, conf = Intent.NORM_QUESTION, 0.7
        why = "question sur la norme"
    return Plan(intent=intent, steps=STEPS_BY_INTENT[intent], confidence=conf, rationale=why)


def route_llm(
    request: str,
    has_attachment: bool = False,
    client: LLMClient | None = None,
    version: int | None = None,
    case_id: str = "",
) -> Plan:
    spec = load_prompt("route", version)
    client = client or LLMClient()
    user = spec.render(request=request, has_attachment="oui" if has_attachment else "non")
    try:
        resp = client.chat(
            [{"role": "system", "content": spec.system}, {"role": "user", "content": user}],
            model=spec.params.model,
            temperature=spec.params.temperature,
            max_tokens=spec.params.max_tokens,
            json_mode=True,
            trace={"agent": "routeur", "prompt_id": spec.id, "prompt_version": spec.version,
                   "case_id": case_id},
        )
        data = resp.json()
        intent = Intent(data["intent"])
        # Les étapes viennent du code, pas du LLM : il ne choisit que l'intention.
        return Plan(
            intent=intent,
            steps=STEPS_BY_INTENT[intent],
            confidence=float(data.get("confidence", 0.5)),
            rationale=str(data.get("rationale", ""))[:300],
        )
    except (LLMError, ValidationError, KeyError, ValueError, TypeError) as exc:
        plan = route_heuristic(request, has_attachment)
        return plan.model_copy(update={"rationale": f"repli heuristique ({type(exc).__name__})"})
