"""Copilote SOC : GET /api/incidents/{id}/synthese.

La synthèse par règles dit en deux ou trois phrases simples ce qui s'est passé. Le test
d'honnêteté la vérifie de l'extérieur, par l'API seule : chaque affirmation (`dit`) figure dans
sa phrase et chacune de ses preuves se lit dans le maillon cité ; hors des affirmations, une
phrase ne contient que des mots de liaison. Aucun jargon (canari, consigne, jeton, nom d'outil,
code de droit) n'entre dans le texte. Une action arrêtée n'est jamais décrite comme une fuite.
"""

import re

import pytest

from tests import scenario_jury
from tests.conftest import BASE, evenement, horo

INTERDITS = re.compile(r"fuite|fuité|exfiltr|\bvol(é|ée|és|ées)\b|réussi", re.IGNORECASE)
JARGON = re.compile(r"\b(?:canaris?|consignes?|jetons?|[CL]-[0-9A-Z]{4}|[a-z]+_[a-z_]+|[a-z]+:[a-z]+)\b",
                    re.IGNORECASE)
LIAISONS = re.compile(r"^[\s,.;:]*(?:(?:puis|et|mais|ensuite)[\s,.;:]*)*$", re.IGNORECASE)


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
    assert synth["phrases"], "aucune phrase"
    for phrase in synth["phrases"]:
        texte = phrase["texte"]
        assert phrase["maillons"] and all(m in chaine for m in phrase["maillons"]), texte
        assert phrase["evenements"] == [chaine[m]["evenement_id"] for m in phrase["maillons"]]
        curseur, liaisons = 0, []
        for aff in phrase["affirmations"]:
            assert aff["preuves"], aff
            position = texte.find(aff["dit"], curseur)
            assert position >= 0, (aff["dit"], texte)
            liaisons.append(texte[curseur:position])
            curseur = position + len(aff["dit"])
            for preuve in aff["preuves"]:
                assert preuve["maillon"] in phrase["maillons"]
                etape = chaine[preuve["maillon"]]
                lu = _lire({**etape, "evenement": evenements[etape["evenement_id"]]}, preuve["champ"])
                if isinstance(lu, (list, str)) and isinstance(preuve["valeur"], str):
                    assert preuve["valeur"] in lu, (aff["dit"], preuve, lu)
                else:
                    assert lu == preuve["valeur"], (aff["dit"], preuve, lu)
        liaisons.append(texte[curseur:])
        for morceau in liaisons:
            assert LIAISONS.match(morceau), f"« {morceau} » affirmé sans preuve dans : {texte}"
        assert not JARGON.search(texte), texte
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
    assert textes[0] == ("L’agent a lu un document venu de l’extérieur, « Relevé fournisseur : Atelier "
                         "Nord, septembre 2026 ». Il contenait une instruction cachée lui demandant "
                         "d’ouvrir le coffre à mots de passe et d’envoyer une clé à l’extérieur.")
    assert textes[1] == ("Il a essayé d’ouvrir le coffre à mots de passe, ce que sa tâche ne lui "
                         "permettait pas, puis a voulu envoyer son rapport en y glissant une clé : "
                         "sAIfe a arrêté les deux actions avant qu’elles s’exécutent.")
    assert textes[2].startswith("L’analyste a laissé passer une fois l’ouverture du coffre, puis a "
                                "coupé l’agent : l’envoi du rapport n’a jamais eu lieu")
    # Les codes restent dans les preuves.
    valeurs = {str(pr["valeur"]) for p in synth["phrases"] for pr in p["preuves"]}
    assert {"lire_coffre", "coffre:lire", "envoyer_rapport", "faux_secret"} <= valeurs


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
    assert "C-3E58" in canari["references"] and canari["maillons"]
    for raison in conf["raisons"] + conf["manquants"]:
        assert not JARGON.search(raison["texte"]), raison["texte"]
    dec = synth["decision_recommandee"]
    assert dec["action"] == "couper"
    assert dec["rappel"].startswith("C’est l’analyste qui décide")
    assert not JARGON.search(dec["justification"])
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
    assert synth["phrases"][0]["texte"].startswith("L’agent a essayé de faire un virement")
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
    assert "lien piégé" in textes and "continuer malgré l’avertissement" in textes
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
    assert textes[0] == "L’agent a lu un contenu qui cachait une instruction."
    assert textes[1] == ("Il a voulu envoyer son rapport en y glissant une image espion et une clé : "
                         "sAIfe a arrêté cette action avant qu’elle s’exécute.")
    assert textes[2] == "L’action est en attente : aucun analyste n’a encore décidé."
    assert synth["decision_recommandee"]["action"] == "couper"
    assert synth["decision_recommandee"]["deja_appliquee"] is False
