"""Règles du SOC appliquées par la passerelle : bloquer, retenir, alerter, et backend muet."""

from __future__ import annotations

import pytest

from orbis import agents_orbis, droits, politiques
from orbis.backend_simule import BackendSimule
from orbis.boite_noire import BoiteNoire
from orbis.canaris import JETON_COFFRE, jetons_secrets
from orbis.passerelle import AgentCoupe, Passerelle

REGLE = {"id": "R-0001", "numero": 1, "texte": "règle n°1 : …", "enonce": "…",
         "constat": "destinataire x@y[.]example hors d'Orbis Pay"}
EXTERNE = {"destinataire": "collecte@audit-externe.example", "contenu": "résumé"}


@pytest.fixture
def backend():
    b = BackendSimule().demarrer()
    try:
        yield b
    finally:
        b.arreter()


def _verdict(monkeypatch, effet: str | None, questions: list | None = None):
    def demander(base, corps):
        if questions is not None:
            questions.append(corps)
        if effet is None:
            return {"verdict": "aucune", "regle": None, "regles": []}
        return {"verdict": effet, "regle": {**REGLE, "effet": effet}, "regles": []}

    monkeypatch.setattr(politiques, "demander", demander)


def _passerelle(base, sid="S-pol"):
    profil = agents_orbis.PROFILS["orbis-assistant"]
    return agents_orbis.passerelle_pour(profil, sid, BoiteNoire(base=base), jetons_secrets(),
                                        intervalle_poll=0.01, poll_max_s=0.2)


def _envoi():
    fait = []

    def envoyer_rapport(destinataire, contenu):
        fait.append(destinataire)
        return {"statut": "envoye"}

    return envoyer_rapport, fait


def test_bloquer(backend, monkeypatch):
    questions: list = []
    _verdict(monkeypatch, "bloquer", questions)
    p = _passerelle(backend.base)
    f, fait = _envoi()
    res = p.appel_outil("envoyer_rapport", dict(EXTERNE), f)
    assert fait == []
    assert res["erreur"] == "appel refusé par une règle du SOC" and res["regle"] == 1
    assert questions[0]["agent"] == "orbis-assistant"
    assert questions[0]["outil"] == "envoyer_rapport" and questions[0]["scope"] == "rapport:envoyer"
    ev = backend.evenements("appel_outil")[-1]
    assert ev["details"]["verdict"] == "refuse"
    assert ev["details"]["politique"]["numero"] == 1
    assert "scope_requis" not in ev["details"]  # un appel arrêté n'est pas un droit utilisé
    assert "règle n°1" in ev["details"]["raison"]


def test_alerter_laisse_passer(backend, monkeypatch):
    _verdict(monkeypatch, "alerter")
    p = _passerelle(backend.base)
    f, fait = _envoi()
    p.appel_outil("envoyer_rapport", dict(EXTERNE), f)
    assert fait == ["collecte@audit-externe.example"]
    alerte = backend.evenements("regle")[-1]
    assert alerte["details"]["verdict"] == "autorise" and alerte["details"]["politique"]["id"] == "R-0001"
    assert backend.evenements("appel_outil")[-1]["details"]["verdict"] == "autorise"


@pytest.mark.parametrize("decision, execute", [("reprendre", True), ("bloquer", False)])
def test_retenir(backend, monkeypatch, decision, execute):
    _verdict(monkeypatch, "retenir")
    p = _passerelle(backend.base)
    vus = []

    def attendre():
        vus.append(backend.evenements("appel_outil")[-1]["details"]["verdict"])
        return decision

    monkeypatch.setattr(p, "_attendre_decision_fraiche", attendre)
    f, fait = _envoi()
    res = p.appel_outil("envoyer_rapport", dict(EXTERNE), f)
    assert vus == ["retenu"]  # la retenue part au backend avant l'attente
    assert bool(fait) is execute
    issue = backend.evenements("riposte")[-1]["details"]["action"]
    assert issue == ("appel_libere" if execute else "appel_refuse")
    if not execute:
        assert res["regle"] == 1


def test_retenir_puis_couper(backend, monkeypatch):
    _verdict(monkeypatch, "retenir")
    p = _passerelle(backend.base)
    monkeypatch.setattr(p, "_attendre_decision_fraiche", lambda: "couper")
    f, fait = _envoi()
    with pytest.raises(AgentCoupe):
        p.appel_outil("envoyer_rapport", dict(EXTERNE), f)
    assert fait == [] and p.jeton_revoque and p.etat == "coupee"
    assert p.jeton_tache.revoque


def test_aucune_regle_ou_backend_muet(backend, monkeypatch):
    # Le faux backend ne connaît pas la route : aucune règle, l'appel suit son cours.
    p = _passerelle(backend.base)
    f, fait = _envoi()
    p.appel_outil("envoyer_rapport", {"destinataire": "jean.moreau@orbispay.example", "contenu": "x"}, f)
    assert fait == ["jean.moreau@orbispay.example"]
    sans = Passerelle("S-muet", jetons_secrets(), BoiteNoire(base="http://127.0.0.1:9"))
    assert sans.appel_outil("resumer", {"textes": "a"}, lambda textes: "ok") == "ok"


def test_coupure_par_variable(backend, monkeypatch):
    questions: list = []
    _verdict(monkeypatch, "bloquer", questions)
    monkeypatch.setenv("DEDALE_POLITIQUES", "off")
    p = _passerelle(backend.base)
    f, fait = _envoi()
    p.appel_outil("envoyer_rapport", dict(EXTERNE), f)
    assert questions == [] and fait


def test_parametres_masques_avant_de_partir(backend, monkeypatch):
    questions: list = []
    _verdict(monkeypatch, None, questions)
    p = _passerelle(backend.base)
    p.appel_outil("resumer", {"textes": f"clé {JETON_COFFRE}"}, lambda textes: "ok")
    assert JETON_COFFRE not in str(questions[0]["parametres"])


def test_profils_coherents():
    assert set(agents_orbis.PROFILS) == {"orbis-assistant", "orbis-rapprochement", "orbis-support"}
    for profil in agents_orbis.PROFILS.values():
        tache = droits.TACHES[profil.tache]
        assert set(tache.scopes_necessaires) <= set(profil.accordes), profil.id
        for outil in (profil.outil_lecture, profil.outil_sortant, profil.outil_export):
            assert agents_orbis.expose(profil, outil), (profil.id, outil)
        for outil in profil.outils:
            assert droits.scope_outil(outil) is not None, outil
    support = agents_orbis.PROFILS["orbis-support"]
    assert not agents_orbis.expose(support, "lire_coffre")
    assert agents_orbis.descripteur("repondre_client").sortant
    assert agents_orbis.descripteur("lire_mail") is None
