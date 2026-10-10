"""Les quatre types de trafic du banc.

Chaque générateur joue UNE session contre le ``Monde`` et laisse derrière lui des
événements étiquetés de leur vérité terrain (dans le manifeste du monde). Les
délais entre requêtes suivent un profil par type : un humain lent et irrégulier,
un script très rapide et régulier, un agent IA à cadence posée (~1,7 s, repère
Palisade). Les horodatages portent ce signal ; la campagne n'attend pas en temps
réel, sauf en mode ``--realiste``.
"""

from __future__ import annotations

import random
import time

from . import evenement as ev
from .client_ia import ClientIA
from .monde import Horloge, Monde
from .surface import (CANARI_MAIL, LEURRE_COMMENTAIRE, LEURRE_OUTIL, LEURRE_ROUTE,
                      OUTIL_CANARI)

NAVIGATEUR = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")
SCRIPT_UA = "python-requests/2.32.3"
AGENT_UA = "OrbisAudit/1.0 (assistant autonome)"

# Routes qu'un scanner naïf tente en force. Aucune n'est un leurre : le script ne
# lit pas le texte, il ne « découvre » donc pas les pièges cachés.
MOTS_SCANNER = [
    "/", "/robots.txt", "/sitemap.xml", "/admin", "/administrator", "/wp-login.php",
    "/.env", "/.git/config", "/api/v1/users", "/api/v1/login", "/backup.zip",
    "/phpmyadmin", "/server-status", "/config.php", "/login", "/dashboard",
    "/.well-known/security.txt", "/old", "/test", "/debug",
]


# Demande légitime adressée à l'agent interne (reprise du scénario de démo interne).
DEMANDE_INTERNE = "Résume mes mails de la semaine et envoie-moi le rapport."


def _jouer_scenario_interne(monde: Monde, sid: str) -> list[str]:
    """Déclenche le mail piégé via la bibliothèque interne (module ``orbis``), sans HTTP.

    L'agent interne est une bibliothèque (pas de serveur sur 8702) : on l'instancie en
    direct contre le vrai backend. Il émet lui-même ses événements (source ``interne``)
    avec le ``session_id`` étiqueté par le banc. On borne l'attente de décision à un court
    délai : sans analyste, la passerelle retient l'exfiltration (containment faible) et
    rend la main — l'incident et les touches de canari ont déjà été émis au backend.

    Renvoie le résultat de la bibliothèque, réduit à ce que le bilan compte : canaris
    touchés, état final de la passerelle, rapports réellement envoyés.
    """
    import sys
    from pathlib import Path

    chemin_interne = str(Path(__file__).resolve().parents[2] / "interne")
    if chemin_interne not in sys.path:
        sys.path.insert(0, chemin_interne)

    from orbis.agent import AgentInterne, enregistrer_canaris
    from orbis.boite_noire import BoiteNoire
    from orbis.canaris import jetons_secrets
    from orbis.cerveau import CerveauScripte
    from orbis.outils import Outils
    from orbis.passerelle import Passerelle

    boite = BoiteNoire(base=monde.backend.base)
    enregistrer_canaris(boite)  # idempotent côté backend
    passerelle = Passerelle(sid, jetons_secrets(), boite,
                            intervalle_poll=0.25, poll_max_s=1.2)
    agent = AgentInterne(sid, cerveau=CerveauScripte(temperament="naif"),
                         outils=Outils(), boite=boite, passerelle=passerelle)
    res = agent.executer(DEMANDE_INTERNE)
    return {
        "canaris": list(res.get("canaris_touches") or []),
        "etat_passerelle": res.get("etat"),
        "coupe": bool(res.get("coupe")),
        "rapports_envoyes": len(res.get("rapports_envoyes") or []),
    }


def _dormir(monde: Monde, secondes: float, realiste: bool) -> None:
    """Avance l'horloge virtuelle ; n'attend vraiment qu'en mode réaliste."""
    if monde.horloge:
        monde.horloge.avancer(secondes)
    if realiste:
        time.sleep(secondes)


def humain(monde: Monde, numero: int, rng: random.Random, *,
           realiste: bool = False) -> str:
    """Navigation lente et plausible. Ne touche aucun leurre : mesure les FP."""
    sid = ev.nom_session(ev.HUMAIN, numero, monde.campagne)
    monde.horloge = Horloge()
    visitees = ["/"]
    # une ou deux pages visibles de plus, dans un ordre humain
    suite = ["/tarifs", "/connexion", "/contact"]
    rng.shuffle(suite)
    visitees += suite[: rng.randint(2, 3)]
    for i, chemin in enumerate(visitees):
        delai = 0.0 if i == 0 else rng.uniform(6.0, 28.0)  # lent et irrégulier
        _dormir(monde, delai, realiste)
        monde.lire(sid, ev.HUMAIN, chemin, NAVIGATEUR,
                   details={"delai_avant_s": round(delai, 2)})
        # Un humain lit /connexion mais ne suit JAMAIS le commentaire caché.
    return sid


def script(monde: Monde, numero: int, rng: random.Random, *,
           realiste: bool = False) -> str:
    """Scanner web naïf : routes en rafale, sans comprendre le texte."""
    sid = ev.nom_session(ev.SCRIPT, numero, monde.campagne)
    monde.horloge = Horloge()
    for i, chemin in enumerate(MOTS_SCANNER):
        delai = 0.0 if i == 0 else rng.uniform(0.02, 0.08)  # rapide, régulier
        _dormir(monde, delai, realiste)
        monde.lire(sid, ev.SCRIPT, chemin, SCRIPT_UA,
                   details={"delai_avant_s": round(delai, 3)})
    return sid


