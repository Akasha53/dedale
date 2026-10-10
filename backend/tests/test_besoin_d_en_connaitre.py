"""Besoin d'en connaître : deux espaces, deux identités.

- la console du SOC (analyste) lit des montants en tranche, ni bénéficiaire ni IBAN, sauf sur un
  signal de fraude, dans la vue détaillée, et cette consultation est notée au journal scellé ;
- l'espace de validation métier (validateur) lit le détail d'un geste retenu et le tranche ;
- chacun reçoit 403 chez l'autre.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app import besoin_d_en_connaitre as bdc
from app import relecteur
from app.main import app
from tests.conftest import BASE, evenement, horo, jeton


class _SansModele:
    """Le relecteur tranche par ses règles seules : le test ne dépend d'aucun modèle."""

    async def __call__(self, systeme, utilisateur, schema, delai):
        raise relecteur.ErreurModele("panne")


@pytest.fixture
def regles(monkeypatch):
    monkeypatch.setenv("DEDALE_RELECTEUR", "auto")
    relecteur.definir_modele(_SansModele())
    yield
    relecteur.definir_modele(None)


def _verifier(client, message, sid="poste-camille", did="v1", **extra):
    corps = {"demande_id": did, "session_id": sid, "geste": "virement", "categorie": "mail_externe",
             "message": message, **extra}
    r = client.post("/api/relecteur/verifier", json=corps, headers=jeton("poste"))
    assert r.status_code == 200, r.text
    return r.json()


def _paiement_d_agent(client, sid="S-paie"):
    """Un agent aux droits trop larges tente un paiement : refusé d'office, pas de fraude."""
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="entree_agent",
        details={"texte": "Résume mes mails.", "agent": "orbis-assistant",
                 "droits": {"tache": "resumer_mails", "jeton": ["mail:lire"]}}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="executer_paiement",
        details={"parametres": {"montant": 48500, "beneficiaire": "atelier-nord"}, "verdict": "refuse",
                 "violation_droits": {"outil": "executer_paiement", "scope_requis": "paiement:executer",
                                      "scopes_jeton": ["mail:lire"], "tache": "resumer_mails"}},
        horodatage=horo(BASE, 1)))
    return next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)


def _consultations(client, iid):
    detail = client.get(f"/api/incidents/{iid}", headers=jeton("analyste")).json()
    return [j for j in detail.get("journal_console", []) if j["acte"] == "consultation"]


# ------------------------------------------------------------------ le SOC sans signal de fraude
def test_soc_lit_une_tranche_ni_beneficiaire_ni_iban(client):
    iid = _paiement_d_agent(client)
    for r in (client.get("/api/incidents"), client.get(f"/api/incidents/{iid}"),
              client.get("/api/sessions/S-paie")):
        texte = json.dumps(r.json(), ensure_ascii=False)
        assert "48500" not in texte and "48 500" not in texte, r.url
        assert "Atelier Nord" not in texte and "6789" not in texte, r.url
    session = client.get("/api/sessions/S-paie").json()
    assert session["confidentialite"]["niveau"] == "minimise"
    vir = next(e["details"]["virement"] for e in client.get("/api/sessions/S-paie").json()["evenements"]
               if e["type"] == "appel_outil")
    assert vir["montant"] is None and vir["montant_tranche"] == "entre 10 et 50 k€"
    assert vir["beneficiaire"] == bdc.MASQUE_BENEFICIAIRE and vir["iban_masque"] == bdc.MASQUE_IBAN
    # Rien n'est ouvert, rien n'est noté.
    assert _consultations(client, iid) == []


def test_flux_temps_reel_minimise_pour_l_analyste(client):
    _paiement_d_agent(client)
    with client.websocket_connect("/ws", headers=jeton("analyste")) as ws:
        client.post("/api/evenements", json=evenement(
            session_id="S-paie", source="interne", surface="outil", type="appel_outil",
            outil="executer_paiement", details={"parametres": {"montant": 12000}, "verdict": "refuse"},
            horodatage=horo(BASE, 2)))
        for _ in range(6):
            message = ws.receive_json()
            texte = json.dumps(message, ensure_ascii=False)
            assert "12000" not in texte and "Atelier Nord" not in texte
            if message["type"] == "incident":
                break


