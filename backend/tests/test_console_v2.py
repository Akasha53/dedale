"""Retours des testeurs (10 octobre) : pseudonymes, actes scellés, signalement, virement, conseil."""

from __future__ import annotations

import json
import re

from app.store import store
from tests.conftest import BASE, evenement, horo

SID = "poste-camille-001"


def _poste_phishing(client, sid=SID, quatre_yeux=False):
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="humain", surface="poste", type="contexte",
        details={"contexte": "Camille ouvre un mail « votre accès expire »"}, horodatage=horo(BASE, 0)))
    details = {"categorie": "phishing", "choix": "continuer", "contexte": "mail reçu",
               "lien": "http://orbispay-verification.net/reactivation?u=camille",
               "message": "Bonjour Camille, ce lien imite Orbis Pay."}
    if quatre_yeux:
        details |= {"quatre_yeux": "demande", "demande_id": "q1", "delai_s": 90, "gravite": "critique"}
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="humain", surface="poste", type="avertissement",
        details=details, horodatage=horo(BASE, 2)))
    return next(i for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)


def _sans_session_id(d):
    d = json.loads(json.dumps(d))
    d.pop("session_id", None)
    if isinstance(d.get("session"), dict):
        d["session"].pop("id", None)
    return json.dumps(d, ensure_ascii=False)


def test_salarie_pseudonymise_partout(client):
    inc = _poste_phishing(client)
    detail = client.get(f"/api/incidents/{inc['id']}").json()
    texte = _sans_session_id(detail)
    assert not re.search(r"camille|martin", texte, re.IGNORECASE)
    assert "?u=" not in texte
    ident = detail["identite"]
    assert re.fullmatch(r"Salarié \d{4}", ident["pseudonyme"])
    assert ident["libelle"] == f"{ident['pseudonyme']} · Finance"
    assert detail["contexte_humain"] == "mail reçu"
    session = client.get(f"/api/sessions/{SID}").json()
    evts = json.dumps([{k: v for k, v in e.items() if k != "session_id"} for e in session["evenements"]],
                      ensure_ascii=False)
    assert not re.search(r"camille", evts, re.IGNORECASE)
    liste = [s for s in client.get("/api/sessions").json()["sessions"] if s["id"] == SID][0]
    assert liste["identite"]["pseudonyme"] == ident["pseudonyme"]


def test_reveler_identite_motif_obligatoire_et_scelle(client):
    inc = _poste_phishing(client)
    r = client.post(f"/api/incidents/{inc['id']}/identite", json={"motif": "", "analyste": "karim"})
    assert r.status_code == 400
    r = client.post(f"/api/incidents/{inc['id']}/identite",
                    json={"motif": "Réinitialiser son accès VPN", "analyste": "karim"})
    assert r.status_code == 200
    rep = r.json()
    assert rep["nom"] == "Camille Martin" and rep["service"] == "Finance"
    detail = client.get(f"/api/incidents/{inc['id']}").json()
    rev = detail["identite"]["revelations"]
    assert rev and rev[0]["analyste"] == "karim" and "VPN" in rev[0]["motif"]
    # Le journal garde l'acte, jamais le nom.
    session = client.get(f"/api/sessions/{SID}").json()
    acte = [e for e in session["evenements"] if e["type"] == "console"][-1]
    assert acte["sceau"] and "Martin" not in json.dumps(acte, ensure_ascii=False)
    assert client.get(f"/api/incidents/{inc['id']}/verification").json()["statut"] == "intacte"


def test_remediations_simulees_et_journalisees(client):
    inc = _poste_phishing(client)
    for action in ("reinitialiser_mot_de_passe", "fermer_sessions", "bloquer_domaine"):
        r = client.post(f"/api/incidents/{inc['id']}/remediation", json={"action": action, "analyste": "karim"})
        assert r.status_code == 200, r.text
        assert r.json()["simulation"] is True
    assert r.json()["domaine"] == "orbispay-verification[.]net"
    doublon = client.post(f"/api/incidents/{inc['id']}/remediation",
                          json={"action": "fermer_sessions", "analyste": "karim"})
    assert doublon.status_code == 400
    journal = client.get(f"/api/incidents/{inc['id']}").json()["journal_console"]
    assert [j["action"] for j in journal] == ["reinitialiser_mot_de_passe", "fermer_sessions", "bloquer_domaine"]


def test_decision_avec_motif_et_quatre_yeux(client):
    inc = _poste_phishing(client, quatre_yeux=True)
    assert client.get(f"/api/incidents/{inc['id']}").json()["quatre_yeux"]["delai_s"] == 90
    r = client.post(f"/api/incidents/{inc['id']}/decision",
                    json={"action": "refuser", "analyste": "karim", "motif": "lien frauduleux"})
    assert r.status_code == 200
    detail = r.json()
    assert detail["statut"] == "clos" and detail["decisions"][-1]["action"] == "refuser"
    note = detail["journal_console"][-1]
    assert note["acte"] == "decision" and note["motif"] == "lien frauduleux"
    # Sans demande de quatre yeux, « accorder » n'a pas de sens.
    autre = _poste_phishing(client, sid="poste-camille-002")
    assert client.post(f"/api/incidents/{autre['id']}/decision",
                       json={"action": "accorder", "analyste": "karim"}).status_code == 400


