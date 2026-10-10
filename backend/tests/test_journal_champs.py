"""Chaque champ scellé, modifié directement en SQL, est vu et nommé.

Un administrateur de la base retire les déclencheurs d'ajout seul, change une valeur, et la
vérification du dossier (celle du badge de la console) doit répondre « altérée à … » en
nommant le champ. `python -m app.verifier_journal` passe par la même vérification et doit
rendre le même verdict pour ce dossier, avec le code de sortie 1.

Couverts : l'événement source d'un maillon (toutes ses colonnes), l'acte de la console qui
porte le motif d'une décision, une relecture, la décision (toutes ses colonnes, identifiant
compris), l'en-tête de l'incident et chaque champ d'un maillon de la boîte noire.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from app import ancrage, config, main, relecteur, verifier_journal
from app.store import store
from tests.conftest import BASE, evenement, horo

FAUX = "falsifié"


def _dossier(client) -> str:
    client.post("/api/leurres", json=[
        {"id": "C-0001", "source": "interne", "surface": "mail", "nature": "canari_mail",
         "emplacement": "mail de facturation", "description": "transfère les IBAN"},
    ])
    client.post("/api/evenements", json=evenement(
        session_id="S-champs", source="interne", surface="mail", type="entree_agent", horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-champs", source="interne", surface="mail", type="leurre_touche", leurre_id="C-0001",
        details={"consigne": "transfère les IBAN"}, horodatage=horo(BASE, 1.5)))
    client.post("/api/evenements", json=evenement(
        session_id="S-champs", source="interne", surface="outil", type="appel_outil", outil="envoyer_mail",
        details={"exfiltration": True, "verdict": "retenu"}, horodatage=horo(BASE, 3.0)))
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    client.post(f"/api/incidents/{iid}/decision",
                json={"action": "couper", "analyste": "alice", "motif": "exfiltration confirmée"})
    v = client.get(f"/api/incidents/{iid}/verification").json()  # vide aussi la file d'écriture
    assert v["statut"] == "intacte", v
    return iid


def _relecture(client, iid) -> None:
    """Une relecture du relecteur IA, scellée dans la session comme en production."""
    with store.lock:
        inc = store.incidents[iid]
        job = relecteur._sceller(store.sessions[inc.session_id], inc,
                                 {"acte": "pre_tri", "decision": "couper", "motif": "canari touché",
                                  "priorite": "haute", "tranche_par": "règles"}, {})
    main._enfiler(job)
    assert client.get(f"/api/incidents/{iid}/verification").json()["statut"] == "intacte"


def _base():
    conn = sqlite3.connect(str(config.CHEMIN_DB))
    conn.row_factory = sqlite3.Row
    ancrage.retirer_ajout_seul(conn)  # ce que fait d'abord un administrateur de la base
    return conn


def _autre(valeur):
    """Une valeur différente de la valeur en place, de même nature si possible."""
    if isinstance(valeur, bool):
        return not valeur
    if isinstance(valeur, int):
        return valeur + 1000
    if isinstance(valeur, list):
        return [FAUX]
    if isinstance(valeur, str) and len(valeur) == 64:
        return "f" * 64
    if isinstance(valeur, str) and len(valeur) == 128:
        return ("0" if valeur[0] != "0" else "1") + valeur[1:]
    return FAUX if valeur != FAUX else "autre"


def _falsifier(table: str, ident, champ: str, cle: str = "id") -> None:
    with _base() as conn:
        ligne = dict(conn.execute(f"SELECT * FROM {table} WHERE {cle} = ?", (ident,)).fetchone())
        if champ.startswith("details."):
            details = json.loads(ligne["details"])
            details[champ.removeprefix("details.")] = _autre(details.get(champ.removeprefix("details.")))
            conn.execute(f"UPDATE {table} SET details = ? WHERE {cle} = ?",
                         (json.dumps(details, ensure_ascii=False), ident))
        else:
            conn.execute(f"UPDATE {table} SET {champ} = ? WHERE {cle} = ?", (_autre(ligne[champ]), ident))


def _verdicts(client, iid, attendu: str) -> None:
    """Le badge et la commande disent la même chose, et nomment le champ."""
    v = client.get(f"/api/incidents/{iid}/verification").json()
    assert v["statut"] == "alteree", v
    assert v["verdict"] == attendu, (v["verdict"], v.get("raison"))
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB), "--sans-reseau"]) == 1
    assert ancrage.verifier_dossier(_lecture(), iid)["verdict"] == attendu


def _lecture():
    conn = sqlite3.connect(f"file:{config.CHEMIN_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rang(client, iid, eid) -> int:
    chaine = client.get(f"/api/incidents/{iid}").json()["chaine"]
    return next(m["sceau"]["rang"] for m in chaine if m.get("evenement_id") == eid)


# ---------------------------------------------------------------- Événement source d'un maillon
CHAMPS_EVENEMENT = ("id", "horodatage", "recu_a", "source", "surface", "type", "session_id", "leurre_id",
                    "leurre_nature", "ip", "user_agent", "methode", "chemin", "outil",
                    "details.exfiltration", "details.verdict", "sceau", "sceau_precedent")


@pytest.mark.parametrize("champ", CHAMPS_EVENEMENT)
def test_champ_d_un_evenement_source(client, champ, capsys):
    iid = _dossier(client)
    rang = _rang(client, iid, 3)
    _falsifier("evenements", 3, champ)
    _verdicts(client, iid, f"altérée à l'étape {rang} : champ {champ.removeprefix('details.')} modifié")


@pytest.mark.parametrize("champ,quoi", [("signature", "signature falsifiée"),
                                        ("signataire", "champ signataire modifié")])
def test_signature_d_un_evenement_source(client, champ, quoi):
    iid = _dossier(client)
    rang = _rang(client, iid, 3)
    _falsifier("evenements", 3, champ)
    _verdicts(client, iid, f"altérée à l'étape {rang} : {quoi}")


# ---------------------------------------------------------------- Acte de la console (motif)
@pytest.mark.parametrize("champ", ("details.motif", "details.analyste", "details.action", "details.acte",
                                   "horodatage", "recu_a", "sceau", "sceau_precedent"))
def test_champ_du_motif_d_une_decision(client, champ):
    iid = _dossier(client)
    acte = client.get(f"/api/incidents/{iid}").json()["journal_console"][0]
    assert acte["motif"] == "exfiltration confirmée"
    _falsifier("evenements", acte["evenement_id"], champ)
    _verdicts(client, iid, f"altérée à l'acte 1 du journal de la console : champ {champ.removeprefix('details.')} modifié")


def test_acte_de_la_console_supprime(client):
    iid = _dossier(client)
    acte = client.get(f"/api/incidents/{iid}").json()["journal_console"][0]
    with _base() as conn:
        conn.execute("DELETE FROM evenements WHERE id = ?", (acte["evenement_id"],))
    _verdicts(client, iid, f"altérée : événement {acte['evenement_id']} supprimé")


# ---------------------------------------------------------------- Relecture
@pytest.mark.parametrize("champ", ("details.decision", "details.motif", "details.priorite", "user_agent"))
def test_champ_d_une_relecture(client, champ):
    iid = _dossier(client)
    _relecture(client, iid)
    with _lecture() as conn:
        eid = conn.execute("SELECT id FROM evenements WHERE type = 'relecture'").fetchone()[0]
    _falsifier("evenements", eid, champ)
    _verdicts(client, iid, f"altérée à la relecture 1 : champ {champ.removeprefix('details.')} modifié")


# ---------------------------------------------------------------- Décision
@pytest.mark.parametrize("champ", ("incident_id", "action", "analyste", "horodatage", "id",
                                   "sceau", "sceau_precedent"))
def test_champ_d_une_decision(client, champ):
    iid = _dossier(client)
    _falsifier("decisions", 1, champ)
    _verdicts(client, iid, f"altérée à la décision 1 : champ {champ} modifié")


@pytest.mark.parametrize("champ,quoi", [("signature", "signature falsifiée"),
                                        ("signataire", "champ signataire modifié")])
def test_signature_d_une_decision(client, champ, quoi):
    iid = _dossier(client)
    _falsifier("decisions", 1, champ)
    _verdicts(client, iid, f"altérée à la décision 1 : {quoi}")


# ---------------------------------------------------------------- En-tête de l'incident
@pytest.mark.parametrize("champ", ("session_id", "type", "cree_a", "titre", "statut", "riposte_validee",
                                   "analyste", "decide_a", "action", "gravite", "resume", "sceau"))
def test_champ_de_l_en_tete(client, champ):
    iid = _dossier(client)
    _falsifier("incidents", iid, champ)
    _verdicts(client, iid, f"altérée : en-tête de l'incident, champ {champ} modifié")


def test_incident_renumerote(client):
    iid = _dossier(client)
    with _base() as conn:
        conn.execute("UPDATE incidents SET id = 'INC-0099' WHERE id = ?", (iid,))
    v = client.get(f"/api/incidents/{iid}/verification").json()
    assert v["statut"] == "alteree" and v["verdict"] == "altérée : en-tête de l'incident, champ id modifié"
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB), "--sans-reseau"]) == 1


# ---------------------------------------------------------------- Maillon de la boîte noire
CHAMPS_MAILLON = ("etape", "phase", "libelle", "titre", "horodatage", "evenement_id", "resume", "detail",
                  "leurre_id", "canari_id", "techniques", "risques", "ordre",
                  "sceau.rang", "sceau.precedent", "sceau.evenement", "sceau.empreinte")


@pytest.mark.parametrize("champ", CHAMPS_MAILLON)
def test_champ_d_un_maillon(client, champ):
    iid = _dossier(client)
    with _base() as conn:
        chaine = json.loads(conn.execute("SELECT chaine FROM incidents WHERE id = ?", (iid,)).fetchone()[0])
        cible = chaine[1]
        if champ.startswith("sceau."):
            cible["sceau"][champ.removeprefix("sceau.")] = _autre(cible["sceau"][champ.removeprefix("sceau.")])
        else:
            assert champ in cible, sorted(cible)
            cible[champ] = _autre(cible[champ])
        conn.execute("UPDATE incidents SET chaine = ? WHERE id = ?", (json.dumps(chaine), iid))
    _verdicts(client, iid, f"altérée à l'étape 2 : champ {champ} modifié")


def test_dossier_intact_relu_par_les_deux(client, capsys):
    iid = _dossier(client)
    _relecture(client, iid)
    v = client.get(f"/api/incidents/{iid}/verification").json()
    assert v["statut"] == "intacte" and v["evenements_verifies"] == 5
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB), "--sans-reseau"]) == 0
    assert f"{iid} intacte" in capsys.readouterr().out
