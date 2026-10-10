"""Comportement anormal : habitude par agent, puis alerte quand l'agent en sort."""

from __future__ import annotations

from datetime import timedelta

from app import anomalies
from app.store import store
from tests.conftest import BASE, evenement

AGENT = "orbis-rapprochement"


def _appel(client, sid, t, outil, **params):
    return client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil=outil,
        horodatage=(BASE + timedelta(seconds=t)).isoformat(),
        details={"agent": AGENT, "parametres": params, "verdict": "autorise"}))


def _habitude(client, minutes=12):
    """Trois appels par minute : un relevé de 40 lignes, un résumé, un rapport interne."""
    for m in range(minutes):
        sid = f"S-hab-{m // 4}"
        _appel(client, sid, m * 60 + 1, "lire_releve", lignes=38 + (m % 5))
        _appel(client, sid, m * 60 + 20, "resumer")
        _appel(client, sid, m * 60 + 40, "envoyer_rapport", destinataire="compta@orbispay.example")
    return minutes * 60 + 600  # départ de la suite, dix minutes plus tard


def test_l_habitude_ne_suffit_pas_avant_vingt_appels(client):
    for i in range(15):
        _appel(client, "S-tot", i, "lire_releve", lignes=40)
    _appel(client, "S-tot", 16, "exporter_contacts")
    assert client.get("/api/incidents").json()["incidents"] == []
    h = client.get(f"/api/agents/{AGENT}").json()["habitude"]
    assert h["prete"] is False


def test_rythme_normal_sans_alerte(client):
    _habitude(client)
    assert client.get("/api/incidents").json()["incidents"] == []
    h = client.get(f"/api/agents/{AGENT}").json()["habitude"]
    assert h["prete"] is True
    assert h["appels_par_minute"] == 3.0
    assert set(h["outils"]) == {"lire_releve", "resumer", "envoyer_rapport"}
    assert 38 <= h["volume_moyen"]["lire_releve"] <= 42


def test_pic_d_appels(client):
    t = _habitude(client)
    for i in range(25):
        _appel(client, "S-pic", t + i, "lire_releve", lignes=40)
    incs = client.get("/api/incidents").json()["incidents"]
    assert len(incs) == 1
    inc = incs[0]
    assert inc["type"] == "interne_anomalie"
    assert inc["gravite"] == "moyenne"
    assert inc["etat"] == "active"  # une alerte ne coupe pas l'agent
    assert "pic d'appels" in inc["titre"]
    maillons = [e for e in inc["chaine"] if e["etape"] == "anomalie"]
    assert len(maillons) == 1  # une alerte par session, pas une par appel
    assert maillons[0]["detail"].startswith("15 appels en une minute, contre 3 par minute")


def test_outil_jamais_utilise(client):
    t = _habitude(client)
    _appel(client, "S-neuf", t, "exporter_contacts")
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_anomalie"
    assert inc["gravite"] == "moyenne"  # outil qui fait sortir des données
    detail = next(e for e in inc["chaine"] if e["etape"] == "anomalie")["detail"]
    assert "outil exporter_contacts jamais utilisé" in detail


def test_outil_inhabituel_anodin_reste_faible(client):
    t = _habitude(client)
    _appel(client, "S-doc", t, "chercher_document", requete="facture")
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["gravite"] == "faible"


def test_volume_lu_multiplie_par_dix(client):
    t = _habitude(client)
    _appel(client, "S-vol", t, "lire_releve", lignes=600)
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_anomalie" and inc["gravite"] == "moyenne"
    detail = next(e for e in inc["chaine"] if e["etape"] == "anomalie")["detail"]
    assert detail.startswith("600 éléments demandés à lire_releve en un appel, contre 40 d'habitude")
    # L'appel anormal n'entre pas dans l'habitude.
    h = client.get(f"/api/agents/{AGENT}").json()["habitude"]
    assert h["volume_moyen"]["lire_releve"] < 45


def test_champ_anomalie_venu_de_dehors_ignore(client):
    client.post("/api/evenements", json=evenement(
        session_id="S-faux", source="interne", surface="outil", type="appel_outil", outil="lire_mail",
        details={"agent": AGENT, "anomalie": {"code": "pic_appels", "raison": "inventé"}}))
    assert client.get("/api/incidents").json()["incidents"] == []


def test_habitude_reconstruite_depuis_le_journal(client):
    t = _habitude(client)
    _appel(client, "S-vol", t, "lire_releve", lignes=600)
    avant = client.get(f"/api/agents/{AGENT}").json()["habitude"]
    anomalies.vider(store)  # comme un redémarrage : l'état se relit dans le journal
    apres = client.get(f"/api/agents/{AGENT}").json()["habitude"]
    assert apres == avant
    # Après relecture, la même alerte ne revient pas une seconde fois.
    _appel(client, "S-vol", t + 5, "lire_releve", lignes=700)
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert len([e for e in inc["chaine"] if e["etape"] == "anomalie"]) == 1
