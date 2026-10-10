"""Fil des agents et correctif en un clic, côté passerelle.

Chaque appel d'outil part au backend avec son verdict (autorise, retenu, refuse) et une raison
courte. Un droit retiré par l'analyste est appris dans les réponses du backend : l'outil qui
l'exige est refusé sans être exécuté, dans la session en cours comme dans les suivantes du
même agent fictif.
"""

from __future__ import annotations

import threading
import time

import pytest

from orbis import droits, jury
from orbis.backend_simule import BackendSimule
from orbis.boite_noire import BoiteNoire
from orbis.canaris import jetons_secrets
from orbis.outils import Outils
from orbis.passerelle import AGENT_DEFAUT, AgentHorsScope, Passerelle


@pytest.fixture
def fidele():
    b = BackendSimule(suspendre_a_l_incident=True).demarrer()
    try:
        yield b
    finally:
        b.arreter()


def _protegee(sid, base, **kw):
    return Passerelle(sid, jetons_secrets(), BoiteNoire(base=base), intervalle_poll=0.02,
                      poll_max_s=kw.pop("poll_max_s", 3.0),
                      jeton_tache=droits.emettre_jeton("rapport_paiements"),
                      scopes_accordes=droits.SCOPES_ACCORDES, retenir_hors_scope=True,
                      decision_fraiche=True, **kw)


def _verdicts(backend, sid):
    return [(e["type"], e.get("outil"), e["details"].get("verdict"))
            for e in backend.evenements() if e.get("session_id") == sid
            and e["details"].get("verdict")]


def test_appel_autorise_porte_son_verdict(boite, backend):
    p = Passerelle("sess-fil", jetons_secrets(), boite,
                   jeton_tache=droits.emettre_jeton("resume_mails"),
                   scopes_accordes=droits.SCOPES_ACCORDES)
    p.entree_agent("Résume mes mails.")
    p.appel_outil("lire_mail", {}, Outils().lire_mail)
    entree = backend.evenements("entree_agent")[0]
    assert entree["details"]["agent"] == AGENT_DEFAUT
    appel = backend.evenements("appel_outil")[0]
    assert appel["details"]["verdict"] == "autorise"
    assert appel["details"]["raison"] == "droit mail:lire dans le jeton"


def test_appel_hors_jeton_refuse_porte_son_verdict(boite, backend):
    p = Passerelle("sess-hs", jetons_secrets(), boite,
                   jeton_tache=droits.emettre_jeton("resume_mails"),
                   scopes_accordes=droits.SCOPES_ACCORDES)
    with pytest.raises(AgentHorsScope):
        p.appel_outil("executer_paiement", {"montant": 10, "beneficiaire": "x"},
                      Outils().executer_paiement)
    appel = next(e for e in backend.evenements("appel_outil") if e["details"].get("violation_droits"))
    assert appel["details"]["verdict"] == "refuse"
    assert "paiement:executer" in appel["details"]["raison"]


def test_scenario_jury_verdicts_dans_l_ordre(fidele):
    c = jury.jouer(fidele.base, "reprendre", session_id="jury-fil", delai_analyste=0.05,
                   poll_max_s=5.0, intervalle=0.02)
    assert c["rapports_envoyes"] == 0
    assert _verdicts(fidele, "jury-fil") == [
        ("appel_outil", "chercher_document", "autorise"),
        ("appel_outil", "lire_coffre", "retenu"),
        ("riposte", "lire_coffre", "autorise"),       # libéré une fois par l'analyste
        ("appel_outil", "envoyer_rapport", "retenu"),
        ("riposte", "envoyer_rapport", "refuse"),     # annulé : l'analyste coupe
        ("riposte", "envoyer_rapport", "refuse"),     # relance après coupure
    ]


def test_droit_retire_refuse_des_la_premiere_session_suivante(fidele):
    fidele.retirer_droit(AGENT_DEFAUT, "coffre:lire")
    outils = Outils()
    p = _protegee("sess-apres-correctif", fidele.base)
    p.entree_agent("Prépare le rapport des paiements.")
    assert "coffre:lire" in p.droits_retires  # appris dans la réponse à l'entrée
    assert "coffre:lire" not in p.scopes_accordes
    res = p.appel_outil("lire_coffre", {"entree": "sauvegarde"}, outils.lire_coffre)
    assert res["droit"] == "coffre:lire" and "erreur" in res
    assert outils.coffre_lectures == []
    refus = [e for e in fidele.evenements("appel_outil") if e["details"].get("droit_retire")]
    assert refus and refus[0]["details"]["verdict"] == "refuse"
    # Aucun incident : l'analyste a déjà tranché en retirant le droit.
    assert not any(e["details"].get("violation_droits") for e in fidele.evenements())
    assert fidele.incidents() == []


def test_droit_retire_sans_evenement_intermediaire(fidele):
    """Le retrait arrive après la dernière réponse : la passerelle relit la session avant
    un appel hors jeton et refuse quand même."""
    outils = Outils()
    p = _protegee("sess-relue", fidele.base)
    p.entree_agent("Prépare le rapport des paiements.")
    fidele.retirer_droit(AGENT_DEFAUT, "coffre:lire")
    res = p.appel_outil("lire_coffre", {"entree": "sauvegarde"}, outils.lire_coffre)
    assert "erreur" in res and outils.coffre_lectures == []


def test_droit_retire_pendant_l_attente_la_reprise_n_execute_pas(fidele):
    sid = "sess-attente"
    outils = Outils()
    p = _protegee(sid, fidele.base)
    p.entree_agent("Prépare le rapport des paiements.")

    def analyste():
        fin = time.monotonic() + 3
        while time.monotonic() < fin:
            if any(e["details"].get("retenu") for e in fidele.evenements("appel_outil")):
                break
            time.sleep(0.02)
        fidele.retirer_droit(AGENT_DEFAUT, "coffre:lire")
        inc = fidele.incidents()[0]
        fidele.etat.decider(inc["id"], "reprendre", "analyste-test")

    fil = threading.Thread(target=analyste, daemon=True)
    fil.start()
    res = p.appel_outil("lire_coffre", {"entree": "sauvegarde"}, outils.lire_coffre)
    fil.join(timeout=3)
    assert "erreur" in res
    assert outils.coffre_lectures == []  # « reprendre » n'a pas rendu le droit
    resultat = [e for e in fidele.evenements("riposte") if e["details"].get("maillon") == "resultat"]
    assert resultat[-1]["details"]["action"] == "appel_refuse"
    assert "retiré" in resultat[-1]["details"]["raison"]


def test_autre_agent_non_touche(fidele):
    fidele.retirer_droit(AGENT_DEFAUT, "coffre:lire")
    p = _protegee("sess-autre-agent", fidele.base, agent="orbis-compta")
    p.entree_agent("Prépare le rapport des paiements.")
    assert p.droits_retires == set()
