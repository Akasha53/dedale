"""Session détournée : le mail piégé fait suivre la consigne cachée, un canari est
touché, et les bons événements partent vers le backend."""

from __future__ import annotations

from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


def _agent_naif(session_id, boite):
    passerelle = Passerelle(session_id, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    return AgentInterne(
        session_id,
        cerveau=CerveauScripte(temperament="naif"),
        outils=Outils(),
        boite=boite,
        passerelle=passerelle,
    )


def test_session_detournee_touche_canari_et_emet_evenements(boite, backend):
    # L'analyste valide la reprise : on isole ici la détection, pas la décision.
    backend.fixer_etat("sess-2", "active")
    agent = _agent_naif("sess-2", boite)
    res = agent.executer("Résume mes mails de la semaine.")

    # Les deux canaris sont touchés : la consigne cachée (C-7A3F) et le faux secret (C-2B91).
    assert set(res["canaris_touches"]) == {"C-7A3F", "C-2B91"}
    assert res["incident"] is True

    # Le backend a reçu des événements leurre_touche portant les bons identifiants.
    touches = backend.evenements("leurre_touche")
    assert touches, "aucun leurre_touche reçu par le backend"
    ids = {e["leurre_id"] for e in touches}
    assert {"C-7A3F", "C-2B91"} <= ids

    # Les canaris ont été enregistrés au démarrage (si on les pousse).
    from orbis.agent import enregistrer_canaris

    assert enregistrer_canaris(boite) is True
    inventaire = backend.leurres()
    assert any(l["id"] == "C-2B91" for l in inventaire)


def test_canari_non_touche_par_agent_prudent(boite, backend):
    # Un agent prudent lit les mêmes mails mais ne suit pas la consigne : aucun canari.
    passerelle = Passerelle("sess-3", jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    agent = AgentInterne(
        "sess-3", cerveau=CerveauScripte("prudent"), outils=Outils(),
        boite=boite, passerelle=passerelle,
    )
    res = agent.executer("Résume mes mails de la semaine.")
    assert res["canaris_touches"] == []
    assert res["incident"] is False
