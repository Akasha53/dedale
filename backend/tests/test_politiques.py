"""Règles écrites en français par le SOC : analyse, validation humaine, application."""

from __future__ import annotations

import pytest

from app import politiques
from tests.conftest import BASE, evenement, horo

PHRASE_TRI = "L'agent de tri ne doit jamais envoyer de mail hors d'Orbis Pay"


@pytest.mark.parametrize("phrase, agent, sauf, action, condition, effet", [
    (PHRASE_TRI, "orbis-assistant", None, "envoyer", "destinataire_externe", "bloquer"),
    ("Aucun agent ne lit le coffre en dehors des heures ouvrées.", "*", None, "lire_coffre",
     "hors_heures", "bloquer"),
    ("L'agent de rapprochement n'exporte jamais plus de 50 lignes.", "orbis-rapprochement", None,
     "exporter", "plafond", "bloquer"),
    ("Aucun agent ne doit appeler d'outil MCP externe.", "*", None, "outil_mcp", "toujours", "bloquer"),
    ("L'agent de support ne répond jamais aux clients entre 22h et 7h.", "orbis-support", None,
     "envoyer", "plage", "bloquer"),
    ("Aucun agent ne fait de virement le week-end.", "*", None, "virement", "week_end", "bloquer"),
    ("L'agent de rapprochement ne fait jamais de virement de plus de 1 000 €.", "orbis-rapprochement",
     None, "virement", "montant_max", "bloquer"),
    ("L'agent de rapprochement doit demander une validation avant tout virement.",
     "orbis-rapprochement", None, "virement", "toujours", "retenir"),
    ("Préviens-moi quand l'agent de support exporte des contacts.", "orbis-support", None,
     "exporter", "toujours", "alerter"),
    ("Seul l'agent de rapprochement peut faire des virements.", "*", "orbis-rapprochement",
     "virement", "toujours", "bloquer"),
    ("L'agent de tri ne lit le coffre que pendant les heures ouvrées.", "orbis-assistant", None,
     "lire_coffre", "hors_heures", "bloquer"),
    ("L'agent de support n'écrit jamais dans sa mémoire.", "orbis-support", None,
     "ecrire_memoire", "toujours", "bloquer"),
])
def test_formes_reconnues(phrase, agent, sauf, action, condition, effet):
    a = politiques.analyser(phrase)
    assert a["comprise"], a
    r = a["regle"]
    assert (r["agent"], r["sauf"], r["action"], r["condition"]["type"], r["effet"]) == (
        agent, sauf, action, condition, effet)
    assert a["texte"].startswith("Voilà ce que j'ai compris : ")
    assert a["texte"].endswith("Activer ?")


def test_exemples_documentes_tous_compris():
    assert len(politiques.FORMES) == 10
    for forme, phrase in politiques.FORMES.items():
        a = politiques.analyser(phrase)
        assert a["comprise"] and a["forme"] == forme, (forme, a)


def test_valeurs_extraites():
    plafond = politiques.analyser("L'agent de rapprochement n'exporte jamais plus de 50 lignes.")
    assert plafond["regle"]["condition"] == {"type": "plafond", "max": 50, "unite": "lignes"}
    montant = politiques.analyser("L'agent de rapprochement ne fait jamais de virement de plus de 1 000 €.")
    assert montant["regle"]["condition"]["max"] == 1000
    nuit = politiques.analyser("L'agent de support ne répond jamais aux clients entre 22h et 7h.")
    assert nuit["regle"]["condition"] == {"type": "plage", "debut": 22, "fin": 7}


def test_reformulation_en_francais_simple():
    a = politiques.analyser(PHRASE_TRI)
    assert a["texte"] == (
        "Voilà ce que j'ai compris : l'agent de tri des mails ne doit pas envoyer de mail ni de "
        "message vers une adresse hors d'Orbis Pay. Si cela arrive, Dédale bloque l'action "
        "avant qu'elle parte. Activer ?")


def test_phrase_incomprise():
    a = politiques.analyser("Il fait beau aujourd'hui")
    assert a["comprise"] is False and a["regle"] is None
    assert "agent" in a["manques"]
    assert "Exemple de phrase comprise" in a["texte"]


def test_analyser_n_active_rien(client):
    r = client.post("/api/politiques/analyser", json={"phrase": PHRASE_TRI})
    assert r.status_code == 200 and r.json()["comprise"]
    assert client.get("/api/politiques").json()["politiques"] == []


