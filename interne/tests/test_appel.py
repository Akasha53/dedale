"""V1 — Appels. L'agent interne traite des transcriptions d'appels. Une transcription
piégée cache une consigne (EchoLeak sur un appel) ; l'agent détourné la suit → canari
C-4D17 touché. Un appel sain ne déclenche rien. La décision humaine coupe ou valide."""

from __future__ import annotations

from orbis import mcp
from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


def _agent(session_id, boite, temperament, tache="triage_appels"):
    passerelle = Passerelle(session_id, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    return AgentInterne(
        session_id,
        cerveau=CerveauScripte(temperament=temperament),
        outils=Outils(),
        boite=boite,
        passerelle=passerelle,
        tache=tache,
    )


def test_chercher_appel_lit_les_transcriptions():
    appels = Outils().chercher_appel("rdv")
    assert any(a["id"] == "appel_rdv_8091" for a in appels)
    assert all("attacker.example" not in a["transcription"] or a["id"] == "appel_rdv_8091" for a in appels)


def test_appel_sain_ne_declenche_rien(boite, backend):
    agent = _agent("sess-appel-sain", boite, "appel_sain")
    res = agent.executer("Trie et résume mes appels.")

    assert res["canaris_touches"] == []
    assert res["incident"] is False
    assert res["jeton_revoque"] is False
    assert backend.evenements("leurre_touche") == []
    # Le rapport ne contient aucun lien externe.
    assert all("attacker.example" not in r["contenu"] for r in res["rapports_envoyes"])


def test_appel_piege_touche_le_canari_appel(boite, backend):
    # L'analyste valide la reprise : on isole la détection.
    backend.fixer_etat("sess-appel-piege", "active")
    agent = _agent("sess-appel-piege", boite, "appel_piege")
    res = agent.executer("Trie et résume mes appels.")

    assert res["canaris_touches"] == ["C-4D17"]      # attribution à la source appel, pas au mail
    assert res["incident"] is True
    ids = {e["leurre_id"] for e in backend.evenements("leurre_touche")}
    assert "C-4D17" in ids
    assert "C-7A3F" not in ids                        # pas de confusion avec le canari mail


def test_appel_piege_coupe_par_analyste(boite, backend):
    # L'analyste COUPE : l'exfiltration est retenue, aucun rapport externe n'est envoyé.
    backend.fixer_etat("sess-appel-coupee", "coupee")
    agent = _agent("sess-appel-coupee", boite, "appel_piege")
    res = agent.executer("Trie et résume mes appels.")

    assert res["coupe"] is True
    assert "C-4D17" in res["canaris_touches"]
    assert res["rapports_envoyes"] == []             # l'appel d'exfiltration n'a jamais eu lieu
