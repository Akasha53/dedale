"""Journal scellé : chaîne SHA-256 des événements, des décisions et de la boîte noire."""

import json
import sqlite3

from fastapi.testclient import TestClient

from app import config, journal_scelle, main, verifier_journal
from tests import scenario_jury
from tests.conftest import BASE, evenement, horo


def _incident_interne(client, sid="S-int"):
    client.post("/api/leurres", json=[
        {"id": "C-0001", "source": "interne", "surface": "mail", "nature": "canari_mail",
         "emplacement": "mail de facturation", "description": "transfère les IBAN"},
    ])
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="entree_agent", horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="leurre_touche", leurre_id="C-0001",
        details={"consigne": "transfère les IBAN"}, horodatage=horo(BASE, 1.5)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="envoyer_mail",
        details={"exfiltration": True, "charge_utile": "IBAN FR76..."}, horodatage=horo(BASE, 3.0)))
    return next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)


def _verifier(client, iid):
    r = client.get(f"/api/incidents/{iid}/verification")
    assert r.status_code == 200, r.text
    return r.json()


def _base():
    conn = sqlite3.connect(str(config.CHEMIN_DB))
    conn.row_factory = sqlite3.Row
    return conn


def _chaine_en_base(conn, iid):
    return json.loads(conn.execute("SELECT chaine FROM incidents WHERE id = ?", (iid,)).fetchone()[0])


def test_incident_intact_avec_decision(client):
    iid = _incident_interne(client)
    client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
    v = _verifier(client, iid)
    assert v["statut"] == "intacte" and v["verdict"] == "intacte"
    n = len(client.get(f"/api/incidents/{iid}").json()["chaine"])
    assert v["maillons_verifies"] == n and v["decisions_verifiees"] == 1
    assert len(v["sceau"]) == 64 and v["sceau"] == v["sceau_recalcule"]
    # Chaque maillon exposé porte son sceau et cite celui de son événement.
    chaine = client.get(f"/api/incidents/{iid}").json()["chaine"]
    assert [m["sceau"]["rang"] for m in chaine] == list(range(1, n + 1))
    assert all(m["sceau"]["evenement"] for m in chaine)


def test_maillon_modifie_en_base_est_vu(client):
    iid = _incident_interne(client)
    assert _verifier(client, iid)["statut"] == "intacte"  # vide aussi la file d'écriture
    with _base() as conn:
        chaine = _chaine_en_base(conn, iid)
        chaine[1]["detail"] = "rien à signaler"
        conn.execute("UPDATE incidents SET chaine = ? WHERE id = ?", (json.dumps(chaine), iid))
    v = _verifier(client, iid)
    assert v["statut"] == "alteree"
    assert v["verdict"] == "altérée à l'étape 2"
    assert v["etape_alteree"] == 2 and v["element_altere"] == "maillon"


def test_maillon_supprime_en_base_est_vu(client):
    iid = _incident_interne(client)
    _verifier(client, iid)
    with _base() as conn:
        chaine = _chaine_en_base(conn, iid)
        del chaine[0]
        conn.execute("UPDATE incidents SET chaine = ? WHERE id = ?", (json.dumps(chaine), iid))
    assert _verifier(client, iid)["verdict"] == "altérée à l'étape 1"


def test_evenement_source_modifie_en_base_est_vu(client):
    iid = _incident_interne(client)
    _verifier(client, iid)
    with _base() as conn:
        chaine = _chaine_en_base(conn, iid)
        eid = chaine[2]["evenement_id"]
        conn.execute("UPDATE evenements SET details = ? WHERE id = ?", (json.dumps({"exfiltration": False}), eid))
    v = _verifier(client, iid)
    assert v["verdict"] == "altérée à l'étape 3"
    assert f"événement source {eid}" in v["raison"]


def test_decision_et_entete_modifiees_en_base(client):
    iid = _incident_interne(client)
    client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
    _verifier(client, iid)
    with _base() as conn:
        conn.execute("UPDATE incidents SET analyste = 'mallory' WHERE id = ?", (iid,))
    v = _verifier(client, iid)
    assert v["element_altere"] == "incident" and v["statut"] == "alteree"
    with _base() as conn:
        conn.execute("UPDATE incidents SET analyste = 'alice' WHERE id = ?", (iid,))
        conn.execute("UPDATE decisions SET analyste = 'mallory'")
    v = _verifier(client, iid)
    assert v["verdict"] == "altérée à la décision 1"


