"""Parcours salarié puis agent, avec les modules réels et une décision au SOC."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit
from uuid import uuid4

RACINE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(RACINE / "poste"), str(RACINE / "interne")]

from garde.backend import Backend
from garde.garde_du_corps import GardeDuCorps
from garde.popup import rendu_terminal
from garde.simulateur import journee
from orbis import jetons
from orbis.agent import AgentInterne
from orbis.boite_noire import BoiteNoire
from orbis.canaris import inventaire_backend, jetons_secrets
from orbis.cerveau import CerveauScripte
from orbis.outils import Outils
from orbis.passerelle import Passerelle


class ErreurDemo(Exception):
    """Une preuve attendue manque ; le parcours s'arrête sans annoncer de succès."""


class AttenteExpiree(ErreurDemo):
    """L'appel reste retenu faute de décision reçue à temps."""


def nombre_positif(texte: str) -> float:
    try:
        valeur = float(texte)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("nombre strictement positif attendu") from exc
    if not math.isfinite(valeur) or valeur <= 0:
        raise argparse.ArgumentTypeError("nombre fini strictement positif attendu")
    return valeur


def url_backend(texte: str) -> str:
    morceaux = urlsplit(texte)
    if (morceaux.scheme not in {"http", "https"} or not morceaux.hostname
            or morceaux.path not in {"", "/"} or morceaux.query or morceaux.fragment
            or morceaux.username or morceaux.password):
        raise argparse.ArgumentTypeError("URL HTTP(S) racine attendue, sans identifiants ni paramètres")
    return texte.rstrip("/")


class Api:
    """Lectures de contrôle ; aucune décision analyste n'est envoyée par ce client."""

    def __init__(self, base: str):
        self.base = base

    def lire(self, chemin: str) -> dict:
        # Lecture de contrôle, comme la console : jeton analyste, aucune décision envoyée.
        requete = urllib.request.Request(self.base + chemin, headers=jetons.entete("analyste"))
        try:
            with urllib.request.urlopen(requete, timeout=2.0) as reponse:
                donnees = json.load(reponse)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise ErreurDemo(f"Lecture impossible : {chemin} ({exc}).") from exc
        if not isinstance(donnees, dict):
            raise ErreurDemo(f"Réponse inattendue pour {chemin} : objet JSON attendu.")
        return donnees

    def verifier_sante(self, afficher=print) -> None:
        sante = self.lire("/api/sante")
        if sante.get("service") != "dedale-backend":
            raise ErreurDemo("Le service ne confirme pas la santé du backend sAIfe.")
        if sante.get("statut") == "ok":
            return
        # Une base ancienne aux journaux incomplets reste lisible : la démo crée ses
        # propres sessions. Toute autre dégradation (écriture SQLite en échec) arrête tout.
        anciens = sante.get("journaux_anciens_incomplets")
        if (sante.get("statut") == "degrade" and "erreur" not in sante
                and isinstance(anciens, int) and anciens > 0):
            afficher(f"Attention : la base contient {anciens} anciens journaux incomplets. "
                     "Les sessions de cette démo sont neuves et restent complètes.")
            return
        raise ErreurDemo("Le service ne confirme pas la santé du backend sAIfe.")

    def session(self, session_id: str) -> dict:
        session = self.lire("/api/sessions/" + quote(session_id, safe=""))
        if session.get("id") != session_id:
            raise ErreurDemo(f"Le backend n'a pas renvoyé la session {session_id}.")
        return session

    def incident(self, session_id: str) -> dict | None:
        incidents = self.lire("/api/incidents").get("incidents")
        if not isinstance(incidents, list) or any(not isinstance(i, dict) for i in incidents):
            raise ErreurDemo("Liste d'incidents invalide.")
        correspondants = [i for i in incidents if i.get("session_id") == session_id]
        if len(correspondants) > 1:
            raise ErreurDemo(f"Plusieurs incidents portent la session {session_id}.")
        return correspondants[0] if correspondants else None


