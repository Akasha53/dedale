"""Un même enchaînement n'ouvre qu'un incident (répétition générale, point 6).

Le salarié passe outre une alerte de phishing, puis lance le virement que le mail réclame : le
geste rejoint le dossier de l'alerte au lieu d'en ouvrir un second.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import relecteur
from tests.conftest import evenement, jeton
from tests.test_relecteur import PANNE, FauxModele, _calme, _relecteur_actif  # noqa: F401


def _continuer(client, sid):
    client.post("/api/evenements", json=evenement(
        source="humain", surface="poste", type="avertissement", session_id=sid,
        horodatage=datetime.now(timezone.utc).isoformat(),
        details={"categorie": "phishing", "choix": "continuer", "message": "Lien suspect.", "gravite": "haute"}))


def _verifier(client, sid, did, **extra):
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": did, "session_id": sid, "geste": "virement", "categorie": "mail_externe",
        "message": "Virement urgent de 48 500 € à Compta Express, IBAN FR76 1111 2222 3333 4444 5555 0042.",
        **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_continuer_puis_virement_un_seul_incident(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "poste-repet-b")
    avant = client.get("/api/incidents").json()["incidents"]
    assert len(avant) == 1
    v = _verifier(client, "poste-repet-b", "u1")
    assert v["fraude"] is True and v["issue"] == "refuse"
    _calme()
    incidents = client.get("/api/incidents").json()["incidents"]
    assert [i["id"] for i in incidents] == [avant[0]["id"]] == [v["incident_id"]]
    inc = client.get(f"/api/incidents/{v['incident_id']}").json()
    assert inc["type"] == "humain_phishing" and inc["gravite"] == "critique"
    assert inc["relecteur"]["decision"] == "refuse"
    assert client.get("/api/relecteur/demandes/u1", headers=jeton("poste")).json()["statut"] == "tranchee"


def test_alerte_dans_la_boite_mail_citee_un_seul_incident(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "mail-9001")
    v = _verifier(client, "poste-mac-lea", "u2", mail_id="9001")
    assert v["fraude"] is True
    _calme()
    assert [i["session_id"] for i in client.get("/api/incidents").json()["incidents"]] == ["mail-9001"]


def test_sans_alerte_le_geste_ouvre_son_propre_dossier(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "poste-autre")
    # Aucune alerte sur ce poste-là ; urgence, bénéficiaire nouveau et montant : fraude au président.
    v = _verifier(client, "poste-ferral-compta-03", "u3")
    assert v["fraude"] is True and v["incident_id"]
    _calme()
    sessions = {i["session_id"] for i in client.get("/api/incidents").json()["incidents"]}
    assert sessions == {"poste-autre", "poste-ferral-compta-03-4y-u3"}
