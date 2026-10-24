"""Registre des dossiers, piste d'audit et comptes utilisateurs (D-058).

Une base SQLite (fichier ``data/registry.db``, hors Git) : aucun serveur à installer, transactions
ACID, sauvegarde par simple copie du fichier. Quatre tables :

- ``cases``    : un dossier par ligne (source, déposant, document, statut, résultats, note, validation) ;
- ``events``   : la **piste d'audit**, en ajout seul. Chaque événement porte l'empreinte SHA-256 du
                 précédent (chaîne de hachage) : modifier ou supprimer un événement après coup casse la
                 chaîne, et ``verify_chain`` le détecte ;
- ``users``    : comptes (analyste, valideur, admin), mots de passe dérivés par PBKDF2-SHA256
                 (200 000 itérations, sel aléatoire), verrouillage après 5 échecs ;
- ``sessions`` : jetons de session (seule leur empreinte est stockée), valables 8 heures.

    python -m core.registry add-user alice --role valideur      # demande le mot de passe
    python -m core.registry users
    python -m core.registry verify                              # contrôle la chaîne d'audit
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import secrets
import sqlite3
import statistics
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROLES = ("analyste", "valideur", "admin")
RANK = {"analyste": 1, "valideur": 2, "admin": 3, "systeme": 4}
STATUSES = ("en_cours", "note_prete", "validation_humaine", "validee", "rejetee", "document_illisible", "erreur")
SESSION_HOURS = 8
MAX_FAILURES = 5
LOCK_MINUTES = 5
PBKDF2_ITERATIONS = 200_000
GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL,
    submitter TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    group_id TEXT NOT NULL DEFAULT '',
    currency TEXT NOT NULL DEFAULT '',
    unit TEXT NOT NULL DEFAULT '',
    onerous INTEGER,
    csm REAL,
    loss REAL,
    controls TEXT NOT NULL DEFAULT '[]',
    portfolio TEXT,
    note_html TEXT,
    note_markdown TEXT,
    validated_by TEXT NOT NULL DEFAULT '',
    validated_at TEXT NOT NULL DEFAULT '',
    decision_comment TEXT NOT NULL DEFAULT '',
    duration_ms REAL,
    llm_calls INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    ever_human INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS cases_status ON cases(status);
CREATE INDEX IF NOT EXISTS cases_created ON cases(created_at);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_case ON events(case_id);
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    failures INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_login TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    source TEXT NOT NULL,
    tools TEXT NOT NULL DEFAULT '[]',
    refs TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS memories_case ON memories(case_id);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS).hex()


@dataclass
class User:
    username: str
    display_name: str
    role: str
    active: bool = True
    last_login: str = ""

    def can(self, role: str) -> bool:
        return RANK.get(self.role, 0) >= RANK[role]

    def public(self) -> dict:
        return {"username": self.username, "display_name": self.display_name, "role": self.role,
                "active": self.active, "last_login": self.last_login}


class AuthError(Exception):
    """Identifiants refusés ou compte verrouillé (message destiné à l'utilisateur)."""


class Registry:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        with self._lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.executescript(SCHEMA)

    # ------------------------------------------------------------------ audit
    def add_event(self, case_id: str, actor: str, action: str, detail: dict | None = None) -> dict:
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT hash FROM events ORDER BY id DESC LIMIT 1").fetchone()
                prev = row["hash"] if row else GENESIS
                at = now()
                payload = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True, default=str)
                digest = _sha("|".join([prev, case_id, at, actor, action, payload]))
                self.db.execute("INSERT INTO events (case_id, at, actor, action, detail, prev_hash, hash) "
                                "VALUES (?, ?, ?, ?, ?, ?, ?)", (case_id, at, actor, action, payload, prev, digest))
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return {"case_id": case_id, "at": at, "actor": actor, "action": action, "detail": detail or {}, "hash": digest}

    def events(self, case_id: str | None = None, limit: int = 500) -> list[dict]:
        sql = "SELECT * FROM events" + (" WHERE case_id = ?" if case_id else "") + " ORDER BY id DESC LIMIT ?"
        args = (case_id, limit) if case_id else (limit,)
        with self._lock:
            rows = self.db.execute(sql, args).fetchall()
        return [{"id": r["id"], "case_id": r["case_id"], "at": r["at"], "actor": r["actor"], "action": r["action"],
                 "detail": json.loads(r["detail"]), "hash": r["hash"]} for r in rows][::-1]

    # ------------------------------------------------------------------ mémoire du Copilot (D-061)
    def add_memory(self, case_id: str, actor: str, question: str, answer: str, source: str,
                   tools: list | None = None, refs: list[str] | None = None) -> dict:
        """Mémoire épisodique : un échange déjà contrôlé (réponse acceptée par le code ou écrite par lui)."""
        row = {"case_id": case_id, "at": now(), "actor": actor, "question": question[:500], "answer": answer[:4000],
               "source": source, "tools": json.dumps(tools or [], ensure_ascii=False),
               "refs": json.dumps(refs or [], ensure_ascii=False)}
        with self._lock:
            cur = self.db.execute("INSERT INTO memories (case_id, at, actor, question, answer, source, tools, refs) "
                                  "VALUES (:case_id, :at, :actor, :question, :answer, :source, :tools, :refs)", row)
        return {**row, "id": cur.lastrowid, "tools": tools or [], "refs": refs or []}

    def memories(self, case_id: str, limit: int = 50) -> list[dict]:
        """Échanges du dossier, du plus ancien au plus récent."""
        with self._lock:
            rows = self.db.execute("SELECT * FROM memories WHERE case_id = ? ORDER BY id DESC LIMIT ?",
                                   (case_id, limit)).fetchall()
        return [{**dict(r), "tools": json.loads(r["tools"]), "refs": json.loads(r["refs"])} for r in rows][::-1]

    def forget(self, case_id: str) -> int:
        with self._lock:
            return self.db.execute("DELETE FROM memories WHERE case_id = ?", (case_id,)).rowcount

    def verify_chain(self) -> dict:
        """Recalcule toute la chaîne : le premier événement modifié, supprimé ou inséré est signalé."""
        prev, n = GENESIS, 0
        with self._lock:
            rows = self.db.execute("SELECT * FROM events ORDER BY id").fetchall()
        for r in rows:
            expected = _sha("|".join([prev, r["case_id"], r["at"], r["actor"], r["action"], r["detail"]]))
            if r["prev_hash"] != prev or r["hash"] != expected:
                return {"intacte": False, "evenements": len(rows), "premier_evenement_altere": r["id"]}
            prev, n = r["hash"], n + 1
        return {"intacte": True, "evenements": n, "derniere_empreinte": prev}

    # ------------------------------------------------------------------ dossiers
    def open_case(self, case_id: str, source: str, actor: str, submitter: str = "", filename: str = "",
                  sha256: str = "") -> None:
        with self._lock:
            exists = self.db.execute("SELECT 1 FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if not exists:
                t = now()
                self.db.execute("INSERT INTO cases (case_id, created_at, updated_at, source, submitter, filename, "
                                "sha256, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'en_cours')",
                                (case_id, t, t, source, submitter or actor, filename, sha256))
        self.add_event(case_id, actor, "depot" if not exists else "reprise",
                       {"source": source, "document": filename, "sha256": sha256[:16], "deposant": submitter or actor})

    def record_outcome(self, case_id: str, actor: str, status: str, *, action: str = "analyse",
                       portfolio: dict | None = None, csm: dict | None = None, controls: list[str] | None = None,
                       note_html: str | None = None, note_markdown: str | None = None,
                       duration_ms: float | None = None, usage: dict | None = None,
                       validated_by: str = "", comment: str = "") -> None:
        if status not in STATUSES:
            raise ValueError(f"statut inconnu : {status}")
        fields: dict[str, Any] = {"status": status, "updated_at": now()}
        if portfolio is not None:
            fields |= {"portfolio": json.dumps(portfolio, ensure_ascii=False), "group_id": portfolio.get("group_id", ""),
                       "currency": portfolio.get("currency", ""),
                       "unit": {1: "", 1000: "milliers", 1_000_000: "millions"}.get(portfolio.get("unit_multiplier", 1), "")}
        if csm is not None:
            fields |= {"csm": csm.get("initial_csm"), "loss": csm.get("initial_loss_component"),
                       "onerous": int(bool(csm.get("onerous")))}
        if controls is not None:
            fields["controls"] = json.dumps(controls, ensure_ascii=False)
        if note_html is not None:
            fields |= {"note_html": note_html, "note_markdown": note_markdown or ""}
        if duration_ms is not None:
            fields["duration_ms"] = duration_ms
        if usage:
            fields |= {"llm_calls": usage.get("llm_calls", 0), "tokens": usage.get("tokens", 0),
                       "cost_usd": usage.get("cost_usd", 0.0)}
        if status == "validation_humaine":
            fields["ever_human"] = 1
        if validated_by:
            fields |= {"validated_by": validated_by, "validated_at": now(), "ever_human": 1}
        if comment:
            fields["decision_comment"] = comment
        with self._lock:
            cols = ", ".join(f"{k} = ?" for k in fields)
            self.db.execute(f"UPDATE cases SET {cols} WHERE case_id = ?", (*fields.values(), case_id))
        detail = {"statut": status}
        if csm is not None:
            detail |= {"csm": round(csm.get("initial_csm") or 0, 2), "perte": round(csm.get("initial_loss_component") or 0, 2)}
        if controls:
            detail["controles"] = controls[:5]
        if comment:
            detail["commentaire"] = comment[:300]
        if usage:
            detail["appels_llm"] = usage.get("llm_calls", 0)
        self.add_event(case_id, actor, action, detail)

    def get_case(self, case_id: str, with_note: bool = False) -> dict | None:
        with self._lock:
            r = self.db.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return self._row(r, with_note) if r else None

    def note_html(self, case_id: str) -> str | None:
        with self._lock:
            r = self.db.execute("SELECT note_html FROM cases WHERE case_id = ?", (case_id,)).fetchone()
        return r["note_html"] if r else None

    def list_cases(self, status: str = "", source: str = "", q: str = "", limit: int = 50,
                   offset: int = 0) -> tuple[list[dict], int]:
        where, args = [], []
        if status:
            where.append("status = ?")
            args.append(status)
        if source:
            where.append("source = ?")
            args.append(source)
        if q:
            where.append("(case_id LIKE ? OR group_id LIKE ? OR submitter LIKE ? OR filename LIKE ?)")
            args += [f"%{q}%"] * 4
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock:
            total = self.db.execute(f"SELECT COUNT(*) FROM cases{clause}", args).fetchone()[0]
            rows = self.db.execute(f"SELECT * FROM cases{clause} ORDER BY created_at DESC, case_id DESC "
                                   "LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return [self._row(r) for r in rows], total

    @staticmethod
    def _row(r: sqlite3.Row, with_note: bool = False) -> dict:
        d = dict(r)
        d["controls"] = json.loads(d["controls"] or "[]")
        d["portfolio"] = json.loads(d["portfolio"]) if d.get("portfolio") else None
        d["onerous"] = None if d["onerous"] is None else bool(d["onerous"])
        d["ever_human"] = bool(d["ever_human"])
        d["has_note"] = bool(d.get("note_html"))
        if not with_note:
            d.pop("note_html", None)
            d.pop("note_markdown", None)
        return d

    # ------------------------------------------------------------------ tableau de bord
    def dashboard(self, days: int = 30) -> dict:
        with self._lock:
            rows = [dict(r) for r in self.db.execute(
                "SELECT case_id, created_at, updated_at, source, status, duration_ms, llm_calls, tokens, cost_usd, "
                "ever_human, validated_at, onerous FROM cases").fetchall()]
        by_status = Counter(r["status"] for r in rows)
        by_source = Counter(r["source"] for r in rows)
        analysed = [r for r in rows if r["status"] not in ("en_cours", "erreur", "document_illisible")]
        durations = [r["duration_ms"] / 1000 for r in rows if r["duration_ms"]]
        today = datetime.now(UTC).date()
        per_day = Counter(r["created_at"][:10] for r in rows)
        series = [{"jour": (today - timedelta(days=k)).isoformat(),
                   "dossiers": per_day.get((today - timedelta(days=k)).isoformat(), 0)} for k in range(days - 1, -1, -1)]
        waiting = sorted((r for r in rows if r["status"] == "validation_humaine"), key=lambda r: r["updated_at"])
        validation_delays = []
        for r in rows:
            if r["validated_at"]:
                start = datetime.fromisoformat(r["created_at"])
                validation_delays.append((datetime.fromisoformat(r["validated_at"]) - start).total_seconds() / 3600)
        n = len(rows)
        return {
            "dossiers": n,
            "par_statut": {s: by_status.get(s, 0) for s in STATUSES},
            "par_source": dict(by_source),
            "taux_validation_humaine": round(sum(r["ever_human"] for r in analysed) / len(analysed), 3) if analysed else 0.0,
            "taux_note_directe": round(sum(1 for r in analysed if not r["ever_human"]) / len(analysed), 3) if analysed else 0.0,
            "groupes_deficitaires": sum(1 for r in analysed if r["onerous"]),
            "duree_mediane_s": round(statistics.median(durations), 1) if durations else None,
            "delai_median_validation_h": round(statistics.median(validation_delays), 1) if validation_delays else None,
            "appels_llm_moyens": round(statistics.mean(r["llm_calls"] for r in rows), 2) if rows else 0.0,
            "tokens_total": sum(r["tokens"] for r in rows),
            "cout_total_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "par_jour": series,
            "en_attente": [{"case_id": r["case_id"], "depuis": r["updated_at"]} for r in waiting[:10]],
        }

    # ------------------------------------------------------------------ comptes
    def has_users(self) -> bool:
        with self._lock:
            return self.db.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None

    def add_user(self, username: str, password: str, role: str, display_name: str = "", actor: str = "systeme") -> User:
        username = username.strip().lower()
        if role not in ROLES:
            raise ValueError(f"rôle inconnu : {role} (choisir parmi {', '.join(ROLES)})")
        if not username.replace(".", "").replace("-", "").replace("_", "").isalnum() or len(username) > 40:
            raise ValueError("identifiant : lettres, chiffres, point, tiret ou souligné (40 caractères au plus)")
        if len(password) < 8:
            raise ValueError("mot de passe : 8 caractères au moins")
        salt = secrets.token_hex(16)
        with self._lock:
            try:
                self.db.execute("INSERT INTO users (username, display_name, role, salt, password_hash, created_at) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (username, display_name or username, role, salt, _hash_password(password, salt), now()))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"l'identifiant {username} existe déjà") from exc
        self.add_event("-", actor, "compte_cree", {"utilisateur": username, "role": role})
        return User(username, display_name or username, role)

    def update_user(self, username: str, actor: str, role: str | None = None, active: bool | None = None,
                    password: str | None = None) -> User:
        user = self.get_user(username)
        if user is None:
            raise ValueError("utilisateur inconnu")
        changes: dict[str, Any] = {}
        if role is not None:
            if role not in ROLES:
                raise ValueError("rôle inconnu")
            changes["role"] = role
        if active is not None:
            changes["active"] = int(active)
        if password is not None:
            if len(password) < 8:
                raise ValueError("mot de passe : 8 caractères au moins")
            salt = secrets.token_hex(16)
            changes |= {"salt": salt, "password_hash": _hash_password(password, salt), "failures": 0, "locked_until": ""}
        if changes:
            with self._lock:
                cols = ", ".join(f"{k} = ?" for k in changes)
                self.db.execute(f"UPDATE users SET {cols} WHERE username = ?", (*changes.values(), user.username))
                if active is False or password is not None:
                    self.db.execute("DELETE FROM sessions WHERE username = ?", (user.username,))
            self.add_event("-", actor, "compte_modifie", {"utilisateur": user.username,
                                                          **{k: v for k, v in changes.items() if k in ("role", "active")},
                                                          **({"mot_de_passe": "réinitialisé"} if password else {})})
        return self.get_user(user.username)

    def get_user(self, username: str) -> User | None:
        with self._lock:
            r = self.db.execute("SELECT * FROM users WHERE username = ?", (username.strip().lower(),)).fetchone()
        return User(r["username"], r["display_name"], r["role"], bool(r["active"]), r["last_login"]) if r else None

    def list_users(self) -> list[User]:
        with self._lock:
            rows = self.db.execute("SELECT * FROM users ORDER BY username").fetchall()
        return [User(r["username"], r["display_name"], r["role"], bool(r["active"]), r["last_login"]) for r in rows]

    def login(self, username: str, password: str) -> tuple[str, User]:
        """Renvoie (jeton de session, utilisateur). Même message d'erreur que le compte existe ou non."""
        username = username.strip().lower()
        with self._lock:
            r = self.db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        refused = AuthError("identifiant ou mot de passe incorrect")
        if r is None:
            _hash_password(password, "00" * 16)         # même durée de calcul : pas d'énumération des comptes
            raise refused
        if r["locked_until"] and r["locked_until"] > now():
            raise AuthError("compte verrouillé après plusieurs échecs : réessayer dans quelques minutes")
        if not r["active"]:
            raise AuthError("compte désactivé")
        if not hmac.compare_digest(_hash_password(password, r["salt"]), r["password_hash"]):
            failures = r["failures"] + 1
            locked = (datetime.now(UTC) + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds") \
                if failures >= MAX_FAILURES else ""
            with self._lock:
                self.db.execute("UPDATE users SET failures = ?, locked_until = ? WHERE username = ?",
                                (0 if locked else failures, locked, username))
            self.add_event("-", username, "connexion_refusee", {"verrouille": bool(locked)})
            raise refused
        token = secrets.token_urlsafe(32)
        expires = (datetime.now(UTC) + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        with self._lock:
            self.db.execute("UPDATE users SET failures = 0, locked_until = '', last_login = ? WHERE username = ?",
                            (now(), username))
            self.db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))
            self.db.execute("INSERT INTO sessions (token_hash, username, expires_at) VALUES (?, ?, ?)",
                            (_sha(token), username, expires))
        self.add_event("-", username, "connexion", {})
        return token, self.get_user(username)

    def session_user(self, token: str) -> User | None:
        with self._lock:
            r = self.db.execute("SELECT username, expires_at FROM sessions WHERE token_hash = ?", (_sha(token),)).fetchone()
        if r is None or r["expires_at"] < now():
            return None
        user = self.get_user(r["username"])
        return user if user and user.active else None

    def logout(self, token: str) -> None:
        with self._lock:
            r = self.db.execute("SELECT username FROM sessions WHERE token_hash = ?", (_sha(token),)).fetchone()
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))
        if r:
            self.add_event("-", r["username"], "deconnexion", {})


_registries: dict[str, Registry] = {}
_reg_lock = threading.Lock()


def get_registry(path: Path) -> Registry:
    """Une connexion par fichier, partagée par les requêtes (SQLite + verrou : sûr entre threads)."""
    key = str(Path(path).resolve())
    with _reg_lock:
        if key not in _registries:
            _registries[key] = Registry(Path(path))
        return _registries[key]


def llm_usage(trace_path: Path, case_id: str, offset: int = 0) -> dict:
    """Appels LLM, tokens et coût d'un dossier, lus dans la trace JSONL à partir de ``offset`` (octets)."""
    calls = tokens = 0
    cost = 0.0
    if not trace_path.exists():
        return {"llm_calls": 0, "tokens": 0, "cost_usd": 0.0}
    with trace_path.open(encoding="utf-8") as f:
        f.seek(offset)
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("kind") == "llm" and str(rec.get("case_id", "")).endswith(case_id):
                calls += 1
                tokens += int(rec.get("tokens_in") or 0) + int(rec.get("tokens_out") or 0)
                cost += float(rec.get("cost_usd") or 0)
    return {"llm_calls": calls, "tokens": tokens, "cost_usd": round(cost, 6)}


def main() -> None:
    from core.config import get_settings

    ap = argparse.ArgumentParser(description="Comptes et piste d'audit du registre")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add-user")
    a.add_argument("username")
    a.add_argument("--role", choices=ROLES, required=True)
    a.add_argument("--name", default="")
    sub.add_parser("users")
    sub.add_parser("verify")
    args = ap.parse_args()
    reg = get_registry(get_settings().registry_path)
    if args.cmd == "add-user":
        pwd = getpass.getpass("Mot de passe (8 caractères au moins) : ")
        if pwd != getpass.getpass("Confirmer : "):
            raise SystemExit("les deux mots de passe diffèrent")
        u = reg.add_user(args.username, pwd, args.role, args.name)
        print(f"compte créé : {u.username} ({u.role})")
    elif args.cmd == "users":
        for u in reg.list_users():
            print(f"{u.username:<20} {u.role:<10} {'actif' if u.active else 'désactivé':<10} {u.last_login}")
    else:
        print(json.dumps(reg.verify_chain(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