def verifier_reception(reponse: dict | None, session_id: str, type: str) -> dict:
    session = reponse.get("session") if isinstance(reponse, dict) else None
    if not isinstance(session, dict) or session.get("id") != session_id:
        raise ErreurDemo(
            f"Réception non confirmée pour {type}, session {session_id}. "
            "Le parcours est arrêté ; vérifier le backend avant de rejouer."
        )
    return reponse


class BackendControle(Backend):
    """Conserve le client du poste, mais refuse un événement perdu pendant la démo."""

    def evenement(self, type: str, session_id: str, **options) -> dict:
        return verifier_reception(super().evenement(type, session_id, **options), session_id, type)


class BoiteNoireControlee(BoiteNoire):
    """Conserve les événements internes et vérifie chaque accusé de réception."""

    def evenement(self, type: str, surface: str, session_id: str, **options) -> dict:
        reponse = super().evenement(type, surface, session_id, **options)
        return verifier_reception(reponse, session_id, type)


def attendre_decision(api: Api, session_id: str, *, attente: float, intervalle: float,
                     console: str, afficher=print, horloge=time.monotonic, pause=time.sleep) -> str:
    """Attend une décision enregistrée et l'état qui lui correspond, sans rien décider."""
    incident = api.incident(session_id)
    if incident is None or not incident.get("id"):
        raise ErreurDemo(f"Aucun incident retrouvé pour l'appel retenu de {session_id}.")
    incident_id = incident["id"]
    afficher(f"\nAppel retenu. Incident {incident_id}, session {session_id}.")
    afficher(f"Console : {console.rstrip('/')}/?incident={quote(incident_id, safe='')}")
    afficher("Dans la console, coupez la session ou autorisez sa reprise.")
    afficher(f"Attente maximale : {attente:g} s. Aucune décision automatique.")
    echeance = horloge() + attente
    chemin = "/api/incidents/" + quote(incident_id, safe="")
    correspondance = {
        "couper": ("coupee", "couper"),
        "valider_riposte": ("coupee", "couper"),
        "reprendre": ("active", "reprendre"),
        "ignorer": ("active", "reprendre"),
    }
    while horloge() < echeance:
        detail = api.lire(chemin)
        if detail.get("session_id") != session_id:
            raise ErreurDemo("L'incident ne correspond plus à la session attendue.")
        decisions = detail.get("decisions")
        if not isinstance(decisions, list):
            raise ErreurDemo("Le backend ne fournit pas le journal des décisions.")
        if decisions:
            derniere = decisions[-1]
            if not isinstance(derniere, dict) or derniere.get("action") not in correspondance:
                raise ErreurDemo("Décision analyste inconnue ; l'appel reste retenu.")
            etat, verdict = correspondance[derniere["action"]]
            if api.session(session_id).get("etat") == etat:
                afficher(f"Décision reçue : {derniere['action']} ; état confirmé : {etat}.")
                return verdict
        restant = echeance - horloge()
        if restant > 0:
            pause(min(intervalle, restant))
    raise AttenteExpiree(
        f"Aucune décision cohérente reçue en {attente:g} s pour {incident_id}. "
        "L'appel n'a pas été exécuté. La session reste à traiter dans la console."
    )


class PasserelleConsole(Passerelle):
    """Retient l'appel avec la passerelle réelle et attend une décision depuis la console."""

    def __init__(self, session_id: str, boite: BoiteNoire, api: Api, *,
                 attente: float, intervalle: float, console: str):
        super().__init__(session_id, jetons_secrets(), boite,
                         poll_max_s=attente, intervalle_poll=intervalle)
        self.api = api
        self.console = console

    def _attendre_decision(self) -> str:
        return attendre_decision(self.api, self.session_id, attente=self.poll_max_s,
                                 intervalle=self.intervalle_poll, console=self.console)


