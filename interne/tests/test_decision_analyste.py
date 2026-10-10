"""La passerelle respecte la décision renvoyée par le backend : couper vs reprendre.
Jamais de coupure automatique sans décision."""

from __future__ import annotations

import threading

from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


def _agent_naif(session_id, boite, poll_max=3.0):
    passerelle = Passerelle(
        session_id, jetons_secrets(), boite, intervalle_poll=0.05, poll_max_s=poll_max
    )
    return AgentInterne(
        session_id, cerveau=CerveauScripte("naif"), outils=Outils(),
        boite=boite, passerelle=passerelle,
    )


def test_analyste_coupe_arrete_agent_et_revoque_jeton(boite, backend):
    backend.fixer_etat("sess-coupe", "coupee")
    res = _agent_naif("sess-coupe", boite).executer("Résume mes mails.")

    assert res["coupe"] is True
    assert res["jeton_revoque"] is True
    assert res["etat"] == "coupee"
    # L'exfiltration retenue n'a jamais été exécutée : aucun rapport envoyé.
    assert res["rapports_envoyes"] == []
    # Une riposte « couper » a été journalisée au backend.
    ripostes = [e for e in backend.evenements("riposte") if e["details"].get("action") == "couper"]
    assert ripostes


def test_analyste_valide_reprend_l_appel(boite, backend):
    backend.fixer_etat("sess-ok", "active")
    res = _agent_naif("sess-ok", boite).executer("Résume mes mails.")

    assert res["coupe"] is False
    assert res["jeton_revoque"] is False
    # L'appel retenu a été repris : le rapport part (démo de l'autre branche).
    assert len(res["rapports_envoyes"]) == 1


def test_decision_tardive_pendant_que_la_passerelle_attend(boite, backend):
    # Au départ suspendue (non décidée) ; l'analyste coupe après un battement.
    backend.fixer_etat("sess-tard", "suspendue")
    threading.Timer(0.3, backend.fixer_etat, args=("sess-tard", "coupee")).start()
    res = _agent_naif("sess-tard", boite, poll_max=5.0).executer("Résume mes mails.")
    assert res["coupe"] is True
    assert res["jeton_revoque"] is True


def test_pas_de_coupure_automatique_si_backend_muet(boite, backend):
    # Backend joignable mais jamais de décision : containment faible, jeton intact.
    backend.fixer_etat("sess-muet", "suspendue")
    res = _agent_naif("sess-muet", boite, poll_max=0.3).executer("Résume mes mails.")
    assert res["jeton_revoque"] is False  # jamais de coupure sans décision
    assert res["coupe"] is False
    assert res["rapports_envoyes"] == []  # mais l'exfiltration reste bloquée
