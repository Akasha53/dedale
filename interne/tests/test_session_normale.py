"""Session normale : demande légitime, aucun canari touché, rien ne se déclenche."""

from __future__ import annotations

from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


def _agent(session_id, boite, temperament):
    passerelle = Passerelle(session_id, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    return AgentInterne(
        session_id,
        cerveau=CerveauScripte(temperament=temperament),
        outils=Outils(),
        boite=boite,
        passerelle=passerelle,
    )


def test_session_normale_sans_alerte(boite, backend):
    agent = _agent("sess-1", boite, "prudent")
    res = agent.executer("Résume mes mails de la semaine.")

    assert res["canaris_touches"] == []
    assert res["incident"] is False
    assert res["jeton_revoque"] is False
    assert res["coupe"] is False
    assert len(res["rapports_envoyes"]) == 1

    # Le rapport envoyé ne contient aucun lien externe ni faux secret.
    contenu = res["rapports_envoyes"][0]["contenu"]
    assert "attacker.example" not in contenu
    assert "ORBISPAY-CANARY" not in contenu

    # Le backend n'a reçu aucun leurre_touche.
    assert backend.evenements("leurre_touche") == []
    # Mais il a bien vu l'entrée, des appels d'outil et la sortie.
    types = {e["type"] for e in backend.evenements()}
    assert {"entree_agent", "appel_outil", "sortie_agent"} <= types