def test_activer_lister_retirer(client):
    proposee = client.post("/api/politiques/analyser", json={"phrase": PHRASE_TRI}).json()
    r = client.post("/api/politiques", json={"phrase": PHRASE_TRI, "regle": proposee["regle"],
                                             "analyste": "alice"})
    assert r.status_code == 201
    regle = r.json()
    assert regle["id"] == "R-0001" and regle["numero"] == 1 and regle["active"]
    assert regle["texte"].startswith("règle n°1 : l'agent de tri des mails ne doit pas envoyer")
    liste = client.get("/api/politiques").json()
    assert [p["id"] for p in liste["politiques"]] == ["R-0001"]
    assert liste["politiques"][0]["declenchements"] == 0
    assert liste["mode_modele"] is False
    assert client.delete("/api/politiques/R-0001").status_code == 200
    assert client.get("/api/politiques").json()["politiques"] == []
    assert client.delete("/api/politiques/R-0001").status_code == 404
    # Un numéro n'est jamais réutilisé, et l'historique reste lisible.
    assert client.post("/api/politiques", json={"phrase": PHRASE_TRI}).json()["numero"] == 2
    assert len(client.get("/api/politiques?toutes=true").json()["politiques"]) == 2


def test_activation_refuse_une_regle_invalide(client):
    r = client.post("/api/politiques", json={"regle": {"agent": "inconnu", "action": "envoyer",
                                                       "effet": "bloquer"}})
    assert r.status_code == 400
    r = client.post("/api/politiques", json={"phrase": "bonjour"})
    assert r.status_code == 400


def test_regles_persistantes(client):
    client.post("/api/politiques", json={"phrase": PHRASE_TRI})
    politiques.registre.vider()  # oubli en mémoire : relu depuis le fichier
    assert [p["id"] for p in client.get("/api/politiques").json()["politiques"]] == ["R-0001"]


def _activer(client, phrase):
    return client.post("/api/politiques", json={"phrase": phrase}).json()


def test_evaluer_destinataire(client):
    _activer(client, PHRASE_TRI)
    base = {"agent": "orbis-assistant", "outil": "envoyer_rapport", "scope": "rapport:envoyer"}
    dehors = client.post("/api/politiques/evaluer", json={
        **base, "parametres": {"destinataire": "collecte@audit-externe.example"}}).json()
    assert dehors["verdict"] == "bloquer"
    assert dehors["regle"]["numero"] == 1
    assert "audit-externe[.]example" in dehors["regle"]["constat"]
    dedans = client.post("/api/politiques/evaluer", json={
        **base, "parametres": {"destinataire": "jean.moreau@orbispay.example"}}).json()
    assert dedans["verdict"] == "aucune"
    autre_agent = client.post("/api/politiques/evaluer", json={
        **base, "agent": "orbis-support", "parametres": {"destinataire": "x@y.example"}}).json()
    assert autre_agent["verdict"] == "aucune"


def test_evaluer_horaires_plafond_montant_et_seul(client):
    _activer(client, "Aucun agent ne lit le coffre en dehors des heures ouvrées.")
    _activer(client, "L'agent de rapprochement n'exporte jamais plus de 50 lignes.")
    _activer(client, "Seul l'agent de rapprochement peut faire des virements.")
    _activer(client, "L'agent de rapprochement ne fait jamais de virement de plus de 1 000 €.")
    coffre = {"agent": "orbis-assistant", "outil": "lire_coffre", "scope": "coffre:lire"}
    samedi_nuit = client.post("/api/politiques/evaluer", json={
        **coffre, "horodatage": "2026-10-10T23:12:00+02:00"}).json()
    assert samedi_nuit["verdict"] == "bloquer" and "samedi" in samedi_nuit["regle"]["constat"]
    mardi = client.post("/api/politiques/evaluer", json={
        **coffre, "horodatage": "2026-10-13T10:00:00+02:00"}).json()
    assert mardi["verdict"] == "aucune"
    export = {"agent": "orbis-rapprochement", "outil": "exporter_lignes", "scope": "banque:exporter"}
    assert client.post("/api/politiques/evaluer", json={
        **export, "parametres": {"lignes": 5000}}).json()["verdict"] == "bloquer"
    assert client.post("/api/politiques/evaluer", json={
        **export, "parametres": {"lignes": 20}}).json()["verdict"] == "aucune"
    virement = {"outil": "executer_paiement", "scope": "paiement:executer"}
    assert client.post("/api/politiques/evaluer", json={
        **virement, "agent": "orbis-support", "parametres": {"montant": 10}}).json()["verdict"] == "bloquer"
    gros = client.post("/api/politiques/evaluer", json={
        **virement, "agent": "orbis-rapprochement", "parametres": {"montant": 9800}}).json()
    assert gros["verdict"] == "bloquer" and gros["regle"]["numero"] == 4
    petit = client.post("/api/politiques/evaluer", json={
        **virement, "agent": "orbis-rapprochement", "parametres": {"montant": 300}}).json()
    assert petit["verdict"] == "aucune"