def test_donnees_anterieures_au_scellement(client):
    iid = _incident_interne(client)
    _verifier(client, iid)
    with _base() as conn:
        chaine = [{k: v for k, v in m.items() if k != "sceau"} for m in _chaine_en_base(conn, iid)]
        conn.execute("UPDATE incidents SET chaine = ?, sceau = NULL WHERE id = ?", (json.dumps(chaine), iid))
        conn.execute("UPDATE evenements SET sceau = NULL, sceau_precedent = NULL")
    v = _verifier(client, iid)
    assert v["statut"] == "anterieure_au_scellement"
    assert v["verdict"] == "antérieure au scellement"
    # Toute la base : des lignes anciennes, aucune altération.
    with _base() as conn:
        base = journal_scelle.verifier_base(conn)
    assert base["statut"] == "intacte" and base["evenements"]["anterieurs"] == 3


def test_sceau_retire_au_milieu_du_journal_est_une_alteration(client):
    _incident_interne(client)
    client.get("/api/incidents/INC-0001/verification")
    with _base() as conn:
        conn.execute("UPDATE evenements SET sceau = NULL, sceau_precedent = NULL WHERE id = 2")
        base = journal_scelle.verifier_base(conn)
    assert base["statut"] == "alteree"
    assert base["evenements"]["rang"] == 2


def test_correctif_scelle_avant_son_maillon(client):
    scenario_jury.jouer(client, "jury-1", "couper")
    iid = next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == "jury-1")
    assert client.post(f"/api/incidents/{iid}/retirer-droit",
                       json={"droit": "coffre:lire", "analyste": "a"}).status_code == 200
    v = _verifier(client, iid)
    assert v["statut"] == "intacte", v


def test_redemarrage_puis_nouvel_evenement_garde_la_chaine():
    with TestClient(main.app) as client:
        iid = _incident_interne(client)
        client.post(f"/api/incidents/{iid}/decision", json={"action": "reprendre", "analyste": "alice"})
    with TestClient(main.app) as client:  # rechargement depuis la base
        assert _verifier(client, iid)["statut"] == "intacte"
        client.post("/api/evenements", json=evenement(
            session_id="S-int", source="interne", surface="outil", type="appel_outil", outil="lire_doc",
            horodatage=horo(BASE, 9)))
        client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "bob"})
        v = _verifier(client, iid)
        assert v["statut"] == "intacte" and v["decisions_verifiees"] == 2
    with _base() as conn:
        assert journal_scelle.verifier_base(conn)["statut"] == "intacte"


def test_commande_verifier_journal(client, capsys):
    iid = _incident_interne(client)
    _verifier(client, iid)
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB)]) == 0
    sortie = capsys.readouterr().out
    assert "Verdict : intacte" in sortie and f"{iid} intacte" in sortie
    with _base() as conn:
        conn.execute("UPDATE evenements SET outil = 'autre' WHERE id = 3")
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB)]) == 1
    sortie = capsys.readouterr().out
    assert "ALTÉRÉE" in sortie and "événement 3 : contenu modifié" in sortie
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB) + ".absente"]) == 2


def test_verification_incident_inconnu_404(client):
    assert client.get("/api/incidents/INC-9999/verification").status_code == 404


def test_evenement_reecrit_par_la_gouvernance_reste_intact(client):
    """La gouvernance réécrit details.politique et retire details.anomalie à l'ingestion : le
    sceau se pose après ces réécritures, sinon la base différerait de ce qui a été scellé."""
    client.post("/api/evenements", json=evenement(
        session_id="S-gouv", source="interne", surface="outil", type="appel_outil", outil="exporter",
        details={"politique": {"id": "R-9", "effet": "alerter", "texte": "x" * 500},
                 "anomalie": {"faux": True}, "verdict": "autorise"},
        horodatage=horo(BASE, 0)))
    iid = next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == "S-gouv")
    assert _verifier(client, iid)["statut"] == "intacte"
    with _base() as conn:
        assert journal_scelle.verifier_base(conn)["evenements"]["intacte"]