# ------------------------------------------------------------------ le SOC sur un signal de fraude
def test_signal_de_fraude_ouvre_le_detail_et_journalise(client, regles):
    # Le salarié vient de passer outre une alerte de phishing, puis demande un virement.
    client.post("/api/evenements", json=evenement(
        source="humain", surface="poste", type="avertissement", session_id="poste-mac-eva",
        horodatage=datetime.now(timezone.utc).isoformat(),
        details={"categorie": "phishing", "choix": "continuer", "message": "Lien suspect."}))
    v = _verifier(client, "Virement de 48 500 € à Compta Express, nouveau RIB FR76 1111 2222 3333 4444 5555 0042.",
                  sid="poste-mac-eva", did="f1")
    assert v["fraude"] is True and v["incident_id"]
    iid = v["incident_id"]
    # La liste reste minimisée, même en fraude.
    liste = json.dumps(client.get("/api/incidents").json(), ensure_ascii=False)
    assert "48500" not in liste and "Compta Express" not in liste
    # La vue détaillée s'ouvre, le dit, et la consultation entre au journal scellé.
    detail = client.get(f"/api/incidents/{iid}").json()
    conf = detail["confidentialite"]
    assert conf["niveau"] == "en_clair" and conf["mention"].startswith("Détail visible : signal de fraude")
    assert conf["detail"]["montant_eur"] == 48500 and conf["detail"]["beneficiaire"] == "Compta Express"
    assert conf["detail"]["iban"] == "•••• 0042"
    notes = _consultations(client, iid)
    assert len(notes) == 1 and notes[0]["analyste"] == bdc.ANALYSTE_CONSULTATION
    assert notes[0]["motif"].startswith("Détail visible : signal de fraude")
    # Relire dans la minute ne note pas une deuxième consultation.
    client.get(f"/api/incidents/{iid}")
    assert len(_consultations(client, iid)) == 1
    # Le journal du dossier reste intact avec l'acte de consultation.
    assert client.get(f"/api/incidents/{iid}/verification").json()["statut"] in ("intacte", "non_persiste")


# ------------------------------------------------------------------ l'espace de validation métier
def test_le_validateur_voit_le_detail_et_tranche(client, regles):
    v = _verifier(client, "Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042.")
    assert v["issue"] == "retenu" and v["fraude"] is False and v["validation"] is True
    # La SOC ne voit rien de ce geste.
    assert client.get("/api/incidents").json()["incidents"] == []
    file = client.get("/api/validation/file", headers=jeton("validateur")).json()
    assert file["total"] == 1
    fiche = file["gestes"][0]
    assert fiche["id"] == "v1" and fiche["montant_eur"] == 3480 and fiche["titre"] == "Virement"
    assert fiche["beneficiaire"]["nom"] == "Atelier Nord" and fiche["beneficiaire"]["connu"] is True
    assert fiche["iban"].endswith("0042") and "1111" not in fiche["iban"]
    assert fiche["rib"] == "nouveau" and fiche["motif"].startswith("Ce RIB n'a jamais servi pour Atelier Nord")
    assert fiche["demandeur"] == {"nom": "Camille Martin", "service": "Finance"}
    # Aucune télémétrie de sécurité : ni score, ni URL, ni agent, ni modèle.
    texte = json.dumps(fiche, ensure_ascii=False).lower()
    for mot in ("score", "http", "hxxp", "agent", "haiku", "modele", "confiance", "signaux"):
        assert mot not in texte, mot
    assert client.get("/api/validation/gestes/v1", headers=jeton("validateur")).json()["id"] == "v1"
    # Motif et signature obligatoires.
    r = client.post("/api/validation/gestes/v1/decision", headers=jeton("validateur"),
                    json={"decision": "accorder", "validateur": "Claire Dubois"})
    assert r.status_code == 400
    r = client.post("/api/validation/gestes/v1/decision", headers=jeton("validateur"),
                    json={"decision": "accorder", "motif": "RIB confirmé par téléphone avec Atelier Nord.",
                          "validateur": "Claire Dubois", "qualite": "finance"})
    assert r.status_code == 200, r.text
    assert r.json()["statut"] == "accorde" and r.json()["decision"]["validateur"] == "Claire Dubois (finance)"
    file = client.get("/api/validation/file", headers=jeton("validateur")).json()
    assert file["total"] == 0 and file["traites"][0]["id"] == "v1"
    r = client.post("/api/validation/gestes/v1/decision", headers=jeton("validateur"),
                    json={"decision": "refuser", "motif": "Finalement non.", "validateur": "Claire Dubois"})
    assert r.status_code == 409
    # La SOC lit le poste : la décision métier n'y figure que par son sens.
    evs = client.get("/api/sessions/poste-camille", headers=jeton("analyste")).json()["evenements"]
    actes = [e for e in evs if e["type"] in bdc.ACTES_METIER]
    assert {e["type"] for e in actes} == {"validation_demandee", "validation_decidee"}
    texte = json.dumps(actes, ensure_ascii=False)
    for secret in ("3480", "Atelier Nord", "Claire", "téléphone", "0042"):
        assert secret not in texte, secret
    assert any(e["details"]["validation_metier"] == "confirmé par le responsable" for e in actes)


