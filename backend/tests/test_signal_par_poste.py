"""Un signal de fraude reste attaché au poste qui l'a produit (retour du RSSI de Ferral).

Un « Continuer » sur un phishing dans une boîte `mail-*` ne fait plus traiter en fraude les
virements des autres postes. La boîte noire et les mesures ne prêtent un « Continuer quand même »
qu'au salarié qui a vraiment vu l'alerte et continué.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import identites, relecteur
from tests.conftest import evenement, jeton
from tests.test_relecteur import PANNE, FauxModele, _calme, _relecteur_actif  # noqa: F401

LYS = "Virement de 320 € à Imprimerie du Lys, IBAN FR76 3000 4000 0500 0012 3456 4412."
COMPTA = "Virement de 2 400 € à Compta Express, IBAN FR76 1111 2222 3333 4444 5555 0042."


def _continuer(client, sid, **details):
    r = client.post("/api/evenements", json=evenement(
        source="humain", surface="poste", type="avertissement", session_id=sid,
        horodatage=datetime.now(timezone.utc).isoformat(),
        details={"categorie": "phishing", "choix": "continuer", "message": "Lien suspect.", **details}))
    assert r.status_code == 200


def _verifier(client, message, sid, did, **extra):
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": did, "session_id": sid, "geste": "virement", "categorie": "mail_externe",
        "message": message, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_un_continuer_dans_une_boite_mail_ne_touche_pas_les_autres_postes(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "mail-demo-4471")
    v = _verifier(client, LYS, "poste-ferral-usine2-11", "a1")
    assert v["fraude"] is False and v["incident_id"] is None, v
    assert "apres_alerte" not in [s["code"] for s in v["signaux"]]
    v = _verifier(client, COMPTA, "poste-ferral-siege-07", "a2")
    assert v["fraude"] is False and v["incident_id"] is None and v["issue"] == "retenu"


def test_le_signal_suit_le_salarie_qui_a_vu_l_alerte(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "poste-ferral-compta-04")
    v = _verifier(client, COMPTA, "poste-ferral-compta-04", "b1")
    assert v["fraude"] is True and v["incident_id"]
    assert "apres_alerte" in [s["code"] for s in v["signaux"]]
    # Un autre poste, au même moment : rien.
    autre = _verifier(client, COMPTA, "poste-ferral-compta-05", "b2")
    assert autre["fraude"] is False and autre["incident_id"] is None
    # Le mail cité par le geste compte pour ce poste-là, et pour lui seul.
    _continuer(client, "mail-7788")
    lie = _verifier(client, COMPTA, "poste-ferral-compta-06", "b3", mail_id="7788")
    assert lie["fraude"] is True
    # Même poste, même salarié : un seul pseudonyme pour l'alerte et pour le virement.
    _calme()
    inc = client.get(f"/api/incidents/{v['incident_id']}").json()
    assert identites.identite(inc["session_id"])["pseudonyme"] == identites.identite("poste-ferral-compta-04")["pseudonyme"]


def test_la_boite_noire_ne_prete_pas_un_continuer_jamais_clique(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    _continuer(client, "poste-ferral-compta-04")  # un vrai « Continuer »
    v = _verifier(client, COMPTA, "poste-ferral-compta-04", "c1")
    assert v["fraude"] is True and v["incident_id"]
    # Fraude lue dans le geste seul, sans aucune alerte avant sur ce poste.
    pdg = _verifier(client, "Virement urgent et confidentiel de 380 000 € à Golden Bridge Trading Ltd, Hong Kong, "
                            "IBAN HK12 3456 7890 1234 5678, demandé par le PDG.", "poste-ferral-compta-03", "c2")
    assert pdg["fraude"] is True and pdg["incident_id"]
    _calme()
    # Le virement rejoint le dossier de la vraie alerte : un seul « Continuer », celui du salarié.
    inc = client.get(f"/api/incidents/{v['incident_id']}").json()
    assert [e["etape"] for e in inc["chaine"]].count("choix") == 1
    # Le virement lu seul, sans alerte avant : aucun choix prêté au salarié.
    inc = client.get(f"/api/incidents/{pdg['incident_id']}").json()
    etapes = [e["etape"] for e in inc["chaine"]]
    assert "choix" not in etapes and "avertissement" not in etapes, etapes
    assert "continuer" not in " ".join(e.get("detail") or "" for e in inc["chaine"])
    assert "passé outre" not in (inc.get("resume") or "")
    sess = client.get(f"/api/sessions/{client.get(f'/api/incidents/{pdg['incident_id']}').json()['session_id']}").json()
    assert all((e.get("details") or {}).get("choix") is None for e in sess["evenements"])
    # Mesures : un seul « Continuer » simulé, un seul compté.
    m = client.get("/api/mesures").json()
    assert m["gestes_humains"]["passes_outre"] == 1, m["gestes_humains"]
