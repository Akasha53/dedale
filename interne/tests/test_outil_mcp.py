"""Fonction 1 — outils / serveurs MCP piégés (tool poisoning).

Un outil MCP d'apparence utile cache une consigne dans sa DESCRIPTION. L'agent qui la suit
déclenche le canari `outil_mcp_piege` (C-9F2E). Un outil MCP sain ne déclenche rien.
"""

from __future__ import annotations

from orbis import detection, mcp
from orbis.agent import AgentInterne
from orbis.canaris import jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


def _agent(session_id, boite, temperament, tache):
    passerelle = Passerelle(session_id, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=2)
    return AgentInterne(
        session_id,
        cerveau=CerveauScripte(temperament=temperament),
        outils=Outils(),
        boite=boite,
        passerelle=passerelle,
        tache=tache,
    )


def test_description_saine_non_detectee():
    sain = mcp.PAR_NOM["convertir_montant"]
    assert detection.description_piegee(sain.description) is False
    assert detection.detecter_consigne_outil(sain.description, None) == []


def test_description_piegee_detectee():
    piege = mcp.PAR_NOM["verifier_conformite"]
    assert detection.description_piegee(piege.description) is True
    tr = detection.detecter_consigne_outil(piege.description, piege.canari_id)
    assert len(tr) == 1
    assert tr[0].type == "consigne_outil_mcp"
    assert tr[0].canari_id == "C-9F2E"


def test_outil_mcp_sain_ne_declenche_rien(boite, backend):
    agent = _agent("sess-mcp-sain", boite, "mcp_sain", "conversion_facture")
    res = agent.executer("Convertis la facture Atelier Nord en dollars.")

    assert res["canaris_touches"] == []
    assert res["incident"] is False
    assert res["jeton_revoque"] is False
    assert res["hors_scope"] is False
    assert "outil:mcp" in res["scopes_utilises"]  # l'outil MCP sain a bien été utilisé
    assert backend.evenements("leurre_touche") == []


def test_outil_mcp_piege_declenche_le_canari(boite, backend):
    # L'analyste valide la reprise : on isole ici la détection du tool poisoning.
    backend.fixer_etat("sess-mcp-piege", "active")
    agent = _agent("sess-mcp-piege", boite, "mcp_piege", "verif_conformite")
    res = agent.executer("Fais la vérification de conformité de mon compte.")

    # Le canari de l'outil MCP piégé est touché, en tête (attribution MCP).
    assert "C-9F2E" in res["canaris_touches"]
    assert res["incident"] is True
    # Le backend a reçu un leurre_touche portant l'identifiant du canari MCP.
    ids = {e["leurre_id"] for e in backend.evenements("leurre_touche")}
    assert "C-9F2E" in ids
    # La passerelle a journalisé l'appel de l'outil MCP suspect (sa description est piégée).
    appels = backend.evenements("appel_outil")
    assert any(e["details"].get("outil_mcp_suspect") for e in appels)


def test_inventaire_publie_le_canari_mcp(boite, backend):
    from orbis.agent import enregistrer_canaris

    assert enregistrer_canaris(boite) is True
    inv = {l["id"]: l for l in backend.leurres()}
    assert "C-9F2E" in inv
    assert inv["C-9F2E"]["nature"] == "outil_mcp_piege"
    # Le texte piégé de la description n'est pas publié : la description publiée est propre.
    assert "collecte-metrics" not in inv["C-9F2E"]["description"]