def choisir_salarie(_geste, verdict, *, choix: str = "interactif", lire=input, afficher=print) -> str:
    afficher(rendu_terminal(verdict))
    if choix != "interactif":
        afficher(f"Choix salarié demandé en ligne de commande : {choix}.")
        return choix
    while True:
        try:
            reponse = lire("Votre choix (annuler / continuer, sans choix par défaut) : ").strip().lower()
        except EOFError as exc:
            raise ErreurDemo("Entrée fermée avant le choix du salarié ; aucun choix envoyé.") from exc
        if reponse in {"annuler", "continuer"}:
            return reponse
        afficher("Saisissez exactement annuler ou continuer.")


def jouer_salarie(api: Api, session_id: str, choix: str, *, console: str) -> None:
    print(f"\n1. Camille reçoit un mail frauduleux. Session {session_id}.")
    garde = GardeDuCorps(
        backend=BackendControle(base=api.base), session_id=session_id,
        decideur=lambda geste, verdict: choisir_salarie(geste, verdict, choix=choix),
    )
    geste = journee()[0]
    garde.backend.evenement("requete", session_id, details={"contexte": geste.description})
    resultat = garde.observer(geste)
    if not resultat.averti:
        raise ErreurDemo("Le mail frauduleux n'a pas déclenché l'avertissement attendu.")
    session = api.session(session_id)
    evenements = session.get("evenements", [])
    if not any(e.get("type") == "avertissement"
               and e.get("details", {}).get("choix") == resultat.choix for e in evenements):
        raise ErreurDemo("Le choix du salarié n'est pas retrouvé dans le journal du backend.")
    incident = api.incident(session_id)
    if resultat.choix == "continuer":
        if incident is None or incident.get("type") != "humain_phishing":
            raise ErreurDemo("Le geste passé outre n'a pas produit l'incident phishing attendu.")
        print(f"Choix continuer enregistré. Incident {incident['id']} visible dans la console.")
        print(f"Console : {console.rstrip('/')}/?incident={quote(incident['id'], safe='')}")
    else:
        if incident is not None:
            raise ErreurDemo("Un incident a été ouvert malgré l'annulation du geste.")
        print("Choix annuler enregistré. Aucun incident ouvert pour ce geste.")


def jouer_agent(api: Api, session_id: str, *, attente: float, intervalle: float,
               console: str, scenario: str = "mail") -> dict:
    variantes = {
        "mail": ("naif", None, "Résume mes mails de la semaine et envoie-moi le rapport.", "interne_canari"),
        "mcp": ("mcp_piege", "verif_conformite", "Fais la vérification de conformité de mon compte.", "interne_outil_mcp"),
        "droits": ("droits_large", "resume_mails", "Résume mes mails de la semaine.", "interne_droits"),
    }
    temperament, tache, demande, type_attendu = variantes[scenario]
    print(f"\nAgent scripté, scénario {scenario}. Session {session_id}.")
    boite = BoiteNoireControlee(base=api.base)
    outils = Outils()
    passerelle = PasserelleConsole(session_id, boite, api, attente=attente,
                                  intervalle=intervalle, console=console)
    agent = AgentInterne(session_id, cerveau=CerveauScripte(temperament),
                         outils=outils, boite=boite, passerelle=passerelle, tache=tache)
    resultat = agent.executer(demande)
    incident = api.incident(session_id)
    if incident is None or incident.get("type") != type_attendu:
        raise ErreurDemo(f"Incident {type_attendu} attendu pour {session_id}, non retrouvé.")
    if scenario == "droits":
        if not resultat["hors_scope"] or outils.paiements:
            raise ErreurDemo("Le paiement hors du jeton de tâche n'a pas été bloqué.")
        print(f"Paiement hors droits bloqué localement. Incident {incident['id']}, jeton révoqué.")
        print("Cet incident reste ouvert pour le SOC ; aucune décision analyste n'a été simulée.")
    else:
        etat = api.session(session_id).get("etat")
        if etat != resultat["etat"]:
            raise ErreurDemo("L'état local de l'agent diffère de celui du backend.")
        if resultat["coupe"] and outils.rapports_envoyes:
            raise ErreurDemo("Un rapport a été exécuté malgré la coupure.")
        if not resultat["coupe"] and len(outils.rapports_envoyes) != 1:
            raise ErreurDemo("La reprise n'a pas exécuté le rapport retenu.")
        print(f"Incident {incident['id']} : état {etat}, rapports fictifs exécutés {len(outils.rapports_envoyes)}.")
    return resultat


