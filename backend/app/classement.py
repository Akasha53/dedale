"""Tri d'une session en humain / script / agent IA.

Chaque signal est journalisé avec sa raison en clair : le score n'est jamais une boîte noire.
Le score est une somme pondérée de signaux présents, bornée à [0, 1]. La décision combine deux
familles de signaux :

- signaux « IA » (seul un modèle de langage les produit) : a suivi une consigne cachée, a
  répondu à une contre-injection, a enchaîné lecture d'un document puis action sur une route
  qui n'y était que décrite ;
- signaux d'« automatisation » (machine, pas forcément IA) : cadence régulière proche des
  ~1,7 s mesurés par Palisade, forme de requête automatisée (user-agent outil, en-têtes).

Un signal « navigateur humain » tire la décision vers `humain` et retient le classement.
"""

from __future__ import annotations

from statistics import mean, pstdev

from . import config

# user-agents d'outils automatisés courants.
import re

_UA_OUTIL = re.compile(
    r"(python-requests|httpx|aiohttp|curl|wget|libwww|go-http|java/|okhttp|scrapy|"
    r"node-fetch|axios|headless|puppeteer|playwright|selenium|bot\b|spider|crawler)",
    re.IGNORECASE,
)
_UA_NAVIGATEUR = re.compile(r"(Mozilla/5\.0.*(Gecko|AppleWebKit|Chrome|Safari|Firefox|Edg))", re.IGNORECASE)

POIDS = {
    "consigne_cachee_suivie": 0.45,
    "reponse_contre_injection": 0.35,
    "lecture_puis_action": 0.25,
    "cadence_machine": 0.20,
    "forme_automatisee": 0.15,
}


def _cadence(delais: list[float]) -> tuple[bool, bool, str]:
    """(machine, humaine, raison) à partir des intervalles entre requêtes (secondes)."""
    if len(delais) < 2:
        return False, False, "Pas assez de requêtes pour juger la cadence (< 2 intervalles)"
    m = mean(delais)
    ecart = pstdev(delais)
    cv = ecart / m if m > 0 else 0.0
    raison = (
        f"intervalle moyen {m:.2f} s, écart-type {ecart:.2f} s "
        f"(repère Palisade {config.PALISADE_DELAI} s pour un agent)"
    )
    # Machine : rythme serré et régulier (faible coefficient de variation).
    if m <= 3.0 and cv < 0.6:
        return True, False, "Cadence régulière et rapide — " + raison
    # Humain : rythme lent ou très irrégulier.
    if m > 6.0 or cv > 1.2:
        return False, True, "Cadence lente ou irrégulière, typiquement humaine — " + raison
    return False, False, "Cadence intermédiaire, non concluante — " + raison


def _forme(user_agents: set[str]) -> tuple[bool, bool, str]:
    """(automatisee, navigateur, raison) d'après les user-agents vus sur la session."""
    uas = [u for u in user_agents if u]
    if not uas:
        return True, False, "Aucun user-agent transmis — comportement typiquement automatisé"
    joint = " | ".join(uas)
    if any(_UA_OUTIL.search(u) for u in uas):
        return True, False, f"User-agent d'outil automatisé détecté : {joint}"
    if all(_UA_NAVIGATEUR.search(u) for u in uas):
        return False, True, f"User-agent de navigateur : {joint}"
    return False, False, f"User-agent non concluant : {joint}"


def classer(sess) -> tuple[str, float, list[dict]]:
    """Retourne (classement, score, signaux). `sess` est un store.Session."""
    signaux: list[dict] = []

    def ajouter(code: str, present: bool, categorie: str, raison: str) -> None:
        signaux.append(
            {
                "code": code,
                "present": present,
                "poids": POIDS.get(code, 0.0),
                "categorie": categorie,
                # `libelle` et `raison` portent la même explication en clair (exigence « jamais
                # une boîte noire ») ; `libelle` est le nom lu par la console.
                "libelle": raison,
                "raison": raison,
            }
        )

    # --- Signaux IA ---
    ajouter(
        "consigne_cachee_suivie",
        sess.flag_consigne_cachee,
        "ia",
        (
            f"A suivi une consigne cachée (leurre {sess.consigne_leurre_id}) que seul un programme "
            "lisant le texte exécuterait"
        )
        if sess.flag_consigne_cachee
        else "Aucune consigne cachée suivie",
    )
    ajouter(
        "reponse_contre_injection",
        sess.flag_contre_injection_reponse,
        "ia",
        "A répondu à une contre-injection en exposant son objectif ou ses consignes"
        if sess.flag_contre_injection_reponse
        else "Pas de réponse à une contre-injection",
    )
    ajouter(
        "lecture_puis_action",
        sess.flag_lecture_action,
        "ia",
        "A lu un document/mail puis agi sur une route qui n'y était que décrite"
        if sess.flag_lecture_action
        else "Pas d'enchaînement lecture puis action sur une route découverte",
    )

    # --- Signaux d'automatisation ---
    machine, humaine_cadence, raison_cadence = _cadence(sess.delais)
    ajouter("cadence_machine", machine, "automatisation", raison_cadence)

    auto_forme, navigateur, raison_forme = _forme(sess.user_agents)
    ajouter("forme_automatisee", auto_forme, "automatisation", raison_forme)

    # Signal humain (informe mais ne compte pas dans le score ; il retient la décision).
    raison_h = raison_forme if navigateur else raison_cadence
    signaux.append(
        {
            "code": "forme_navigateur",
            "present": navigateur or humaine_cadence,
            "poids": 0.0,
            "categorie": "humain",
            "libelle": raison_h,
            "raison": raison_h,
        }
    )

    score = round(min(1.0, sum(s["poids"] for s in signaux if s["present"])), 3)

    indice_ia = sess.flag_consigne_cachee or sess.flag_contre_injection_reponse or sess.flag_lecture_action
    indice_auto = machine or auto_forme

    if indice_ia and score >= config.SEUIL_AGENT_IA:
        classement = "agent_ia"
    elif indice_auto and not navigateur and score >= config.SEUIL_SCRIPT:
        classement = "script"
    elif (navigateur or humaine_cadence) and not indice_auto and not indice_ia:
        classement = "humain"
    else:
        classement = "inconnu"

    return classement, score, signaux