def test_signalement_ouvre_un_dossier(client):
    client.post("/api/evenements", json=evenement(
        session_id="poste-mac-signalement-M1", source="humain", surface="poste", type="signalement",
        details={"origine": "app-mac", "mail_id": "M1", "message": "Mail signalé par le salarié : « Facture »",
                 "cible": "compta@fournisseur-nord.example", "verdict_analyseur": "sur",
                 "document_source": {"type": "mail", "titre": "Facture", "expediteur": "compta@fournisseur-nord.example",
                                     "destinataire": "camille.martin@orbispay.example", "corps": "Bonjour Camille"}},
        horodatage=horo(BASE, 0)))
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "humain_signalement" and inc["contexte_humain"] == "signalement"
    assert [m["phase"] for m in inc["chaine"]] == ["contexte", "signalement"]
    synth = client.get(f"/api/incidents/{inc['id']}/synthese").json()
    assert synth["decision_recommandee"]["action"] == "clore"
    assert "jugé sûr" in synth["texte"]
    assert client.get("/api/mesures").json()["gestes_humains"]["signalements"] == 1


def test_virement_lisible_et_iban_masque(client):
    sid = "S-paie"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="entree_agent",
        details={"texte": "Résume mes mails.", "agent": "orbis-assistant",
                 "droits": {"tache": "resumer_mails", "jeton": ["mail:lire"]}}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="executer_paiement",
        details={"parametres": {}, "verdict": "refuse",
                 "violation_droits": {"outil": "executer_paiement", "scope_requis": "paiement:executer",
                                      "scopes_jeton": ["mail:lire"], "tache": "resumer_mails"}},
        horodatage=horo(BASE, 1)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="riposte", outil="executer_paiement",
        details={"action": "bloquer_hors_scope", "scope_requis": "paiement:executer", "jeton_revoque": True},
        horodatage=horo(BASE, 1.01)))
    # Le backend lit le virement en entier…
    brut = next(e["details"]["virement"] for e in store.evenements.values()
                if e["outil"] == "executer_paiement" and e["type"] == "appel_outil")
    assert brut["montant"] == 3480.0 and brut["beneficiaire"] == "Atelier Nord"
    assert re.fullmatch(r"FR76 •••• •••• \d{4}", brut["iban_masque"])
    # …mais la console du SOC n'a pas besoin d'en connaître le détail : sans signal de fraude,
    # elle lit une tranche, ni le bénéficiaire ni l'IBAN (besoin_d_en_connaitre.py).
    evs = client.get(f"/api/sessions/{sid}").json()["evenements"]
    vir = next(e["details"]["virement"] for e in evs if e["outil"] == "executer_paiement" and e["type"] == "appel_outil")
    assert vir["montant"] is None and vir["montant_tranche"] == "entre 1 et 10 k€"
    assert vir["beneficiaire"] == "[bénéficiaire masqué]" and vir["iban_masque"] == "[IBAN masqué]"
    assert vir["complete_par_demo"] is True
    # Refus d'office : le conseil suit l'état et propose de clore.
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    dec = client.get(f"/api/incidents/{iid}/synthese").json()["decision_recommandee"]
    assert dec["action"] == "clore" and dec["dossier_ferme"] is False


def test_inventaire_porte_un_proprietaire(client):
    inv = client.get("/api/agents").json()["inventaire"]
    assert {a["id"]: a["proprietaire"] for a in inv}["orbis-rapprochement"] == "Direction financière"


def test_quatre_yeux_conseille_de_refuser(client):
    inc = _poste_phishing(client, quatre_yeux=True)
    dec = client.get(f"/api/incidents/{inc['id']}/synthese").json()["decision_recommandee"]
    assert dec["action"] == "refuser" and "accorder" in dec["actions_possibles"]


def test_prenom_cite_suffit_a_pseudonymiser(client):
    """Une session sans préfixe nominatif (démo jury) : le prénom cité suffit à la masquer."""
    inc = _poste_phishing(client, sid="jury-215301-ab12-poste")
    detail = client.get(f"/api/incidents/{inc['id']}").json()
    assert not re.search(r"camille", _sans_session_id(detail), re.IGNORECASE)
    assert detail["identite"]["service"] == "Finance"


def test_telechargement_garde_a_son_titre_et_sa_phrase(client):
    sha = "a3f2c19d4b70e8856cba9c0d11e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0"
    client.post("/api/evenements", json=evenement(
        session_id=f"poste-mac-telechargement-{sha[:12]}", source="humain", surface="poste",
        type="avertissement", user_agent="dedale-mac/0.2", horodatage=horo(BASE, 0),
        details={"origine": "app-mac", "contexte": "telechargement", "categorie": "phishing",
                 "choix": "continuer", "choix_poste": "garder", "type_fichier": "application",
                 "motifs": ["double_extension", "application"], "provenance": "mail",
                 "domaine": "cdn.factures-orbis.example", "cible": "cdn.factures-orbis.example",
                 "sha256": sha, "gravite": "haute",
                 "message": "Ce fichier vient de cdn.factures-orbis.example et peut lancer un programme."}))
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["titre"].startswith("Fichier à risque gardé par le salarié")
    assert inc["contexte_humain"] == "telechargement"
    action = next(m for m in inc["chaine"] if m["phase"] == "action_risquee")
    assert "un programme venu de cdn.factures-orbis.example" in action["detail"] and sha[:12] in action["detail"]
    synth = client.get(f"/api/incidents/{inc['id']}/synthese").json()
    assert synth["phrases"][0]["texte"].startswith("Un programme a été téléchargé depuis cdn.factures-orbis.example")
    assert "gardé le fichier" in synth["texte"]
    assert synth["decision_recommandee"]["action"] == "clore"
