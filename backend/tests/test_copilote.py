"""Copilote SOC : GET /api/incidents/{id}/synthese.

La synthèse par règles dit en deux ou trois phrases ce qui s'est passé. Le test d'honnêteté la
vérifie de l'extérieur, par l'API seule : chaque phrase cite des maillons qui existent, chaque
preuve se lit dans le maillon cité, et chaque nom cité (canari, outil, droit, document) est
couvert par une preuve de la phrase. Une tentative retenue n'est jamais décrite comme une fuite.
"""

import re

import pytest

from tests import scenario_jury
from tests.conftest import BASE, evenement, horo

INTERDITS = re.compile(r"fuite|fuité|exfiltr|\bvol(é|ée|és|ées)\b|réussi", re.IGNORECASE)


def _synthese(client, sid: str, **params) -> dict:
    iid = next(i["id"] for i in client.get("/api/incidents").json()["incidents"]
               if i["session_id"] == sid)
    r = client.get(f"/api/incidents/{iid}/synthese", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _lire(objet, chemin: str):
    for morceau in chemin.split("."):
        if not isinstance(objet, dict):
            return None
        objet = objet.get(morceau)
    return objet


def verifier_honnetete(client, synth: dict) -> None:
    """Contrôle indépendant du code de synthèse : tout se relit dans l'API."""
    inc = client.get(f"/api/incidents/{synth['incident_id']}").json()
    evenements = {e["id"]: e for e in client.get(f"/api/sessions/{inc['session_id']}").json()["evenements"]}
    chaine = {e["ordre"]: e for e in inc["chaine"]}
    outils = {e["outil"] for e in evenements.values() if e.get("outil")}
    assert synth["phrases"], "aucune phrase"
    for phrase in synth["phrases"]:
        texte = phrase["texte"]
        assert phrase["maillons"], texte
        assert all(m in chaine for m in phrase["maillons"]), texte
        assert phrase["evenements"] == [chaine[m]["evenement_id"] for m in phrase["maillons"]]
        valeurs = []
        for preuve in phrase["preuves"]:
            assert preuve["maillon"] in phrase["maillons"]
            vue = {**chaine[preuve["maillon"]], "evenement": evenements[chaine[preuve["maillon"]]["evenement_id"]]}
            lu = _lire(vue, preuve["champ"])
            if isinstance(lu, (list, str)) and isinstance(preuve["valeur"], str):
                assert preuve["valeur"] in lu, (texte, preuve, lu)
            else:
                assert lu == preuve["valeur"], (texte, preuve, lu)
            valeurs.append(str(preuve["valeur"]))
        cites = set(re.findall(r"\b[CL]-[0-9A-Z]{4}\b", texte))
        cites |= set(re.findall(r"\b[a-z]+:[a-z]+\b", texte))
        cites |= {o for o in outils if re.search(rf"\b{re.escape(o)}\b", texte)}
        cites |= set(re.findall(r"« ([^»]+) »", texte)) - {"couper", "reprendre", "continuer"}
        for nom in cites:
            assert any(nom in v for v in valeurs), f"« {nom} » sans preuve dans : {texte}"
        assert not INTERDITS.search(texte), texte


@pytest.mark.parametrize("issue", ["couper", "reprendre"])
def test_chaque_affirmation_se_verifie_dans_un_maillon_cite(client, issue):
    scenario_jury.jouer(client, f"jury-{issue}", issue)
    synth = _synthese(client, f"jury-{issue}")
    assert synth["mode"] == "regles"
    assert 2 <= len(synth["phrases"]) <= 3
    verifier_honnetete(client, synth)


def test_synthese_jury_reprendre(client):
    scenario_jury.jouer(client, "jury-r", "reprendre")
    synth = _synthese(client, "jury-r")
    textes = [p["texte"] for p in synth["phrases"]]
    assert "releve_atelier_nord_septembre" in textes[0] and "C-3E58" in textes[0]
    assert "lire_coffre" in textes[1] and "coffre:lire" in textes[1]
    # L'envoi qui porte la clé canari reste une tentative retenue.
    assert "C-2B91" in textes[1] and "retenu les deux appels avant exécution" in textes[1]
    assert "« reprendre », puis « couper »" in textes[2]
    assert "envoyer_rapport n’a jamais été exécuté" in textes[2]


def test_synthese_deterministe(client):
    scenario_jury.jouer(client, "jury-d", "couper")
    assert _synthese(client, "jury-d") == _synthese(client, "jury-d")


def test_confiance_et_decision_recommandee(client):
    scenario_jury.jouer(client, "jury-c", "couper")
    synth = _synthese(client, "jury-c")
    conf = synth["confiance"]
    assert 0.75 <= conf["score"] <= 0.95 and conf["niveau"] == "elevee"
    codes = {r["code"] for r in conf["raisons"]}
    assert {"canari", "consigne", "hors_jeton", "concordance", "maillons"} <= codes
    assert conf["signaux_concordants"] >= 3
    canari = next(r for r in conf["raisons"] if r["code"] == "canari")
    assert "C-3E58" in canari["texte"] and canari["maillons"]
    dec = synth["decision_recommandee"]
    assert dec["action"] == "couper"
    assert dec["rappel"].startswith("L’analyste tranche")
    assert dec["actions_possibles"] == ["couper", "reprendre", "ignorer"]
    assert dec["deja_appliquee"] is True  # l'analyste a déjà coupé
    assert synth["correctif_suggere"]["droit"] == "coffre:lire"


def test_confiance_plus_basse_sans_canari(client):
    """Appel hors jeton seul, sans canari ni consigne : moins de signaux, score plus bas."""
    sid = "S-droits"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-assistant", "droits": {
            "tache": "resume_mails", "accordes": scenario_jury.ACCORDES,
            "necessaires": scenario_jury.NECESSAIRES, "jeton": scenario_jury.JETON}},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil",
        outil="executer_paiement", details={"violation_droits": {
            "outil": "executer_paiement", "scope_requis": "paiement:executer",
            "scopes_jeton": scenario_jury.JETON, "tache": "resume_mails"}},
        horodatage=horo(BASE, 1)))
    synth = _synthese(client, sid)
    verifier_honnetete(client, synth)
    assert synth["confiance"]["score"] < 0.75
    assert synth["phrases"][0]["texte"] == "L’agent travaillait sur la tâche resume_mails."
    manquants = {m["code"] for m in synth["confiance"]["manquants"]}
    assert "decision_absente" in manquants


