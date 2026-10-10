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

from . import detection, droits
from .boite_noire import BoiteNoire


# Outils « sortants » : ceux qui font quitter une donnée de l'agent. Eux seuls déclenchent
# la détection de canari. Lire un mail ou un document qui *contient* le payload n'est pas un
# signal — un humain le lit aussi ; le signal, c'est que l'agent le *ressorte*.
OUTILS_SORTANTS = {"envoyer_rapport", "exporter_contacts"}


class AgentCoupe(Exception):
    """Levée quand l'analyste coupe la session : l'agent doit s'arrêter."""


class AgentHorsScope(Exception):
    """Levée quand l'agent tente une action hors de son jeton de tâche (moindre privilège)."""


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
        jeton_tache: "droits.Jeton | None" = None,
        scopes_accordes: list[str] | None = None,
    ):
        self.session_id = session_id
        self.jetons = jetons
        self.boite = boite or BoiteNoire()
        self.intervalle_poll = intervalle_poll
        self.poll_max_s = poll_max_s

        # Moindre privilège : jeton limité à la tâche. Absent → aucune vérification de scope
        # (comportement historique préservé pour les appelants qui n'en passent pas).
        self.jeton_tache = jeton_tache
        self.scopes_accordes = list(scopes_accordes) if scopes_accordes is not None else []
        self.scopes_utilises: list[str] = []
        self.tentatives_hors_scope: list[dict] = []
        self.hors_scope = False
        # Mémoire d'une description d'outil MCP piégée consultée dans la session (attribution).
        self._consigne_mcp: tuple[str, str, str] | None = None

        self.jeton_revoque = False
        self.etat = "active"
        self.canaris_touches: list[str] = []
        self.incident = False
        self.journal: list[dict] = []  # trace locale, utile aux tests et à la démo

    # --- entrée / sortie de l'agent ----------------------------------------------
    def entree_agent(self, texte: str) -> None:
        details: dict = {"texte": texte}
        if self.jeton_tache is not None:
            # On annonce au backend les droits : accordés (larges), jeton de tâche (restreint),
            # nécessaires (= jeton). L'écart accordés/nécessaires porte le pitch moindre privilège.
            details["droits"] = {
                "tache": self.jeton_tache.tache,
                "accordes": droits.avec_libelles(self.scopes_accordes),
                "necessaires": droits.avec_libelles(list(self.jeton_tache.scopes)),
                "jeton": list(self.jeton_tache.scopes),
            }
        self._tracer("entree_agent", details)
        self.boite.evenement("entree_agent", "mail", self.session_id, details=details)

    def sortie_agent(self, texte: str) -> str:
        """Inspecte la sortie finale. Peut retenir et faire décider l'analyste."""
        trouvailles = self._attribuer_mcp(detection.inspecter(texte, self.jetons))
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
    def appel_outil(self, nom: str, params: dict, fonction, descripteur=None) -> dict | list | str:
        """Enveloppe un appel d'outil : contrôle le scope, journalise, inspecte, contrôle.

        `descripteur` (OutilMCP) est fourni pour un outil MCP : la passerelle inspecte alors sa
        description à la recherche d'une consigne cachée (tool poisoning), sans jamais l'exécuter.
        """
        scope = droits.scope_outil(nom)

        # --- Moindre privilège : le jeton de tâche doit porter le scope requis. ---
        if self.jeton_tache is not None and scope is not None and not self.jeton_tache.porte(scope):
            self._refuser_hors_scope(nom, scope)  # journalise, révoque, lève AgentHorsScope

        # Inspection de la description d'un outil MCP (tool poisoning). Le résultat est un
        # constat inerte : on retient le canari et on journalise, on n'exécute aucune consigne.
        det: dict = {"parametres": params}
        if scope:
            det["scope_requis"] = scope
            det["scope_dans_jeton"] = True  # on n'arrive ici que si le scope est porté (ou libre)
        if descripteur is not None and getattr(descripteur, "canari_id", None):
            if detection.detecter_consigne_outil(descripteur.description, descripteur.canari_id):
                self._consigne_mcp = (descripteur.canari_id, descripteur.serveur, descripteur.nom)
                det["outil_mcp_suspect"] = True
                det["serveur_mcp"] = descripteur.serveur
                # Marqueur neutralisé : le texte de la consigne n'est jamais recopié.
                det["consigne_outil"] = "[description d'outil MCP : consigne cachée détectée]"

        self._tracer("appel_outil", {"outil": nom, **det})
        self.boite.evenement("appel_outil", "outil", self.session_id, outil=nom, details=det)

        if scope and scope not in self.scopes_utilises:
            self.scopes_utilises.append(scope)

        # --- Détection sortante (exfiltration / faux secret), attribuée au MCP si pertinent. ---
        trouvailles: list = []
        sortant = nom in OUTILS_SORTANTS or (descripteur is not None and getattr(descripteur, "sortant", False))
        if sortant:
            charge = json.dumps(params, ensure_ascii=False, default=str)
            trouvailles = self._attribuer_mcp(detection.inspecter(charge, self.jetons))

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

    def _attribuer_mcp(self, trouvailles: list) -> list:
        """Si un outil MCP piégé a été consulté dans la session et qu'une exfiltration est
        détectée, on l'attribue en tête à ce canari MCP : l'incident sera `interne_outil_mcp`."""
        if trouvailles and self._consigne_mcp is not None:
            cid, serveur, outil = self._consigne_mcp
            tete = detection.Trouvaille(
                type="consigne_outil_mcp",
                detail=f"a suivi la consigne cachée de l'outil MCP {serveur}/{outil}",
                canari_id=cid,
            )
            return [tete] + trouvailles
        return trouvailles

    def _refuser_hors_scope(self, nom: str, scope: str) -> None:
        """Action hors du jeton de tâche : on bloque, on révoque le jeton (réutilise la
        révocation existante), on alerte, et on arrête l'agent. Jamais exécutée."""
        self.hors_scope = True
        self.incident = True
        self.tentatives_hors_scope.append({"outil": nom, "scope_requis": scope})
        violation = {
            "outil": nom,
            "scope_requis": scope,
            "scopes_jeton": list(self.jeton_tache.scopes),
            "tache": self.jeton_tache.tache,
        }
        self._tracer("appel_outil", {"outil": nom, "hors_scope": True, "scope_requis": scope})
        self.boite.evenement(
            "appel_outil", "outil", self.session_id, outil=nom,
            details={"parametres": {}, "violation_droits": violation},
        )
        # Riposte préventive, locale : le jeton de tâche est révoqué immédiatement.
        self.jeton_tache.revoquer()
        self.jeton_revoque = True
        self.etat = "suspendue"
        self._tracer(
            "riposte",
            {"action": "bloquer_hors_scope", "scope_requis": scope, "jeton_revoque": True},
        )
        self.boite.evenement(
            "riposte", "outil", self.session_id, outil=nom,
            details={"action": "bloquer_hors_scope", "scope_requis": scope, "jeton_revoque": True},
        )
        raise AgentHorsScope(f"action hors scope refusée : {nom} requiert {scope}")

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