# ------------------------------------------------------------------ chacun chez soi
def test_validateur_refuse_sur_la_console_et_analyste_refuse_sur_la_validation(client, regles):
    _verifier(client, "Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042.")
    nu = TestClient(app)
    nu.event_hooks = {"request": [], "response": []}
    with nu:
        for chemin in ("/api/incidents", "/api/sessions", "/api/mesures", "/api/relecteur/file"):
            assert nu.get(chemin, headers=jeton("validateur")).status_code == 403, chemin
        decision = {"decision": "accorder", "motif": "Vu avec le fournisseur.", "validateur": "Marc"}
        for role in ("analyste", "poste", "passerelle"):
            r = nu.post("/api/validation/gestes/v1/decision", headers=jeton(role), json=decision)
            assert r.status_code == 403, role
            assert nu.get("/api/validation/file", headers=jeton(role)).status_code == 403, role
        assert nu.post("/api/validation/gestes/v1/decision", json=decision).status_code == 401
        file = nu.get("/api/validation/file", headers=jeton("validateur")).json()
        assert file["gestes"][0]["statut"] == "en_attente"


# ------------------------------------------------------------------ le texte
@pytest.mark.parametrize("brut, attendu", [
    ("Virement de 48 500 € à Atelier Nord.", "Virement de [entre 10 et 50 k€] à [bénéficiaire masqué]."),
    ("IBAN FR76 3000 4000 0500 0012 3456 789 demandé", "IBAN [IBAN masqué] demandé"),
    ("RIB enregistré •••• 6789", "RIB enregistré ••••"),
    ("12k EUR vers Cabinet Ferrand", "[entre 10 et 50 k€] vers [bénéficiaire masqué]"),
    ("1,2 M€ d'un coup", "[plus de 1 M€] d'un coup"),
    ("Règle : bloquer au-dessus de 10 000 €.", "Règle : bloquer au-dessus de 10 000 €."),
    ("Export de 40 fiches clients", "Export de 40 fiches clients"),
    ("sceau 3f2a9c00e4b7d1aa", "sceau 3f2a9c00e4b7d1aa"),
])
def test_masquer_texte(brut, attendu):
    bdc.vider()
    assert bdc.masquer_texte(brut, bdc._noms_metier()) == attendu


def test_tranches():
    assert [bdc.tranche(v) for v in (300, 3480, 48500, 75000, 380000, 2e6)] == [
        "moins de 1 k€", "entre 1 et 10 k€", "entre 10 et 50 k€", "entre 50 et 100 k€",
        "entre 100 et 500 k€", "plus de 1 M€"]
