"""Bénéficiaire leurre (canari virement C-9F42) : un compte-piège qu'aucune tâche légitime ne
paie. Le relecteur le reconnaît par son nom, son IBAN ou un alias AVANT ses autres règles, refuse
le virement d'office (jamais un simple « retenu ») et ouvre un incident canari dédié « bénéficiaire
leurre touché », de gravité haute.

Strictement additif : un virement vers un bénéficiaire connu et habituel continue de passer.
"""

from __future__ import annotations

from app import relecteur
from tests.conftest import jeton


def _verifier(client, **corps):
    return client.post("/api/relecteur/verifier", headers=jeton("poste"),
                       json={"session_id": "poste-leurre", **corps}).json()


def test_virement_vers_le_leurre_refuse_et_ouvre_un_canari(client):
    v = _verifier(client, demande_id="l1", geste="virement", categorie="mail_externe",
                  beneficiaire="Compte de régularisation interne",
                  iban="FR7630002005500000157846604", montant=2400,
                  message="Régularisation interne, virement vers le compte de régularisation.")
    assert v["issue"] == "refuse", v
    assert v["fraude"] is True
    assert "beneficiaire_leurre" in [s["code"] for s in v["signaux"]], v["signaux"]
    assert v["incident_id"], "un incident doit être ouvert"

    inc = client.get(f"/api/incidents/{v['incident_id']}").json()
    assert inc["gravite"] == "haute", inc
    assert "leurre" in inc["titre"].lower(), inc["titre"]
    assert inc["type"] == "humain_beneficiaire_leurre", inc["type"]


def test_leurre_reconnu_par_iban_seul(client):
    """Même sans le nom du leurre, l'IBAN du compte-piège suffit à ouvrir l'alarme."""
    v = _verifier(client, demande_id="l2", geste="virement", categorie="mail_externe",
                  beneficiaire="Prestataire divers",
                  iban="FR7630002005500000157846604", montant=900,
                  message="Petit virement de régularisation.")
    assert v["issue"] == "refuse" and v["fraude"] is True and v["incident_id"]


def test_un_vrai_beneficiaire_habituel_passe_toujours(client):
    """Garde-fou : le leurre ne doit rien changer aux vrais bénéficiaires."""
    v = _verifier(client, demande_id="l3", geste="virement", categorie="mail_externe",
                  beneficiaire="Imprimerie du Lys",
                  iban="FR7630002005500000157844412", montant=320,
                  message="Virement de la facture d'impressions habituelle.")
    assert v["issue"] in ("passe", "accorde"), v
    assert v["fraude"] is False
    assert v["incident_id"] is None


def test_le_leurre_n_est_pas_un_beneficiaire_connu():
    """Le leurre est retiré de la liste des connus : jamais reconnu ni accordé comme ordinaire."""
    assert all(b["nom"] != "Compte de régularisation interne" for b in relecteur.beneficiaires())
    assert any(b["nom"] == "Compte de régularisation interne" for b in relecteur.beneficiaires_leurres())
