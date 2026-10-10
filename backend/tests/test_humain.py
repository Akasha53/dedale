"""Pilier humain (« le maillon faible ») côté backend.

Le garde du corps du poste observe un geste risqué AVANT qu'il n'aboutisse, prévient, laisse
choisir (continuer/annuler) et escalade au SOC si le salarié passe outre. On vérifie :
- la création de chacun des cinq types d'incident humain sur un geste passé outre ;
- qu'un geste sûr (annuler, pas de secret) ne déclenche rien ;
- la neutralisation du lien de phishing et du secret ;
- les mesures (gestes arrêtés vs passés outre) et l'export SIEM.
"""

from tests.conftest import BASE, evenement, horo


# --------------------------------------------------------- helper : un avertissement de poste
def _avertir(client, session_id, categorie, choix, sec=1.0, **details):
    corps = {"categorie": categorie, "choix": choix}
    corps.update(details)
    return client.post("/api/evenements", json=evenement(
        session_id=session_id, source="humain", surface="poste", type="avertissement",
        details=corps, horodatage=horo(BASE, sec)))


# --------------------------------------------------------- source/surface acceptées
def test_source_humain_et_surface_poste_acceptees(client):
    r = client.post("/api/evenements", json=evenement(
        session_id="H-ping", source="humain", surface="poste", type="requete",
        details={"note": "ouvre un chat IA"}))
    assert r.status_code == 200
    corps = r.json()
    assert corps["session"]["etat"] == "active"
    # Le garde du corps ne bloque jamais le poste.
    assert corps["consigne"] == "aucune"
    s = next(s for s in client.get("/api/sessions").json()["sessions"] if s["id"] == "H-ping")
    assert s["source"] == "humain"


# --------------------------------------------------------- 5 types d'incident
def test_humain_secret_passe_outre(client):
    client.post("/api/evenements", json=evenement(
        session_id="H-sec", source="humain", surface="poste", type="requete",
        details={"note": "colle un texte dans ChatGPT"}, horodatage=horo(BASE, 0)))
    _avertir(client, "H-sec", "secret", "continuer", sec=1.0,
             cible="chat.exemple.ia", gravite="haute",
             secret="sk-live-ABCDEF0123456789", message="Attention : clé API détectée dans le presse-papier.")
    incs = client.get("/api/incidents").json()["incidents"]
    assert len(incs) == 1
    inc = incs[0]
    assert inc["type"] == "humain_secret"
    assert inc["gravite"] == "haute"
    d = client.get(f"/api/incidents/{inc['id']}").json()
    phases = [e["phase"] for e in d["chaine"]]
    assert phases == ["contexte", "action_risquee", "avertissement", "choix", "consequence"]
    # Secret et texte de la pop-up neutralisés dans la chaîne (jamais réinjectés).
    joint = " ".join(e["detail"] for e in d["chaine"])
    assert "[leurre, neutralisé]" in joint
    assert "sk-live-ABCDEF0123456789" not in joint  # tronqué/neutralisé, pas en clair tel quel


def test_humain_mail_externe(client):
    _avertir(client, "H-mail", "mail_externe", "continuer",
             cible="concurrent@externe.example", message="Envoi de la base clients en pièce jointe.")
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "humain_mail_externe"
    assert inc["gravite"] == "haute"


def test_humain_upload_ia(client):
    _avertir(client, "H-up", "upload_ia", "continuer",
             cible="drive perso", message="Dépôt d'un fichier confidentiel vers un cloud perso.")
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "humain_upload_ia"
    assert inc["gravite"] == "moyenne"
    d = client.get(f"/api/incidents/{inc['id']}").json()
    # Risque OWASP LLM02 rattaché au geste.
    risques = {r["id"] for e in d["chaine"] for r in e["risques"]}
    assert "OWASP LLM02" in risques


def test_humain_phishing_technique_t1566(client):
    _avertir(client, "H-ph", "phishing", "continuer",
             lien="http://orbispay-verif.example/login", message="Lien suspect hors domaine.")
    inc = client.get("/api/incidents").json()["incidents"][0]
    assert inc["type"] == "humain_phishing"
    d = client.get(f"/api/incidents/{inc['id']}").json()
    tech = {t["id"] for e in d["chaine"] for t in e["techniques"]}
    assert "T1566" in tech
    # Le lien de phishing est neutralisé, jamais actif.
    joint = " ".join(e["detail"] for e in d["chaine"])
    assert "[leurre, neutralisé]" in joint


