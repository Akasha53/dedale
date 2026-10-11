"""Fraude au président lue dans le geste lui-même, sans mail avant (retour du RSSI de Ferral).

380 000 € urgents et confidentiels vers Hong Kong, « demandés par le PDG » : un dossier s'ouvre au
SOC, montant en tranche et bénéficiaire masqué, le relecteur refuse, et la finance voit le geste
retenu sans pouvoir l'accorder. Un gros virement légitime vers un fournisseur connu ne déclenche rien.
"""

from __future__ import annotations

import json

import pytest

from app import relecteur
from tests.conftest import jeton
from tests.test_relecteur import PANNE, FauxModele, _calme, _relecteur_actif  # noqa: F401

PDG = ("Virement urgent et confidentiel de 380 000 € à Golden Bridge Trading Ltd, Hong Kong, "
       "IBAN HK12 3456 7890 1234 5678, demandé par le PDG pour une acquisition.")


def _verifier(client, message, sid="poste-ferral-compta-03", did="p1"):
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": did, "session_id": sid, "geste": "virement", "categorie": "mail_externe", "message": message})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("horaire", [False, True])
def test_fraude_au_president_sans_mail_ouvre_un_dossier_soc(client, monkeypatch, horaire):
    monkeypatch.setattr(relecteur, "horaire_inhabituel", lambda h: horaire)
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    v = _verifier(client, PDG)
    codes = [s["code"] for s in v["signaux"]]
    assert v["fraude"] is True and "fraude_president" in codes, v
    assert v["issue"] == "refuse" and v["incident_id"]
    raison = next(s["raison"] for s in v["signaux"] if s["code"] == "fraude_president")
    for marqueur in ("bénéficiaire nouveau", "étranger", "urgence", "confidentialité", "dirigeant cité"):
        assert marqueur in raison
    _calme()
    # SOC : le dossier existe, la liste ne porte ni montant exact ni bénéficiaire.
    soc = client.get("/api/incidents", headers=jeton("analyste")).json()["incidents"]
    assert [i["id"] for i in soc] == [v["incident_id"]]
    brut = json.dumps(soc, ensure_ascii=False)
    assert not any(x in brut for x in ("380 000", "380000", "380\u202f000", "Golden Bridge", "HK12"))
    sess = client.get(f"/api/sessions/{soc[0]['session_id']}").json()
    demande = next(e for e in sess["evenements"] if (e.get("details") or {}).get("quatre_yeux") == "demande")
    assert demande["details"]["montant_tranche"] == "plus de 10 000 €"
    # Finance : le geste est là, retenu par la sécurité, avec le motif ; pas de bouton Accorder.
    file = client.get("/api/validation/file", headers=jeton("validateur")).json()
    fiche = next(f for f in file["gestes"] if f["id"] == "p1")
    assert fiche["statut"] == "retenu_soc"
    assert "signes d'une fraude au président" in fiche["motif"].lower()
    r = client.post("/api/validation/gestes/p1/decision", headers=jeton("validateur"),
                    json={"decision": "accorder", "motif": "Le PDG a insisté.", "validateur": "Claire Dubois",
                          "qualite": "finance"})
    assert r.status_code == 409
    r = client.post("/api/validation/relecteur/p1", headers=jeton("validateur"),
                    json={"verdict": "accorde", "validateur": "claire", "motif": "Le PDG a insisté."})
    assert r.status_code == 400


def test_fraude_au_president_le_modele_ne_peut_pas_l_accorder(client, monkeypatch):
    monkeypatch.setattr(relecteur, "horaire_inhabituel", lambda h: False)
    relecteur.definir_modele(FauxModele(geste={"decision": "accorde", "motif_salarie": "Virement validé.",
                                               "motif_soc": "Acquisition annoncée.", "confiance": 0.9}))
    v = _verifier(client, PDG.replace("380 000", "8 000"), did="p2")
    assert v["fraude"] is True and v["issue"] in ("refuse", "retenu") and v["incident_id"]


@pytest.mark.parametrize("message", [
    # Fournisseur connu, RIB habituel, dans ses usages, même pressé par la direction.
    "Virement urgent de 4 900 € à Atelier Nord, IBAN FR76 3000 4000 0500 0012 3456 6789, demandé par la direction.",
    # Gros virement à un fournisseur connu, RIB habituel : la finance confirme, la SOC n'en voit rien.
    "Virement de 48 000 € à Atelier Nord, IBAN FR76 3000 4000 0500 0012 3456 6789, renouvellement du parc.",
])
def test_gros_virement_legitime_vers_un_connu_ne_declenche_pas(client, monkeypatch, message):
    monkeypatch.setattr(relecteur, "horaire_inhabituel", lambda h: True)  # pire cas : la nuit
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    v = _verifier(client, message, did="l1")
    assert v["fraude"] is False and v["incident_id"] is None, v
    assert "fraude_president" not in [s["code"] for s in v["signaux"]]
    assert client.get("/api/incidents", headers=jeton("analyste")).json()["incidents"] == []
