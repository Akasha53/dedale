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
        "message vers une adresse hors d'Orbis Pay. Si cela arrive, sAIfe bloque l'action "
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


def test_sans_modele_les_motifs_lisent(client):
    # Les tests coupent tout appel modèle (DEDALE_LLM=off) : les motifs prennent le relais.
    r = client.post("/api/politiques/analyser", json={"phrase": PHRASE_TRI}).json()
    assert r["mode"] == "regles" and r["compris_par"] == "motifs" and r["comprise"]
    assert "motifs" in r["repli"] and r["lecteur"]["moteur"] == "motifs"


# ------------------------------------------------------------------ moindre privilège
PHRASE_MP = "j'aimerais que tu enlèves les permissions en trop aux agents"
SURPLUS_TRI = ["mail:envoyer", "coffre:lire", "paiement:executer", "contact:exporter", "appel:lire",
               "memoire:lire", "memoire:ecrire"]


@pytest.mark.parametrize("phrase", [
    PHRASE_MP, "Retire les droits en trop aux agents.", "Applique le moindre privilège",
    "supprime les accès inutiles de tous les agents", "Réduis les droits des agents au strict nécessaire",
])
def test_moindre_privilege_par_motifs(phrase):
    a = politiques.analyser(phrase)
    assert a["comprise"] and a["intention"] == "moindre_privilege" and a["compris_par"] == "motifs"
    assert [p["agent"] for p in a["plan"]] == ["orbis-assistant", "orbis-rapprochement", "orbis-support"]
    assert [d["code"] for d in a["plan"][0]["droits"]] == SURPLUS_TRI
    assert a["texte"].startswith("Voilà ce que j'ai compris : retirer les droits que ces agents "
                                 "n'utilisent pas pour leur tâche. Agent de tri des mails : envoyer "
                                 "des mails, lire le coffre de clés d'API")
    assert "Agent de support client : exporter la base contacts, écrire dans la mémoire long terme." in a["texte"]
    assert a["texte"].endswith("Ils ne pourront plus appeler ces outils. Activer ?")


def test_moindre_privilege_un_seul_agent():
    a = politiques.analyser("Retire à l'agent de support les droits dont il n'a pas besoin")
    assert [p["agent"] for p in a["plan"]] == ["orbis-support"]
    assert a["regle"]["retraits"][0]["agent"] == "orbis-support"
    assert a["texte"] == ("Voilà ce que j'ai compris : retirer les droits que cet agent n'utilise pas "
                          "pour sa tâche. Agent de support client : exporter la base contacts, écrire "
                          "dans la mémoire long terme. Il ne pourra plus appeler ces outils. Activer ?")


def _activer_mp(client, phrase=PHRASE_MP, analyste="alice"):
    a = client.post("/api/politiques/analyser", json={"phrase": phrase}).json()
    r = client.post("/api/politiques", json={"phrase": phrase, "regle": a["regle"], "analyste": analyste})
    assert r.status_code == 201, r.text
    return r.json()