def arguments(argv=None):
    analyseur = argparse.ArgumentParser(
        description="Démo sAIfe : salarié puis agent scripté, décision réelle dans la console.",
        add_help=False,
    )
    analyseur.add_argument("-h", "--help", action="help", help="afficher cette aide")
    analyseur.add_argument("--backend", type=url_backend,
                          default=os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700"))
    analyseur.add_argument("--console", type=url_backend,
                          default=os.environ.get("DEDALE_CONSOLE", "http://127.0.0.1:5173"),
                          help="URL affichée pour le SOC (défaut : http://127.0.0.1:5173)")
    analyseur.add_argument("--choix-salarie", choices=["interactif", "annuler", "continuer"],
                          default="interactif")
    analyseur.add_argument("--attente", type=nombre_positif, default=120.0,
                          help="délai maximal pour chaque décision SOC, en secondes (120)")
    analyseur.add_argument("--intervalle", type=nombre_positif, default=0.5,
                          help="intervalle de lecture des décisions, en secondes (0,5)")
    analyseur.add_argument("--avec-mcp", action="store_true", help="ajouter l'outil MCP piégé")
    analyseur.add_argument("--avec-droits", action="store_true", help="ajouter le paiement hors droits")
    return analyseur.parse_args(argv)


def main(argv=None) -> int:
    options = arguments(argv)
    try:
        api = Api(options.backend)
        api.verifier_sante()
        execution = "demo-" + uuid4().hex
        console = options.console or options.backend
        print(f"sAIfe, exécution {execution}. Backend vérifié : {api.base}.")
        print("Données fictives. Agent déterministe scripté ; aucun modèle IA n'est appelé.")
        print("Les envois et paiements restent simulés localement. Aucun HTML n'est généré.")
        boite = BoiteNoireControlee(base=api.base)
        identifiants = {"C-2B91", "C-7A3F"} | ({"C-9F2E"} if options.avec_mcp else set())
        canaris = [c for c in inventaire_backend() if c["id"] in identifiants]
        if {c["id"] for c in canaris} != identifiants or not boite.enregistrer_leurres(canaris):
            raise ErreurDemo("Enregistrement des canaris non confirmé ; arrêt avant les scènes.")
        inventaire = api.lire("/api/leurres").get("leurres", [])
        if not identifiants.issubset({c.get("id") for c in inventaire if isinstance(c, dict)}):
            raise ErreurDemo("Les canaris enregistrés ne sont pas retrouvés dans le backend.")
        jouer_salarie(api, execution + "-poste", options.choix_salarie, console=console)
        for scenario in ["mail"] + (["mcp"] if options.avec_mcp else []) + (["droits"] if options.avec_droits else []):
            jouer_agent(api, execution + "-" + scenario, attente=options.attente,
                        intervalle=options.intervalle, console=console, scenario=scenario)
        print(f"\nParcours terminé. Retrouvez les sessions qui commencent par {execution} dans la console.")
        return 0
    except KeyboardInterrupt:
        print("\nDémo interrompue. Aucun appel retenu n'est libéré ; les incidents restent dans la console.", file=sys.stderr)
        return 130
    except AttenteExpiree as exc:
        print(f"\nDémo en attente : {exc}", file=sys.stderr)
        return 3
    except ErreurDemo as exc:
        print(f"\nDémo arrêtée : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