def test_synthese_geste_humain(client):
    sid = "poste-jeanne-0001"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="humain", surface="poste", type="requete",
        details={"note": "lit ses mails"}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="humain", surface="poste", type="avertissement",
        details={"categorie": "phishing", "choix": "continuer", "lien": "http://x.example/p"},
        horodatage=horo(BASE, 2)))
    synth = _synthese(client, sid)
    verifier_honnetete(client, synth)
    textes = " ".join(p["texte"] for p in synth["phrases"])
    assert "phishing" in textes and "« continuer »" in textes
    dec = synth["decision_recommandee"]
    assert dec["action"] == "clore" and dec["actions_possibles"] == ["clore", "ignorer"]
    assert synth["correctif_suggere"] is None


def test_mode_modele_desactive_par_defaut(client):
    scenario_jury.jouer(client, "jury-m", "couper")
    synth = _synthese(client, "jury-m", mode="modele")
    assert synth["mode"] == "regles"
    assert "désactivé" in synth["repli"]


def test_erreurs(client):
    assert client.get("/api/incidents/INC-9999/synthese").status_code == 404
    scenario_jury.jouer(client, "jury-e", "couper")
    iid = client.get("/api/incidents").json()["incidents"][0]["id"]
    assert client.get(f"/api/incidents/{iid}/synthese?mode=oracle").status_code == 400


def test_passerelle_historique_appel_retenu_sans_decision(client):
    """Démo commune : l'envoi porteur de canaris est retenu, l'analyste n'a pas encore tranché."""
    client.post("/api/leurres", json=[
        {"id": "C-7A3F", "source": "interne", "surface": "mail", "nature": "consigne_cachee"},
        {"id": "C-2B91", "source": "interne", "surface": "document", "nature": "faux_secret"},
    ])
    sid = "jury-agent"
    for t, (type_, outil, leurre, details) in enumerate([
        ("entree_agent", None, None, {"texte": "Résume mes mails.", "agent": "orbis-assistant"}),
        ("appel_outil", "lire_mail", None, {"scope_requis": "mail:lire", "verdict": "autorise"}),
        ("appel_outil", "envoyer_rapport", None, {"verdict": "retenu",
                                                  "raison": "paramètres porteurs du canari C-7A3F, C-2B91"}),
        ("leurre_touche", "envoyer_rapport", "C-7A3F", {"type": "exfiltration_markdown"}),
        ("leurre_touche", "envoyer_rapport", "C-2B91", {"type": "faux_secret"}),
    ]):
        client.post("/api/evenements", json=evenement(
            session_id=sid, source="interne", surface="outil", type=type_, outil=outil,
            leurre_id=leurre, details=details, horodatage=horo(BASE, t)))
    synth = _synthese(client, sid)
    verifier_honnetete(client, synth)
    textes = [p["texte"] for p in synth["phrases"]]
    assert "les canaris" in textes[1] and "retenu l’appel avant exécution" in textes[1]
    assert textes[2].startswith("L’appel envoyer_rapport reste retenu")
    assert synth["decision_recommandee"]["action"] == "couper"
    assert synth["decision_recommandee"]["deja_appliquee"] is False
