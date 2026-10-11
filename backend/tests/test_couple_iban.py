"""Un bénéficiaire connu, c'est un couple bénéficiaire et IBAN (retour de la testeuse du cabinet comptable).

- L'associé valide une fois « Bureau Vallée » sans IBAN : 320 € vers un compte lituanien ne
  passent plus sans signal ensuite.
- Une demande sans IBAN est retenue, motif « IBAN absent », même pour un fournisseur de la liste.
- Un RIB client confirmé par téléphone entre dans la mémoire : le mois suivant, le même couple
  passe sans être retenu ; un autre IBAN pour ce client est retenu.
"""

from __future__ import annotations

from app import relecteur
from tests.conftest import jeton
from tests.test_relecteur import PANNE, FauxModele, _relecteur_actif  # noqa: F401


def _verifier(client, message, did, sid="poste-cabinet-02"):
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": did, "session_id": sid, "geste": "virement", "categorie": "mail_externe", "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def _confirmer(client, did, qualite="responsable", motif="Fournisseur validé par l'associé."):
    r = client.post(f"/api/validation/gestes/{did}/decision", headers=jeton("validateur"),
                    json={"decision": "accorder", "motif": motif, "validateur": "Hélène Morel", "qualite": qualite})
    assert r.status_code == 200, r.text


def _codes(v):
    return [s["code"] for s in v["signaux"]]


def test_un_accord_sans_iban_ne_vaut_pour_aucun_compte(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    v = _verifier(client, "Virement de 320 € à Bureau Vallée.", "bv1")
    assert v["issue"] == "retenu" and "iban_absent" in _codes(v) and v["motif_salarie"].startswith("IBAN absent")
    _confirmer(client, "bv1")
    # Le mois suivant, même nom, compte lituanien : signal, retenu.
    v = _verifier(client, "Virement de 320 € à Bureau Vallée, IBAN LT12 1000 0111 0100 1000.", "bv2")
    assert v["issue"] == "retenu" and v["signaux"], v
    # Fournisseur de la liste, mêmes quatre derniers chiffres, mais un IBAN lituanien : pays inhabituel.
    v = _verifier(client, "Virement de 320 € à Imprimerie du Lys, IBAN LT12 1000 0111 0100 4412.", "lys-lt")
    assert v["issue"] == "retenu" and "iban_pays" in _codes(v) and "rib_change" in _codes(v), v


def test_demande_sans_iban_retenue_iban_absent(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    v = _verifier(client, "Virement de 320 € à Imprimerie du Lys.", "sans")
    assert v["issue"] == "retenu" and v["fraude"] is False and v["validation"] is True
    assert "iban_absent" in _codes(v) and v["motif_salarie"].startswith("IBAN absent")
    fiche = client.get("/api/validation/gestes/sans", headers=jeton("validateur")).json()
    assert fiche["motif"].startswith("IBAN absent") and fiche["iban"] is None and fiche["rib"] == "non_precise"
    # Avec l'IBAN enregistré, le même virement passe sans pop-up.
    v = _verifier(client, "Virement de 320 € à Imprimerie du Lys, IBAN FR76 3000 4000 0500 0012 3456 4412.", "avec")
    assert v["issue"] == "passe"


def test_couple_confirme_par_telephone_passe_le_mois_suivant(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    nouveau = "Virement de 890 € au Cabinet Ferrand, IBAN FR76 1234 5678 9012 3456 7788 9911."
    v = _verifier(client, nouveau, "cf1")
    assert v["issue"] == "retenu" and "rib_change" in _codes(v)
    _confirmer(client, "cf1", qualite="finance", motif="RIB confirmé par téléphone avec le client.")
    entree = client.get("/api/relecteur/memoire").json()["entrees"][0]
    assert entree["verdict"] == "accorde" and entree["rib"] and entree["iban_pays"] == "FR"
    assert "9911" not in str(entree)  # l'IBAN n'entre dans la mémoire que haché
    # Le mois suivant, le même couple : aucun signal, aucune pop-up.
    v = _verifier(client, nouveau.replace("890", "910"), "cf2", sid="poste-cabinet-04")
    assert v["issue"] == "passe" and v["signaux"] == [], v
    # Un autre IBAN pour ce client reste un signal, quel que soit le texte.
    v = _verifier(client, "Virement de 890 € au Cabinet Ferrand, IBAN FR76 9999 8888 7777 6666 5555 4433.", "cf3")
    assert v["issue"] == "retenu" and "rib_change" in _codes(v)


def test_couple_hors_liste_confirme_avec_iban(client):
    relecteur.definir_modele(FauxModele(erreur=PANNE))
    msg = "Virement de 320 € à Bureau Vallée, IBAN FR76 2004 1010 0505 0001 3M02 606."
    assert _verifier(client, msg, "h1")["issue"] == "retenu"
    _confirmer(client, "h1")
    assert _verifier(client, msg, "h2")["issue"] == "passe"
    v = _verifier(client, "Virement de 320 € à Bureau Vallée, IBAN LT12 1000 0111 0100 1000.", "h3")
    assert v["issue"] == "retenu" and "rib_change" in _codes(v) and "iban_pays" in _codes(v), v
