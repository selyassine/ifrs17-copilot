"""Registre des dossiers, piste d'audit chaînée, comptes et rôles (D-058)."""

import sqlite3

import pytest

from core.registry import AuthError, Registry


@pytest.fixture
def reg(tmp_path):
    return Registry(tmp_path / "r.db")


def test_cycle_de_vie_et_audit(reg):
    reg.open_case("c1", "site", "alice", filename="ext01.pdf", sha256="ab" * 32)
    reg.record_outcome("c1", "alice", "validation_humaine", controls=["taux à confirmer"],
                       csm={"initial_csm": 10.0, "initial_loss_component": 0.0, "onerous": False},
                       usage={"llm_calls": 4, "tokens": 900, "cost_usd": 0.0})
    reg.record_outcome("c1", "bob", "validee", action="analyse_apres_validation", validated_by="bob")
    case = reg.get_case("c1")
    assert case["status"] == "validee" and case["validated_by"] == "bob" and case["ever_human"]
    assert [e["action"] for e in reg.events("c1")] == ["depot", "analyse", "analyse_apres_validation"]
    assert reg.verify_chain()["intacte"]


def test_chaine_d_audit_detecte_une_modification(reg, tmp_path):
    for k in range(3):
        reg.add_event("c1", "alice", f"action_{k}", {"k": k})
    db = sqlite3.connect(tmp_path / "r.db")
    db.execute("UPDATE events SET actor = 'mallory' WHERE id = 2")
    db.commit()
    res = reg.verify_chain()
    assert not res["intacte"] and res["premier_evenement_altere"] == 2


def test_liste_filtres_et_tableau_de_bord(reg):
    for k, st in enumerate(["note_prete", "validation_humaine", "note_prete"]):
        reg.open_case(f"c{k}", "n8n-email" if k else "site", "systeme", submitter=f"u{k}@x.fr")
        reg.record_outcome(f"c{k}", "systeme", st, duration_ms=1000 * (k + 1))
    rows, total = reg.list_cases(status="note_prete")
    assert total == 2 and all(r["status"] == "note_prete" for r in rows)
    assert reg.list_cases(q="u1@")[1] == 1
    d = reg.dashboard()
    assert d["dossiers"] == 3 and d["par_source"] == {"site": 1, "n8n-email": 2}
    assert d["taux_validation_humaine"] == pytest.approx(1 / 3, abs=1e-3) and d["duree_mediane_s"] == 2.0
    assert d["en_attente"][0]["case_id"] == "c1" and len(d["par_jour"]) == 30


def test_comptes_mots_de_passe_et_verrouillage(reg):
    reg.add_user("Alice", "motdepasse1", "valideur")
    token, user = reg.login("alice", "motdepasse1")
    assert user.role == "valideur" and reg.session_user(token).username == "alice"
    for _ in range(5):
        with pytest.raises(AuthError):
            reg.login("alice", "mauvais")
    with pytest.raises(AuthError, match="verrouillé"):
        reg.login("alice", "motdepasse1")
    with pytest.raises(AuthError, match="incorrect"):
        reg.login("inconnu", "x" * 8)               # même message : pas d'énumération des comptes
    reg.logout(token)
    assert reg.session_user(token) is None


def test_desactivation_coupe_les_sessions(reg):
    reg.add_user("bob", "motdepasse2", "analyste")
    token, _ = reg.login("bob", "motdepasse2")
    reg.update_user("bob", "admin", active=False)
    assert reg.session_user(token) is None
    with pytest.raises(AuthError, match="désactivé"):
        reg.login("bob", "motdepasse2")


def test_mot_de_passe_jamais_stocke_en_clair(reg, tmp_path):
    reg.add_user("carol", "secret-tres-long", "admin")
    raw = (tmp_path / "r.db").read_bytes()
    assert b"secret-tres-long" not in raw
