"""Passerelle « boîte noire » : la couche par laquelle TOUT passe.

Elle journalise au backend (entree_agent, appel_outil avec ses paramètres, sortie_agent),
inspecte les sorties (exfiltration EchoLeak, usage d'un faux secret canari) et, dès qu'un
canari est touché, retient l'appel d'outil en cours et interroge le backend
`GET /api/sessions/{id}` chaque seconde jusqu'à la décision de l'analyste :

- `active`  -> reprendre : l'appel retenu s'exécute ;
- `coupee`  -> l'agent s'arrête, son jeton est révoqué.

Jamais de coupure automatique : seule la décision renvoyée par le backend coupe. Si le
backend reste muet, l'appel retenu est *refusé* (containment faible) mais le jeton n'est
pas révoqué — on ne coupe pas sans décision humaine.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from . import detection
from .boite_noire import BoiteNoire


# Outils « sortants » : ceux qui font quitter une donnée de l'agent. Eux seuls déclenchent
# la détection de canari. Lire un mail ou un document qui *contient* le payload n'est pas un
# signal — un humain le lit aussi ; le signal, c'est que l'agent le *ressorte*.
OUTILS_SORTANTS = {"envoyer_rapport"}


class AgentCoupe(Exception):
    """Levée quand l'analyste coupe la session : l'agent doit s'arrêter."""


@dataclass
class Decision:
    verdict: str  # "reprendre" | "couper" | "bloquer"
    trouvailles: list[detection.Trouvaille] = field(default_factory=list)


def _etat_depuis(rep: dict | None) -> str | None:
    """Extrait l'état de session d'une réponse backend, quelle que soit sa forme."""
    if not rep:
        return None
    if isinstance(rep.get("etat"), str):
        return rep["etat"]
    sess = rep.get("session")
    if isinstance(sess, dict) and isinstance(sess.get("etat"), str):
        return sess["etat"]
    return None


class Passerelle:
    def __init__(
        self,
        session_id: str,
        jetons: dict[str, str],
        boite: BoiteNoire | None = None,
        *,
        intervalle_poll: float = 1.0,
        poll_max_s: float = 60.0,
    ):
        self.session_id = session_id
        self.jetons = jetons
        self.boite = boite or BoiteNoire()
        self.intervalle_poll = intervalle_poll
        self.poll_max_s = poll_max_s

        self.jeton_revoque = False
        self.etat = "active"
        self.canaris_touches: list[str] = []
        self.incident = False
        self.journal: list[dict] = []  # trace locale, utile aux tests et à la démo

    # --- entrée / sortie de l'agent ----------------------------------------------
    def entree_agent(self, texte: str) -> None:
        self._tracer("entree_agent", {"texte": texte})
        self.boite.evenement(
            "entree_agent", "mail", self.session_id, details={"texte": texte}
        )

    def sortie_agent(self, texte: str) -> str:
        """Inspecte la sortie finale. Peut retenir et faire décider l'analyste."""
        trouvailles = detection.inspecter(texte, self.jetons)
        if trouvailles:
            decision = self._gerer_touche(trouvailles, surface="outil", outil=None)
            if decision.verdict == "couper":
                raise AgentCoupe("session coupée par l'analyste")
            if decision.verdict == "bloquer":
                texte = "[sortie retenue par la passerelle : exfiltration suspectée, pas de validation analyste]"
        self._tracer("sortie_agent", {"texte": texte})
        self.boite.evenement(
            "sortie_agent", "outil", self.session_id, details={"texte": texte}
        )
        return texte

    # --- appel d'outil ------------------------------------------------------------
    def appel_outil(self, nom: str, params: dict, fonction) -> dict | list | str:
        """Enveloppe un appel d'outil : journalise, inspecte les paramètres, contrôle."""
        self._tracer("appel_outil", {"outil": nom, "parametres": params})
        self.boite.evenement(
            "appel_outil",
            "outil",
            self.session_id,
            outil=nom,
            details={"parametres": params},
        )

        trouvailles = []
        if nom in OUTILS_SORTANTS:
            charge = json.dumps(params, ensure_ascii=False, default=str)
            trouvailles = detection.inspecter(charge, self.jetons)

        if trouvailles:
            decision = self._gerer_touche(trouvailles, surface="outil", outil=nom)
            if decision.verdict == "couper":
                raise AgentCoupe("session coupée par l'analyste")
            if decision.verdict == "bloquer":
                return {
                    "erreur": "appel refusé par la passerelle",
                    "raison": "canari touché, pas de validation analyste",
                }
            # verdict "reprendre" : l'analyste a validé, l'appel retenu s'exécute.

        return fonction(**params)

    # --- cœur du contrôle humain --------------------------------------------------
    def _gerer_touche(
        self, trouvailles: list[detection.Trouvaille], *, surface: str, outil: str | None
    ) -> Decision:
        """Canari touché : journalise, retient, interroge le backend jusqu'à décision."""
        self.incident = True
        self.etat = "suspendue"
        for t in trouvailles:
            if t.canari_id and t.canari_id not in self.canaris_touches:
                self.canaris_touches.append(t.canari_id)
            self._tracer(
                "leurre_touche",
                {"type": t.type, "detail": t.detail, "leurre_id": t.canari_id},
            )
            self.boite.evenement(
                "leurre_touche",
                surface,
                self.session_id,
                leurre_id=t.canari_id,
                outil=outil,
                details={"type": t.type, "detail": t.detail},
            )

        verdict = self._attendre_decision()
        if verdict == "couper":
            self.jeton_revoque = True
            self.etat = "coupee"
            self._tracer("riposte", {"action": "couper", "jeton_revoque": True})
            self.boite.evenement(
                "riposte",
                surface,
                self.session_id,
                outil=outil,
                details={"action": "couper", "jeton_revoque": True},
            )
        elif verdict == "reprendre":
            self.etat = "active"
            self._tracer("riposte", {"action": "reprendre"})
        else:  # bloquer : containment faible, jeton intact
            self.etat = "suspendue"
            self._tracer("riposte", {"action": "bloquer", "raison": "backend muet"})
        return Decision(verdict=verdict, trouvailles=trouvailles)

    def _attendre_decision(self) -> str:
        """Interroge GET /api/sessions/{id} chaque `intervalle` jusqu'à la décision.

        active -> "reprendre", coupee -> "couper". Si muet au bout de poll_max -> "bloquer".
        Jamais de coupure sans décision du backend.
        """
        debut = time.monotonic()
        while time.monotonic() - debut < self.poll_max_s:
            rep = self.boite.lire_session(self.session_id)
            etat = _etat_depuis(rep)
            if etat == "active":
                return "reprendre"
            if etat == "coupee":
                return "couper"
            # "suspendue", None (backend muet) ou inconnu : on continue d'attendre.
            time.sleep(self.intervalle_poll)
        return "bloquer"

    def _tracer(self, type: str, donnees: dict) -> None:
        self.journal.append({"type": type, **donnees})
