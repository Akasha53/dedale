"""Le « monde » que voit un générateur de trafic.

Un générateur ne connaît que ce monde : lire une page, suivre une route, appeler
un outil, faire entrer/sortir un agent. Le monde réalise chaque interaction de
deux façons selon le mode, sans que le générateur change :

- ``autonome`` : le banc synthétise les événements et les POST au backend
  lui-même, en servant les pages depuis ``SurfaceLocale``. Utile tant que
  ``leurres/`` et ``interne/`` n'existent pas, et pour développer le backend
  contre un trafic déjà étiqueté.
- ``surface`` : le banc tape en vrai sur ``leurres/`` (8701) et ``interne/``
  (8702) ; ce sont elles qui émettent les événements vers le backend. Le banc ne
  poste rien, il garde seulement le manifeste de ce qu'il a provoqué.

Dans les deux cas, le monde tient un manifeste par session (les événements que le
banc a produits ou provoqués, avec leur vérité terrain) : c'est la matière de la
vérification de cohérence et du résumé.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from . import evenement as ev
from .backend import Backend
from .surface import Reponse, SurfaceHTTP, SurfaceLocale


class Horloge:
    """Horloge virtuelle par session : avance au rythme des délais simulés.

    Les horodatages portent ainsi un vrai signal de cadence (un agent ~1,7 s, un
    humain lent et variable, un script très rapide) sans que la campagne attende
    en temps réel — donc reproductible à graine fixe.
    """

    def __init__(self, base: datetime | None = None):
        self.t = base or datetime.now().astimezone()

    def avancer(self, secondes: float) -> datetime:
        self.t = self.t + timedelta(seconds=secondes)
        return self.t

    def maintenant(self) -> datetime:
        return self.t


class Monde:
    def __init__(self, mode: str, surface: SurfaceLocale | SurfaceHTTP,
                 backend: Backend, campagne: str | None = None):
        if mode not in ("autonome", "surface"):
            raise ValueError(f"mode inconnu : {mode!r}")
        self.mode = mode
        self.surface = surface
        self.backend = backend
        # Identifiant de campagne, porté par chaque session_id (None : ancien format).
        self.campagne = campagne
        self.manifeste: dict[str, list[dict]] = {}
        # Réponses du backend, par session et dans l'ordre d'émission (mode autonome) :
        # consigne, classement renvoyé et latence de l'aller-retour HTTP.
        self.reponses: dict[str, list[dict]] = {}
        # Mode surface : résultat de la bibliothèque interne par session (passerelle réelle).
        self.resultats_internes: dict[str, dict] = {}
        self.horloge: Horloge | None = None

    def _moment(self) -> datetime | None:
        return self.horloge.maintenant() if self.horloge else None

    # --- journalisation interne -------------------------------------------
    def _noter(self, evenement: dict) -> None:
        self.manifeste.setdefault(evenement["session_id"], []).append(evenement)

    def _emettre(self, evenement: dict) -> str:
        """Réalise un événement. Renvoie la consigne du backend.

        En mode autonome, poste l'événement et lit la consigne. En mode surface,
        c'est la vraie surface qui a déjà émis l'équivalent : on ne fait que noter.
        """
        self._noter(evenement)
        if self.mode == "autonome":
            rep = self.backend.emettre(evenement)
            self.reponses.setdefault(evenement["session_id"], []).append({
                "consigne": rep.get("consigne", "aucune"),
                "classement": (rep.get("session") or {}).get("classement", "inconnu"),
                "latence_ms": self.backend.derniere_latence_ms,
            })
            return rep.get("consigne", "aucune")
        return "aucune"

    # --- interactions offertes au générateur ------------------------------
    def lire(self, session_id: str, verite: str, chemin: str,
             user_agent: str | None, *, source: str = "externe",
             surface_nom: str = "site", methode: str = "GET",
             details: dict[str, Any] | None = None) -> Reponse:
        """Lit une page. Émet un événement ``requete`` et renvoie la réponse."""
        evt = ev.evenement(source=source, surface=surface_nom, type="requete",
                           session_id=session_id, verite_terrain=verite,
                           user_agent=user_agent, methode=methode, chemin=chemin,
                           details=details, moment=self._moment())
        consigne = self._emettre(evt)
        if self.mode == "autonome":
            rep = self.surface.page(chemin, consigne)  # type: ignore[union-attr]
        else:
            rep = self.surface.page(chemin, session_id, user_agent, methode)  # type: ignore[call-arg]
            consigne = rep.consigne
        rep.consigne = consigne
        return rep

    def suivre_route(self, session_id: str, verite: str, chemin: str,
                     user_agent: str | None, leurre_id: str, *,
                     source: str = "externe", surface_nom: str = "site") -> Reponse:
        """Suit une route découverte (ex. un Disallow). Émet ``requete`` puis
        ``leurre_touche`` sur cette route."""
        rep = self.lire(session_id, verite, chemin, user_agent,
                        source=source, surface_nom=surface_nom)
        evt = ev.evenement(source=source, surface=surface_nom, type="leurre_touche",
                           session_id=session_id, verite_terrain=verite,
                           leurre_id=leurre_id, methode="GET", chemin=chemin,
                           user_agent=user_agent, moment=self._moment(),
                           details={"motif": "route cachée suivie après lecture"})
        self._emettre(evt)
        return rep

    def appeler_outil(self, session_id: str, verite: str, outil: str,
                      leurre_id: str, *, source: str = "externe",
                      surface_nom: str = "mcp") -> str:
        """Appelle un outil annoncé. Émet ``appel_outil`` puis ``leurre_touche``."""
        self._emettre(ev.evenement(
            source=source, surface=surface_nom, type="appel_outil",
            session_id=session_id, verite_terrain=verite, outil=outil,
            moment=self._moment(),
            details={"motif": "outil annoncé par une consigne cachée"}))
        return self._emettre(ev.evenement(
            source=source, surface=surface_nom, type="leurre_touche",
            session_id=session_id, verite_terrain=verite, leurre_id=leurre_id,
            outil=outil, moment=self._moment(),
            details={"motif": "faux outil appelé"}))

    def agent_entre(self, session_id: str, verite: str, details: dict[str, Any], *,
                    source: str, surface_nom: str) -> str:
        return self._emettre(ev.evenement(
            source=source, surface=surface_nom, type="entree_agent",
            session_id=session_id, verite_terrain=verite, details=details,
            moment=self._moment()))

    def agent_sort(self, session_id: str, verite: str, details: dict[str, Any], *,
                   source: str, surface_nom: str) -> str:
        return self._emettre(ev.evenement(
            source=source, surface=surface_nom, type="sortie_agent",
            session_id=session_id, verite_terrain=verite, details=details,
            moment=self._moment()))

    def toucher_canari(self, session_id: str, verite: str, canari_id: str,
                       outil: str, *, surface_nom: str = "mail") -> str:
        """Appel d'un outil sensible qui touche un canari interne."""
        self._emettre(ev.evenement(
            source="interne", surface="outil", type="appel_outil",
            session_id=session_id, verite_terrain=verite, outil=outil,
            moment=self._moment(),
            details={"motif": "consigne cachée d'un mail piégé suivie"}))
        return self._emettre(ev.evenement(
            source="interne", surface=surface_nom, type="leurre_touche",
            session_id=session_id, verite_terrain=verite, leurre_id=canari_id,
            outil=outil, moment=self._moment(),
            details={"motif": "canari touché"}))

    def etat_session(self, session_id: str) -> dict | None:
        return self.backend.session(session_id)