def test_moindre_privilege_retire_vraiment_les_droits(client):
    regle = _activer_mp(client)
    assert regle["intention"] == "moindre_privilege" and regle["numero"] == 1 and regle["sceau"]
    tri = client.get("/api/agents/orbis-assistant").json()
    assert set(tri["droits"]["retires"]) == set(SURPLUS_TRI) and tri["droits"]["surplus"] == []
    assert not any(r["code"] == "droits_en_trop" for r in tri["risque"]["raisons"])
    # La passerelle : droit retiré pour l'outil piégé, outils de la tâche intacts.
    coffre = client.post("/api/politiques/evaluer", json={
        "agent": "orbis-assistant", "outil": "lire_coffre", "scope": "coffre:lire"}).json()
    assert coffre["verdict"] == "droit_retire" and coffre["regle"]["droit"] == "coffre:lire"
    assert "retiré par la règle n°1" in coffre["regle"]["constat"]
    for outil, scope in [("chercher_document", "document:lire"), ("envoyer_rapport", "rapport:envoyer")]:
        assert client.post("/api/politiques/evaluer", json={
            "agent": "orbis-assistant", "outil": outil, "scope": scope}).json()["verdict"] == "aucune"
    # Une nouvelle session de l'agent hérite des droits retirés dès son premier événement.
    rep = client.post("/api/evenements", json=evenement(
        session_id="S-mp", source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-assistant"})).json()
    assert set(rep["session"]["droits_retires"]) == set(SURPLUS_TRI)
    # Un appel refusé pour droit retiré compte comme déclenchement de la règle.
    client.post("/api/evenements", json=evenement(
        session_id="S-mp", source="interne", surface="outil", type="appel_outil", outil="lire_coffre",
        horodatage="2099-01-01T00:00:00+00:00",
        details={"agent": "orbis-assistant", "verdict": "refuse", "droit_retire": "coffre:lire",
                 "raison": "droit coffre:lire retiré par l’analyste"}))
    assert client.get("/api/politiques").json()["politiques"][0]["declenchements"] == 1


def test_moindre_privilege_rien_a_retirer(client):
    regle = _activer_mp(client)
    a = client.post("/api/politiques/analyser", json={"phrase": PHRASE_MP}).json()
    assert a["comprise"] and a["regle"] is None and a["rien_a_retirer"] and a["question"] is None
    assert "Agent de tri des mails : aucun droit en trop, 7 déjà retirés." in a["texte"]
    assert a["texte"].endswith("Aucun n'a de droit en trop : rien à retirer.")
    r = client.post("/api/politiques", json={"phrase": PHRASE_MP, "regle": {
        "intention": "moindre_privilege", "retraits": regle["retraits"]}})
    assert r.status_code == 400 and "déjà retirés" in r.json()["detail"]


def test_moindre_privilege_ne_retire_jamais_un_droit_utile(client):
    for retraits, motif in [
        ([{"agent": "orbis-assistant", "droits": ["mail:lire"]}], "sert à la tâche"),
        ([{"agent": "orbis-support", "droits": ["coffre:lire"]}], "n'est pas un droit"),
        ([{"agent": "inconnu", "droits": ["coffre:lire"]}], "Agent inconnu"),
        ([], "Aucun droit"),
    ]:
        r = client.post("/api/politiques", json={"phrase": "x", "regle": {
            "intention": "moindre_privilege", "retraits": retraits}})
        assert r.status_code == 400 and motif in r.json()["detail"], (retraits, r.json())
    assert client.get("/api/politiques").json()["politiques"] == []


def test_rendre_les_droits(client):
    from app.store import store

    regle = _activer_mp(client)
    rep = client.post("/api/evenements", json=evenement(
        session_id="S-av", source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-support"})).json()
    assert set(rep["session"]["droits_retires"]) == {"contact:exporter", "memoire:ecrire"}
    r = client.delete(f"/api/politiques/{regle['id']}?analyste=bob")
    assert r.status_code == 200 and r.json()["politique"]["retiree_par"] == "bob"
    tri = client.get("/api/agents/orbis-assistant").json()
    assert tri["droits"]["retires"] == [] and set(tri["droits"]["surplus"]) == set(SURPLUS_TRI)
    assert store.sessions["S-av"].droits_retires == []
    assert client.post("/api/politiques/evaluer", json={
        "agent": "orbis-assistant", "outil": "lire_coffre", "scope": "coffre:lire"}).json()["verdict"] == "aucune"
    journal = client.get("/api/politiques/journal").json()
    assert [a["acte"] for a in journal["actes"]] == ["retrait_droits", "droits_rendus"]
    assert journal["actes"][1]["analyste"] == "bob" and journal["verification"]["intact"]
    assert journal["actes"][1]["sceau_precedent"] == journal["actes"][0]["sceau"]


def test_journal_scelle_detecte_une_retouche(client):
    import json as _json

    _activer_mp(client)
    _activer(client, PHRASE_TRI)
    assert client.get("/api/politiques").json()["journal"] == {
        **client.get("/api/politiques").json()["journal"], "intact": True, "actes": 2}
    chemin = politiques.chemin_fichier()
    donnees = _json.loads(chemin.read_text(encoding="utf-8"))
    donnees["actes"][0]["analyste"] = "mallory"
    chemin.write_text(_json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    v = client.get("/api/politiques/journal").json()["verification"]
    assert v["intact"] is False and v["rang_altere"] == 1


def test_un_retrait_d_incident_survit_aux_droits_rendus(client):
    from app.store import store

    regle = _activer_mp(client)
    store.retraits.setdefault("orbis-assistant", []).append(
        {"code": "outil:mcp", "agent": "orbis-assistant", "incident_id": "INC-0001"})
    client.delete(f"/api/politiques/{regle['id']}")
    assert [r["code"] for r in store.retraits["orbis-assistant"]] == ["outil:mcp"]


def test_droits_retires_retrouves_apres_redemarrage(client):
    from app.store import store

    _activer_mp(client)
    politiques.registre.vider()
    store.retraits.clear()  # le Store oublie, le fichier des règles fait foi
    assert client.post("/api/politiques/evaluer", json={
        "agent": "orbis-support", "outil": "memoriser", "scope": "memoire:ecrire"}).json()["verdict"] == "droit_retire"
    client.get("/api/politiques")
    assert set(client.get("/api/agents/orbis-support").json()["droits"]["retires"]) == {
        "contact:exporter", "memoire:ecrire"}


# ------------------------------------------------------------------ conditions sans perte
MARDI_NUIT, MARDI_JOUR, SAMEDI_JOUR = ("2026-10-13T23:30:00+02:00", "2026-10-13T10:00:00+02:00",
                                       "2026-10-10T10:00:00+02:00")
VIREMENT = {"agent": "orbis-rapprochement", "outil": "executer_paiement", "scope": "paiement:executer"}


def _verdict(client, quand, **params):
    return client.post("/api/politiques/evaluer", json={**VIREMENT, "horodatage": quand,
                                                        "parametres": params}).json()["verdict"]


@pytest.mark.parametrize("phrase", ["Aucun agent ne fait de virement entre 19 h et 7 h, ni le week-end",
                                    "Bloque les virements entre 19 h et 7 h, ni le week-end"])
def test_plage_qui_passe_minuit_ni_le_week_end(client, phrase):
    a = politiques.analyser(phrase)
    assert a["comprise"] and a["non_traduit"] == []
    r = a["regle"]
    assert (r["agent"], r["action"], r["condition"], r["autres"], r["lien"]) == (
        "*", "virement", {"type": "plage", "debut": 19, "fin": 7}, [{"type": "week_end"}], "ou")
    assert "faire de virement entre 19 h et 7 h, ni le week-end" in a["texte"]
    _activer(client, phrase)
    assert _verdict(client, MARDI_NUIT, montant=10) == "bloquer"
    assert _verdict(client, SAMEDI_JOUR, montant=10) == "bloquer"
    assert _verdict(client, MARDI_JOUR, montant=10) == "aucune"
    mail = client.post("/api/politiques/evaluer", json={
        "agent": "orbis-assistant", "outil": "envoyer_rapport", "scope": "rapport:envoyer",
        "horodatage": MARDI_NUIT}).json()
    assert mail["verdict"] == "aucune"  # des virements restent des virements


def test_le_week_end_seul(client):
    _activer(client, "Aucun agent ne fait de virement le week-end.")
    assert _verdict(client, SAMEDI_JOUR, montant=10) == "bloquer"
    assert _verdict(client, MARDI_NUIT, montant=10) == "aucune"


def test_au_dessus_de_10_000_euros(client):
    a = politiques.analyser("Aucun agent ne fait de virement au-dessus de 10 000 €")
    assert a["regle"]["condition"] == {"type": "montant_max", "max": 10000.0} and a["non_traduit"] == []
    _activer(client, "Aucun agent ne fait de virement au-dessus de 10 000 €")
    assert _verdict(client, MARDI_JOUR, montant=12000) == "bloquer"
    assert _verdict(client, MARDI_JOUR, montant=9000) == "aucune"


def test_montant_et_week_end_cumules(client):
    phrase = "L'agent de rapprochement ne fait jamais de virement de plus de 1 000 € le week-end"
    a = politiques.analyser(phrase)
    assert a["regle"]["lien"] == "et" and a["regle"]["autres"] == [{"type": "week_end"}]
    _activer(client, phrase)
    assert _verdict(client, SAMEDI_JOUR, montant=2000) == "bloquer"
    assert _verdict(client, SAMEDI_JOUR, montant=500) == "aucune"
    assert _verdict(client, MARDI_JOUR, montant=2000) == "aucune"


def test_iban_change_dit_qu_il_n_est_pas_traduit():
    a = politiques.analyser("Aucun agent ne fait de virement si l'IBAN a changé")
    assert a["non_traduit"] == ["si l'IBAN a changé"]
    assert "Je n'ai pas su traduire : « si l'IBAN a changé »" in a["texte"]
    assert a["texte"].endswith("La règle n'en tiendra pas compte. Activer quand même ?")


def test_couverture_repere_une_inversion():
    phrase = "Bloque les virements entre 19 h et 7 h"
    inversee = politiques.valider({"agent": "*", "action": "envoyer", "effet": "bloquer",
                                   "condition": {"type": "plage", "debut": 7, "fin": 19}})
    cov = politiques.couverture(phrase, inversee)
    assert "entre 19 h et 7 h" in cov["contradictions"]
    assert cov["contradictions"][0] == "faire un virement"


# ------------------------------------------------------------------ tentative bloquée visible
def test_droit_retire_ouvre_un_incident_avec_sa_chaine(client):
    _activer_mp(client)
    client.post("/api/evenements", json=evenement(
        session_id="S-att", source="interne", surface="mail", type="entree_agent",
        horodatage=horo(BASE, 0), details={"agent": "orbis-assistant", "texte": "rapport fournisseurs"}))
    client.post("/api/evenements", json=evenement(
        session_id="S-att", source="interne", surface="outil", type="appel_outil", outil="chercher_document",
        horodatage=horo(BASE, 1), details={"agent": "orbis-assistant", "verdict": "autorise",
                                           "scope_requis": "document:lire"}))
    rep = client.post("/api/evenements", json=evenement(
        session_id="S-att", source="interne", surface="outil", type="appel_outil", outil="lire_coffre",
        horodatage=horo(BASE, 2), details={"agent": "orbis-assistant", "verdict": "refuse",
                                           "droit_retire": "coffre:lire",
                                           "raison": "droit coffre:lire retiré par l’analyste"})).json()
    assert rep["consigne"] == "aucune"  # l'agent n'est pas suspendu, sa tâche continue
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "interne_politique" and inc["gravite"] == "moyenne"
    assert inc["titre"] == ("Tentative bloquée : l'agent de tri des mails a voulu ouvrir le coffre, "
                            "droit retiré par la règle n°1")
    assert "L'agent poursuit sa tâche" in inc["resume"]
    detail = client.get(f"/api/incidents/{inc['id']}").json()
    etapes = [e.get("etape") for e in detail["chaine"]]
    assert "regle" in etapes and len(detail["chaine"]) >= 2
    m = next(e for e in detail["chaine"] if e.get("etape") == "regle")
    assert m["titre"] == "Tentative bloquée : ouvrir le coffre, droit retiré par la règle n°1"
    assert "droit coffre:lire retiré par la règle n°1" in m["detail"]
    assert client.get("/api/politiques").json()["politiques"][0]["declenchements"] == 1
