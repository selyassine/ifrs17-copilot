"""Bibliothèque de prompts : fiches YAML versionnées dans prompts/<agent>/<id>.vN.yaml.

Les gabarits utilisent la syntaxe ``$variable`` (string.Template) et non ``{variable}``,
pour que les exemples JSON des few-shot puissent contenir des accolades.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from string import Template

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.config import ROOT

PROMPTS_DIR = ROOT / "prompts"
_FILE_RE = re.compile(r"^(?P<id>[a-z0-9_]+)\.v(?P<version>\d+)\.yaml$")

TECHNIQUES = {
    "zero_shot", "few_shot", "chain_of_thought", "role_prompting", "structured_output",
    "guardrails", "self_consistency", "prompt_chaining", "generated_knowledge",
    "llm_as_judge", "tool_use", "delimiters", "query_rewriting",
}


class PromptParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(description="'small' ou 'large' (résolu via .env) ou un nom exact")
    temperature: float = Field(ge=0.0, le=1.5)
    max_tokens: int = Field(gt=0, le=8000)


class PromptEval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test_set: str
    metric: str
    scores: dict[str, float] = Field(default_factory=dict, description="{'v1': 0.62, ...}")
    notes: str = Field(default="", description="modèle, date, nombre de cas, replis")


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    version: int = Field(ge=1)
    agent: str
    role: str
    techniques: list[str]
    params: PromptParams
    system: str
    template: str
    output_schema: str | None = None
    failures_observed: list[str] = Field(default_factory=list)
    changes: str = ""
    eval: PromptEval | None = None

    def render(self, **variables: str) -> str:
        return Template(self.template).substitute(**variables)

    def variables(self) -> set[str]:
        return {m.group("named") or m.group("braced")
                for m in Template.pattern.finditer(self.template)
                if m.group("named") or m.group("braced")}


def load_prompt_file(path: Path) -> PromptSpec:
    m = _FILE_RE.match(path.name)
    if not m:
        raise ValueError(f"nom de fichier invalide : {path.name} (attendu <id>.vN.yaml)")
    spec = PromptSpec(**yaml.safe_load(path.read_text(encoding="utf-8")))
    if spec.id != m["id"] or spec.version != int(m["version"]):
        raise ValueError(f"{path.name} : id/version du fichier ≠ contenu ({spec.id} v{spec.version})")
    if spec.agent != path.parent.name:
        raise ValueError(f"{path.name} : agent '{spec.agent}' ≠ dossier '{path.parent.name}'")
    unknown = set(spec.techniques) - TECHNIQUES
    if unknown:
        raise ValueError(f"{path.name} : techniques inconnues {sorted(unknown)}")
    return spec


def all_prompt_files(root: Path = PROMPTS_DIR) -> list[Path]:
    return sorted(root.glob("*/*.v*.yaml"))


@lru_cache
def load_prompt(prompt_id: str, version: int | None = None, root: Path = PROMPTS_DIR) -> PromptSpec:
    """Charge une version précise, ou la plus récente si ``version`` est None."""
    candidates = [load_prompt_file(p) for p in all_prompt_files(root)
                  if p.name.startswith(f"{prompt_id}.v")]
    candidates = [c for c in candidates if c.id == prompt_id]
    if version is not None:
        candidates = [c for c in candidates if c.version == version]
    if not candidates:
        raise KeyError(f"prompt introuvable : {prompt_id} v{version or 'dernière'}")
    return max(candidates, key=lambda c: c.version)