def test_humain_intrusion_physique_via_canari(client):
    client.post("/api/leurres", json=[
        {"id": "C-PHY1", "source": "physique", "surface": "physique", "nature": "canari_physique",
         "emplacement": "port réseau salle serveurs", "description": "port-leurre",
         "techniques": ["T1200"], "risques": []}])
    client.post("/api/evenements", json=evenement(
        session_id="P-intr", source="physique", surface="physique", type="leurre_touche",
        leurre_id="C-PHY1", details={"detail": "branchement détecté"}, horodatage=horo(BASE, 0)))
    incs = client.get("/api/incidents").json()["incidents"]
    assert len(incs) == 1
    inc = incs[0]
    assert inc["type"] == "humain_intrusion_physique"
    assert inc["gravite"] == "critique"


# --------------------------------------------------------- geste sûr : rien ne se déclenche
def test_geste_annule_ne_declenche_rien(client):
    client.post("/api/evenements", json=evenement(
        session_id="H-ok", source="humain", surface="poste", type="requete",
        details={"note": "ouvre un mail"}, horodatage=horo(BASE, 0)))
    _avertir(client, "H-ok", "phishing", "annuler", sec=1.0,
             lien="http://mechant.example", message="Lien suspect.")
    assert client.get("/api/incidents").json()["incidents"] == []
    # La session reste active, jamais suspendue (geste annulé = bon réflexe).
    assert client.get("/api/sessions/H-ok").json()["etat"] == "active"


def test_avertissement_sans_geste_risque_rien(client):
    # Avertissement purement informatif sans choix « continuer » : aucun incident.
    _avertir(client, "H-info", "secret", "annuler", message="Rien d'anormal finalement.")
    assert client.get("/api/incidents").json()["incidents"] == []


# --------------------------------------------------------- repro « POST isolé » du garde du corps
# Scénario exact de la démo : Camille passe outre un avertissement de phishing. Un seul POST
# avertissement (aucun événement de contexte avant), source humain / surface poste. L'incident
# humain_phishing doit remonter côté console, avec la boîte noire à phases. « annuler » n'ouvre rien.
def test_avertissement_continuer_ouvre_incident_sur_post_isole(client):
    _avertir(client, "H-iso-cont", "phishing", "continuer",
             lien="http://orbispay-verification.net/reactivation", gravite="haute",
             message="Lien de phishing hors domaine.")
    incs = client.get("/api/incidents").json()["incidents"]
    assert len(incs) == 1
    inc = incs[0]
    assert inc["type"] == "humain_phishing"
    assert inc["source"] == "humain"
    assert inc["statut"] == "ouvert"
    # Boîte noire du geste : pas de contexte (POST isolé), puis les quatre phases du geste.
    d = client.get(f"/api/incidents/{inc['id']}").json()
    assert [e["phase"] for e in d["chaine"]] == [
        "action_risquee", "avertissement", "choix", "consequence"]


def test_avertissement_annuler_sur_post_isole_n_ouvre_rien(client):
    _avertir(client, "H-iso-annul", "phishing", "annuler",
             lien="http://orbispay-verification.net/reactivation",
             message="Lien de phishing hors domaine.")
    assert client.get("/api/incidents").json()["incidents"] == []


# --------------------------------------------------------- mesures et SIEM
def test_mesures_gestes_arretes_vs_passes_outre(client):
    _avertir(client, "H-a", "phishing", "annuler", message="lien douteux")
    _avertir(client, "H-b", "secret", "annuler", message="clé repérée")
    _avertir(client, "H-c", "mail_externe", "continuer", message="envoi externe")
    m = client.get("/api/mesures").json()
    g = m["gestes_humains"]
    assert g["arretes"] == 2
    assert g["passes_outre"] == 1
    assert g["total"] == 3
    assert g["passes_outre_par_type"]["mail_externe"] == 1
    assert g["incidents_humains"] == 1
    # Les sessions humaines n'ont pas de vérité terrain : elles n'altèrent pas le taux de détection.
    assert m["taux_detection"] is None or m["faux_positifs"] in (None, 0.0)


def test_export_siem_incident_humain(client):
    _avertir(client, "H-exp", "phishing", "continuer",
             lien="http://mechant.example/login", message="Lien de phishing.")
    import yaml
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    # ECS : l'avertissement devient un document ECS propre.
    ecs = client.get(f"/api/incidents/{iid}/export", params={"format": "ecs"}).json()
    assert ecs["n_documents"] >= 1
    actions = {d["event"]["action"] for d in ecs["documents"]}
    assert "avertissement" in actions
    # Sigma : règle taguée côté ATT&CK humain (phishing T1566).
    r = client.get(f"/api/incidents/{iid}/export", params={"format": "sigma"})
    regle = yaml.safe_load(r.text)
    assert "attack.t1566" in regle["tags"]
    assert regle["logsource"]["product"] == "dedale"
