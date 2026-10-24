"""Authentification et rôles (D-058).

Deux façons de s'authentifier, vérifiées par la même dépendance :
- **machine** (n8n, scripts, tests) : en-tête ``X-API-Token`` = ``API_TOKEN`` du .env ; acteur
  « systeme », tous les droits, comme avant ;
- **utilisateur** (site) : ``POST /v1/auth/login`` renvoie un jeton de session, envoyé ensuite dans
  ``Authorization: Bearer …`` ; le rôle du compte limite les actions :

      analyste  : déposer et analyser des dossiers, interroger la norme, Copilot, consulter le registre
      valideur  : + approuver ou rejeter un dossier en validation humaine
      admin     : + gérer les comptes, consulter et vérifier la piste d'audit complète

Sans ``API_TOKEN`` dans le .env (développement local), les appels sans jeton restent acceptés.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from core.config import Settings, get_settings
from core.registry import RANK, Registry, get_registry


@dataclass
class Actor:
    name: str
    role: str
    kind: str                     # machine | utilisateur | anonyme

    def can(self, role: str) -> bool:
        return RANK.get(self.role, 0) >= RANK[role]


def registry(settings: Settings = Depends(get_settings)) -> Registry:
    reg = get_registry(settings.registry_path)
    if settings.admin_password and not reg.has_users():
        reg.add_user(settings.admin_username or "admin", settings.admin_password, "admin", "Administrateur")
    return reg


def current_actor(x_api_token: str | None = Header(default=None),
                  authorization: str | None = Header(default=None),
                  settings: Settings = Depends(get_settings)) -> Actor:
    if authorization and authorization.lower().startswith("bearer "):
        user = registry(settings).session_user(authorization[7:].strip())
        if user is None:
            raise HTTPException(status_code=401, detail="session expirée ou invalide : reconnectez-vous")
        return Actor(user.username, user.role, "utilisateur")
    if settings.api_token:
        if x_api_token != settings.api_token:
            raise HTTPException(status_code=401, detail="jeton API invalide")
        return Actor("systeme", "systeme", "machine")
    return Actor("anonyme", "systeme", "anonyme")


def require(role: str):
    def dependency(actor: Actor = Depends(current_actor)) -> Actor:
        if not actor.can(role):
            raise HTTPException(status_code=403, detail=f"action réservée au rôle {role} ou supérieur")
        return actor
    return dependency


# dépendances prêtes à l'emploi (une instance par rôle)
ANALYSTE = require("analyste")
VALIDEUR = require("valideur")
ADMIN = require("admin")