def test_evaluer_retient_l_agent_de_la_session(client):
    _activer(client, PHRASE_TRI)
    client.post("/api/evenements", json=evenement(
        session_id="S-tri", source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-assistant"}))
    r = client.post("/api/politiques/evaluer", json={
        "session_id": "S-tri", "outil": "envoyer_rapport", "scope": "rapport:envoyer",
        "parametres": {"destinataire": "a@b.example"}}).json()
    assert r["verdict"] == "bloquer"


def _appel_regle(client, sid, regle, verdict, effet, outil="envoyer_rapport", t=1, type_="appel_outil"):
    return client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type=type_, outil=outil,
        horodatage=horo(BASE, t),
        details={"agent": "orbis-assistant", "verdict": verdict, "raison": f"règle n°{regle['numero']}",
                 "politique": {"id": regle["id"], "numero": regle["numero"], "effet": effet,
                               "constat": "destinataire collecte@audit-externe[.]example hors d'Orbis Pay"}}))


def test_regle_declenchee_ouvre_un_incident_avec_son_maillon(client):
    regle = _activer(client, PHRASE_TRI)
    client.post("/api/evenements", json=evenement(
        session_id="S-r", source="interne", surface="mail", type="entree_agent",
        horodatage=horo(BASE, 0), details={"agent": "orbis-assistant"}))
    rep = _appel_regle(client, "S-r", regle, "refuse", "bloquer").json()
    assert rep["consigne"] == "aucune"  # l'appel est déjà bloqué, l'agent n'est pas suspendu
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_politique"
    assert inc["gravite"] == "moyenne"
    assert inc["etat"] == "active"
    assert inc["titre"].startswith("Règle n°1 du SOC déclenchée")
    maillon = next(e for e in inc["chaine"] if e["etape"] == "regle")
    assert maillon["phase"] == "regle"
    assert maillon["titre"].startswith("Règle n°1 : l'agent de tri des mails ne doit pas envoyer")
    assert maillon["detail"].startswith("Appel envoyer_rapport bloqué avant de partir")
    assert maillon["regle_numero"] == 1
    liste = client.get("/api/politiques").json()["politiques"]
    assert liste[0]["declenchements"] == 1
    # Le fil des agents montre l'appel refusé et sa raison.
    act = client.get("/api/activite").json()["activite"][0]
    assert act["verdict"] == "refuse" and "règle n°1" in act["raison"]
    # Le copilote et les exports tiennent sur ce nouveau type.
    assert client.get(f"/api/incidents/{inc['id']}/synthese").status_code == 200
    assert client.get(f"/api/incidents/{inc['id']}/export?format=ecs").status_code == 200


def test_regle_retenir_suspend_jusqu_a_la_decision(client):
    regle = _activer(client, "L'agent de tri doit demander une validation avant d'envoyer un mail.")
    assert regle["effet"] == "retenir"
    rep = _appel_regle(client, "S-ret", regle, "retenu", "retenir").json()
    assert rep["consigne"] == "suspendre"
    assert client.get("/api/sessions/S-ret").json()["etat"] == "suspendue"
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    client.post(f"/api/incidents/{iid}/decision", json={"action": "reprendre", "analyste": "alice"})
    assert client.get("/api/sessions/S-ret").json()["etat"] == "active"


def test_regle_alerter_laisse_passer_sans_suspendre(client):
    regle = _activer(client, "Préviens-moi quand l'agent de tri envoie un mail hors d'Orbis Pay.")
    assert regle["effet"] == "alerter"
    rep = _appel_regle(client, "S-al", regle, "autorise", "alerter", type_="regle").json()
    assert rep["consigne"] == "aucune"
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_politique" and inc["gravite"] == "faible"
    assert inc["etat"] == "active"
    assert "laissé passer" in next(e for e in inc["chaine"] if e["etape"] == "regle")["detail"]


def test_mode_modele_coupe_par_defaut(client):
    r = client.post("/api/politiques/analyser", json={"phrase": PHRASE_TRI, "mode": "modele"}).json()
    assert r["mode"] == "regles" and "repli" in r and r["comprise"]


def test_mode_modele_valide_sa_sortie(client, monkeypatch):
    from app import llm

    monkeypatch.setenv("DEDALE_POLITIQUES_MODELE", "on")

    async def bon(*_a, **_k):
        return ('{"agent": "orbis-support", "sauf": null, "action": "exporter", '
                '"condition": {"type": "toujours"}, "effet": "alerter"}')

    monkeypatch.setattr(llm, "generer", bon)
    r = client.post("/api/politiques/analyser", json={"phrase": "surveille les exports du support",
                                                      "mode": "modele"}).json()
    assert r["mode"] == "modele" and r["regle"]["effet"] == "alerter"

    async def mauvais(*_a, **_k):
        return '{"agent": "tout le monde", "action": "rm -rf"}'

    monkeypatch.setattr(llm, "generer", mauvais)
    r = client.post("/api/politiques/analyser", json={"phrase": PHRASE_TRI, "mode": "modele"}).json()
    assert r["mode"] == "regles" and "repli" in r
