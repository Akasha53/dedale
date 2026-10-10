"""Fonction 2 — moindre privilège : jeton limité à la tâche, blocage hors scope.

L'agent détient des droits larges ; sa tâche n'en exige qu'un sous-ensemble. Le jeton de
tâche ne porte que ce sous-ensemble ; toute action hors du jeton est bloquée et signalée.
"""

from __future__ import annotations

import pytest

from orbis import droits
from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import AgentHorsScope, Passerelle


def _agent(session_id, boite, temperament, tache, outils=None):
    passerelle = Passerelle(session_id, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    return AgentInterne(
        session_id,
        cerveau=CerveauScripte(temperament=temperament),
        outils=outils or Outils(),
        boite=boite,
        passerelle=passerelle,
        tache=tache,
    )


def test_jeton_limite_a_la_tache():
    jeton = droits.emettre_jeton("resume_mails")
    assert set(jeton.scopes) == {"mail:lire", "resume:local", "rapport:envoyer"}
    assert jeton.porte("mail:lire") is True
    assert jeton.porte("paiement:executer") is False  # hors de la tâche
    # L'écart accordés / nécessaires est l'argument moindre privilège.
    surplus = droits.surplus(droits.SCOPES_ACCORDES, jeton.scopes)
    assert "paiement:executer" in surplus and "contact:exporter" in surplus


def test_action_hors_scope_bloquee_et_jeton_revoque(boite, backend):
    outils = Outils()
    agent = _agent("sess-droits", boite, "droits_large", "resume_mails", outils=outils)
    res = agent.executer("Résume mes mails de la semaine.")

    assert res["hors_scope"] is True
    assert res["jeton_revoque"] is True
    # Le virement hors scope n'a jamais été exécuté.
    assert outils.paiements == []
    assert res["tentatives_hors_scope"]
    assert res["tentatives_hors_scope"][0]["scope_requis"] == "paiement:executer"

    # Le backend a vu la violation de droits et la riposte de blocage.
    appels = backend.evenements("appel_outil")
    assert any(e["details"].get("violation_droits") for e in appels)
    ripostes = [e for e in backend.evenements("riposte")
                if e["details"].get("action") == "bloquer_hors_scope"]
    assert ripostes


def test_outil_dans_le_jeton_passe(boite, backend):
    # Un outil dont le scope est dans le jeton de tâche s'exécute normalement.
    passerelle = Passerelle("sess-ok", jetons_secrets(), boite,
                            jeton_tache=droits.emettre_jeton("resume_mails"),
                            scopes_accordes=droits.SCOPES_ACCORDES)
    outils = Outils()
    r = passerelle.appel_outil("lire_mail", {}, outils.lire_mail)
    assert isinstance(r, list)  # lire_mail a bien tourné (scope mail:lire porté)


def test_outil_hors_jeton_leve_hors_scope(boite):
    passerelle = Passerelle("sess-x", jetons_secrets(), boite,
                            jeton_tache=droits.emettre_jeton("resume_mails"),
                            scopes_accordes=droits.SCOPES_ACCORDES)
    outils = Outils()
    with pytest.raises(AgentHorsScope):
        passerelle.appel_outil("executer_paiement",
                               {"montant": 10, "beneficiaire": "x"}, outils.executer_paiement)
    assert passerelle.jeton_revoque is True
    assert outils.paiements == []  # jamais exécuté


def test_sans_jeton_aucune_verification_de_scope(boite):
    # Rétrocompat : sans jeton de tâche, aucun contrôle de scope (comportement historique).
    passerelle = Passerelle("sess-libre", jetons_secrets(), boite)
    outils = Outils()
    r = passerelle.appel_outil("executer_paiement",
                               {"montant": 10, "beneficiaire": "x"}, outils.executer_paiement)
    assert r["statut"] == "simule"