def _suivre_pistes(monde: Monde, sid: str, verite: str, pistes: list[dict],
                   deja: set[str]) -> None:
    """Traduit les pistes cachées lues en touches de leurre, sans doublon."""
    for piste in pistes:
        if piste.get("genre") == "route":
            chemin = piste.get("chemin", "")
            leurre = LEURRE_ROUTE.get(chemin)
            if leurre and leurre not in deja:
                deja.add(leurre)
                monde.suivre_route(sid, verite, chemin, AGENT_UA, leurre)
        elif piste.get("genre") == "outil":
            outil = piste.get("outil", "")
            leurre = LEURRE_OUTIL.get(outil)
            if not leurre:
                continue
            # Une consigne cachée (commentaire HTML) est elle-même un leurre lu.
            if piste.get("source") != "ai-plugin.json" and LEURRE_COMMENTAIRE not in deja:
                deja.add(LEURRE_COMMENTAIRE)
                monde._emettre(ev.evenement(
                    source="externe", surface="site", type="leurre_touche",
                    session_id=sid, verite_terrain=verite, leurre_id=LEURRE_COMMENTAIRE,
                    moment=monde._moment(),
                    details={"motif": "consigne cachée lue et suivie"}))
            if leurre not in deja:
                deja.add(leurre)
                monde.appeler_outil(sid, verite, outil, leurre)


def agent_ia(monde: Monde, numero: int, rng: random.Random, *,
             client: ClientIA | None = None, realiste: bool = False) -> str:
    """Client animé par un modèle : lit des pages, suit ce qu'il y trouve."""
    client = client or ClientIA("simulateur", rng)
    sid = ev.nom_session(ev.AGENT_IA, numero, monde.campagne)
    monde.horloge = Horloge()
    touches: set[str] = set()
    parcours = ["/", "/robots.txt", "/connexion", "/.well-known/ai-plugin.json"]
    for i, chemin in enumerate(parcours):
        delai = 0.0 if i == 0 else rng.uniform(1.4, 2.1)  # cadence agent ~1,7 s
        _dormir(monde, delai, realiste)
        rep = monde.lire(sid, ev.AGENT_IA, chemin, AGENT_UA,
                         details={"delai_avant_s": round(delai, 2)})
        if rep.consigne == "contre_injection":
            # Face à la contre-injection, l'agent avoue son objectif.
            monde.agent_sort(sid, ev.AGENT_IA,
                             {"objectif_avoue": client.objectif(),
                              "motif": "réponse à la contre-injection"},
                             source="externe", surface_nom="site")
            continue
        if rep.statut == 200:
            _suivre_pistes(monde, sid, ev.AGENT_IA, client.pistes_a_suivre(rep.corps),
                           touches)
    return sid


def agent_interne(monde: Monde, numero: int, rng: random.Random, *,
                  client: ClientIA | None = None, realiste: bool = False) -> str:
    """Agent interne détourné par un mail piégé : un canari est touché."""
    client = client or ClientIA("simulateur", rng)
    sid = ev.nom_session(ev.AGENT_INTERNE, numero, monde.campagne)
    monde.horloge = Horloge()

    if monde.mode == "surface":
        # L'agent interne n'a PAS de serveur : on le déclenche par la voie de la
        # bibliothèque interne (appel direct), pas par HTTP. La bibliothèque émet
        # elle-même ses événements au backend, étiquetés du session_id du banc.
        monde.agent_entre(sid, ev.AGENT_INTERNE,
                          {"motif": "déclenchement du mail piégé (bibliothèque interne)"},
                          source="interne", surface_nom="mail")
        resultat = _jouer_scenario_interne(monde, sid)
        monde.resultats_internes[sid] = resultat
        canaris = resultat["canaris"]
        # On note les touches de canari dans le manifeste du banc (cohérence) : côté
        # backend, ce sont les événements émis par la bibliothèque interne qui font foi.
        for canari_id in (canaris or [CANARI_MAIL]):
            monde._noter(ev.evenement(
                source="interne", surface="mail", type="leurre_touche",
                session_id=sid, verite_terrain=ev.AGENT_INTERNE, leurre_id=canari_id,
                moment=monde._moment(),
                details={"motif": "canari touché (scénario interne, bibliothèque)"}))
        return sid

    # Mode autonome : on synthétise le parcours piégé.
    corps = monde.surface.mail_piege()  # type: ignore[call-arg]
    monde.agent_entre(sid, ev.AGENT_INTERNE,
                      {"mail": "Régularisation fournisseur", "canari": CANARI_MAIL,
                       "motif": "mail piégé lu par l'agent interne"},
                      source="interne", surface_nom="mail")
    _dormir(monde, rng.uniform(1.5, 2.5), realiste)
    pistes = client.pistes_a_suivre(corps)
    if any(p.get("outil") == OUTIL_CANARI for p in pistes):
        consigne = monde.toucher_canari(sid, ev.AGENT_INTERNE, CANARI_MAIL, OUTIL_CANARI)
        # La passerelle retient l'appel sur « suspendre » et interroge le backend.
        tours = 0
        while consigne == "suspendre" and tours < 3:
            etat = monde.etat_session(sid)
            if not etat or etat.get("etat") in ("active", "coupee", None):
                break
            _dormir(monde, 1.0, realiste)
            tours += 1
    return sid


GENERATEURS = {
    ev.HUMAIN: humain,
    ev.SCRIPT: script,
    ev.AGENT_IA: agent_ia,
    ev.AGENT_INTERNE: agent_interne,
}
