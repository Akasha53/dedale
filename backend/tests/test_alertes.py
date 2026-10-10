"""Alerte « décision attendue » : message Slack, faux récepteur local, aucun envoi par défaut."""

import threading
import time

import pytest

from app import alertes, recepteur_demo
from tests.test_journal_scelle import _incident_interne


@pytest.fixture(autouse=True)
def _alertes_vides(monkeypatch):
    monkeypatch.delenv("DEDALE_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("DEDALE_CONSOLE_URL", "http://console.test")
    alertes.historique.clear()
    alertes._envois.clear()
    yield
    alertes.historique.clear()
    alertes._envois.clear()


def _attendre(condition, delai=3.0):
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def recepteur():
    serveur = recepteur_demo.creer_serveur(0, afficher=False)
    fil = threading.Thread(target=serveur.serve_forever, daemon=True)
    fil.start()
    yield serveur
    serveur.shutdown()
    serveur.server_close()


def test_message_au_format_slack():
    detail = {"id": "INC-0007", "titre": "Agent <!channel> détourné", "gravite": "haute",
              "session_id": "S-1", "source": "interne", "etat": "suspendue",
              "ouvert_le": "2026-10-10T19:55:34+02:00", "resume": "résumé"}
    m = alertes.construire_message(detail, "L'agent a lu un mail piégé & a voulu l'envoyer.")
    assert "INC-0007" in m["text"] and "http://console.test/?incident=INC-0007" in m["text"]
    assert [b["type"] for b in m["blocks"]] == ["header", "section", "section", "section", "actions", "context"]
    assert m["blocks"][4]["elements"][0]["url"] == "http://console.test/?incident=INC-0007"
    section = m["blocks"][1]["text"]["text"]
    # Échappement Slack : un titre ne peut pas notifier tout un canal.
    assert "<!channel>" not in section and "&lt;!channel&gt;" in section and "&amp; a voulu" in section
    assert "suspendu" in m["blocks"][3]["text"]["text"]
    assert "trafic de démonstration" in m["blocks"][5]["elements"][0]["text"]


def test_sans_webhook_rien_ne_part(client):
    iid = _incident_interne(client)
    assert _attendre(lambda: client.get("/api/alertes").json()["alertes"])
    r = client.get("/api/alertes").json()
    assert r["webhook_configure"] is False
    (alerte,) = r["alertes"]
    assert alerte["incident_id"] == iid and alerte["statut"] == "non_envoyee"
    assert alerte["message"]["blocks"][0]["text"]["text"] == f"Décision attendue : {iid}"


def test_alerte_recue_par_le_recepteur_demo(client, recepteur, monkeypatch):
    monkeypatch.setenv("DEDALE_WEBHOOK_URL", recepteur_demo.url_de(recepteur))
    iid = _incident_interne(client)
    assert _attendre(lambda: recepteur.recus)
    (message,) = recepteur.recus
    assert message["text"].startswith(f"Décision attendue sur {iid}")
    assert message["blocks"][4]["elements"][0]["url"] == f"http://console.test/?incident={iid}"
    # Sous le titre en gras : ce qui s'est passé, en phrases.
    titre, recit = message["blocks"][1]["text"]["text"].split("\n", 1)
    assert titre.startswith("*") and len(recit) > 20
    # Un événement de plus sur le même incident ne renvoie pas d'alerte.
    client.post("/api/evenements", json={"source": "interne", "surface": "outil", "type": "appel_outil",
                                         "session_id": "S-int", "outil": "lire_doc", "details": {}})
    time.sleep(0.2)
    assert len(recepteur.recus) == 1
    alerte = client.get("/api/alertes").json()["alertes"][0]
    assert alerte["statut"] == "envoyee" and alerte["code_http"] == 200
    assert "DÉCISION ATTENDUE" in recepteur_demo.formater(message)


def test_quota_par_minute(client, recepteur, monkeypatch):
    monkeypatch.setenv("DEDALE_WEBHOOK_URL", recepteur_demo.url_de(recepteur))
    monkeypatch.setenv("DEDALE_ALERTES_MAX_MINUTE", "1")
    _incident_interne(client, "S-a")
    _incident_interne(client, "S-b")
    assert _attendre(lambda: len(client.get("/api/alertes").json()["alertes"]) == 2)
    statuts = sorted(a["statut"] for a in client.get("/api/alertes").json()["alertes"])
    assert statuts == ["envoyee", "limitee"]
    assert len(recepteur.recus) == 1


def test_webhook_injoignable_ne_casse_rien(client, monkeypatch):
    monkeypatch.setenv("DEDALE_WEBHOOK_URL", "http://127.0.0.1:9/webhook")  # port fermé
    iid = _incident_interne(client)
    assert client.get(f"/api/incidents/{iid}").status_code == 200
    assert _attendre(lambda: client.get("/api/alertes").json()["alertes"])
    assert client.get("/api/alertes").json()["alertes"][0]["statut"] == "echec"
    monkeypatch.setenv("DEDALE_WEBHOOK_URL", "ftp://exemple.invalid/hook")
    alertes.historique.clear()
    _incident_interne(client, "S-c")
    assert _attendre(lambda: client.get("/api/alertes").json()["alertes"])
    assert client.get("/api/alertes").json()["alertes"][0]["statut"] == "configuration_invalide"
