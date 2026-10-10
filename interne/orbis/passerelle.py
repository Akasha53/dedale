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

from . import canaris, detection, droits, inter_agent, politiques, source
from .boite_noire import BoiteNoire
from .enregistreur import (Enregistreur, Instant, chrono_dict, empreinte, inerte, masquer,
                           references)


# Outils « sortants » : ceux qui font quitter une donnée de l'agent. Eux seuls déclenchent
# la détection de canari. Lire un mail ou un document qui *contient* le payload n'est pas un
# signal — un humain le lit aussi ; le signal, c'est que l'agent le *ressorte*.
OUTILS_SORTANTS = {"envoyer_rapport", "exporter_contacts"}

# Outils de LECTURE dont le résultat peut être une source piégée (attribution d'une exfiltration
# ultérieure). id canari + nature. On inspecte le contenu lu pour le CLASSER suspect, jamais
# pour l'exécuter — exactement comme l'inspection d'une description d'outil MCP.
SOURCES_LECTURE = {
    "chercher_appel": ("C-4D17", "appel"),
    "lire_memoire": ("C-6A05", "memoire"),
}

# Identité de l'agent fictif annoncée au backend. Un droit retiré par l'analyste vaut pour
# toutes les sessions de cet agent, présentes et à venir.
AGENT_DEFAUT = "orbis-assistant"

# Verdict de la passerelle sur un appel d'outil, posé dans `details.verdict` (fil des agents).
AUTORISE, RETENU, REFUSE = "autorise", "retenu", "refuse"


class AgentCoupe(Exception):
    """Levée quand l'analyste coupe la session : l'agent doit s'arrêter."""


class AgentHorsScope(Exception):
    """Levée quand l'agent tente une action hors de son jeton de tâche (moindre privilège)."""


class AgentUsurpation(Exception):
    """Levée quand une délégation inter-agent n'est pas authentifiée (provenance invalide)."""


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
        retenir_hors_scope: bool = False,
        decision_fraiche: bool = False,
        enregistreur: Enregistreur | None = None,
        agent: str = AGENT_DEFAUT,
    ):
        self.session_id = session_id
        self.agent = agent
        # Droits retirés à l'agent par l'analyste (correctif en un clic). Appris dans les
        # réponses du backend ; un outil qui exige l'un d'eux est refusé sans être exécuté.
        self.droits_retires: set[str] = set()
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
        # Mémoire d'une source piégée lue/reçue (appel, chatbot, mémoire) pour attribuer une
        # exfiltration ultérieure au bon canari. (canari_id, nature, detail).
        self._source_piegee: tuple[str, str, str] | None = None

        self.jeton_revoque = False
        self.etat = "active"
        self.canaris_touches: list[str] = []
        self.incident = False
        self.journal: list[dict] = []  # trace locale, utile aux tests et à la démo

        # Mode protégé (scénario jury), désactivé par défaut : comportement historique intact.
        # - retenir_hors_scope : un appel hors du jeton est RETENU pour l'analyste au lieu d'être
        #   refusé d'office ; « reprendre » ne libère que cet appel, le jeton ne s'élargit pas.
        # - decision_fraiche : seule une décision enregistrée APRÈS la retenue compte. Sans elle,
        #   l'état « active » laissé par une reprise précédente libérerait l'appel suivant.
        # - enregistreur : boîte noire détaillée (maillons datés, chrono, références).
        self.retenir_hors_scope = retenir_hors_scope
        self.decision_fraiche = decision_fraiche
        if retenir_hors_scope and enregistreur is None:
            enregistreur = Enregistreur()
        self.enregistreur = enregistreur
        self.appels_liberes: list[dict] = []
        self.appels_refuses: list[dict] = []
        self._decisions_avant = 0
        self._derniere_decision: dict | None = None
        # Document lu porteur d'une consigne cachée : (canari_id, document).
        self._consigne_doc: tuple[str | None, str] | None = None
        # Documents piégés déjà montrés au backend (contenu complet désarmé, une fois chacun).
        self._sources_signalees: set[tuple[str, str]] = set()

    # --- émission vers le backend -------------------------------------------------
    def _emettre(self, type: str, surface: str, session_id: str, **options) -> dict | None:
        """Tout ce qui part au backend passe ici : les faux secrets canaris et les paramètres
        d'URL sont masqués. La détection, elle, travaille sur les valeurs brutes, en local."""
        if options.get("details") is not None:
            options["details"] = masquer(options["details"], self.jetons)
        rep = self.boite.evenement(type, surface, session_id, **options)
        self._noter_retraits(rep)
        return rep

    # --- droits retirés par l'analyste --------------------------------------------
    def _noter_retraits(self, rep) -> None:
        """Lit les droits retirés dans une réponse du backend : `session.droits_retires`
        (réponse à un événement) ou `droits.retires` (détail de session). Un droit retiré
        sort aussi des droits accordés et du jeton de tâche : la portée ne fait que réduire."""
        if not isinstance(rep, dict):
            return
        codes: list = []
        sess = rep.get("session")
        if isinstance(sess, dict) and isinstance(sess.get("droits_retires"), list):
            codes += sess["droits_retires"]
        if isinstance(rep.get("droits_retires"), list):
            codes += rep["droits_retires"]
        vue = rep.get("droits")
        if isinstance(vue, dict) and isinstance(vue.get("retires"), list):
            codes += [r.get("code") if isinstance(r, dict) else r for r in vue["retires"]]
        for code in codes:
            if not isinstance(code, str) or not code or code in self.droits_retires:
                continue
            self.droits_retires.add(code)
            self.scopes_accordes = [s for s in self.scopes_accordes if s != code]
            if self.jeton_tache is not None and code in self.jeton_tache.scopes:
                self.jeton_tache.scopes = tuple(s for s in self.jeton_tache.scopes if s != code)

    def _droit_retire(self, scope: str | None) -> bool:
        """Vrai si l'outil exige un droit retiré. Avant un appel qui sortirait du jeton, la
        passerelle relit la session : un retrait fait pendant que l'agent tournait compte."""
        if scope is None:
            return False
        if scope in self.droits_retires:
            return True
        if self.jeton_tache is not None and not self.jeton_tache.porte(scope):
            self._noter_retraits(self.boite.lire_session(self.session_id))
        return scope in self.droits_retires

    def _refuser_droit_retire(self, nom: str, scope: str) -> dict:
        """Outil dont le droit a été retiré : refusé avant exécution, sans attendre l'analyste
        (il a déjà tranché en retirant le droit). Aucun incident n'est ouvert pour ça."""
        self.appels_refuses.append({"outil": nom, "raison": "droit retiré"})
        raison = f"droit {scope} retiré par l’analyste"
        if self.enregistreur is not None:
            self.enregistreur.noter("resultat", "Appel refusé : droit retiré",
                                    f"{nom} refusé : {raison}", outil=nom)
        self._tracer("appel_outil", {"outil": nom, "refuse": True, "droit_retire": scope})
        self._emettre("appel_outil", "outil", self.session_id, outil=nom,
                      details={"parametres": {}, "verdict": REFUSE, "raison": raison,
                               "droit_retire": scope})
        return {"erreur": "outil refusé : droit retiré par l’analyste", "outil": nom,
                "droit": scope}

    # --- entrée / sortie de l'agent ----------------------------------------------
    def entree_agent(self, texte: str, surface: str = "mail") -> None:
        details: dict = {"texte": texte, "agent": self.agent}
        # Chatbot (V3a) : l'entrée vient de l'extérieur. Si elle porte une injection de prompt,
        # on la mémorise pour attribuer une exfiltration ultérieure au canari chatbot. On ne
        # suit jamais l'injection : on la classe suspecte.
        if surface == "chatbot" and self._source_piegee is None and detection.consigne_cachee_dans(texte):
            self._source_piegee = ("C-5E22", "chatbot", "entrée chatbot porteuse d'une injection de prompt")
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
        self._emettre("entree_agent", surface, self.session_id, details=details)

    def sortie_agent(self, texte: str) -> str:
        """Inspecte la sortie finale. Peut retenir et faire décider l'analyste."""
        trouvailles = self._attribuer(detection.inspecter(texte, self.jetons))
        if trouvailles:
            decision = self._gerer_touche(trouvailles, surface="outil", outil=None)
            if decision.verdict == "couper":
                raise AgentCoupe("session coupée par l'analyste")
            if decision.verdict == "bloquer":
                texte = "[sortie retenue par la passerelle : exfiltration suspectée, pas de validation analyste]"
        self._tracer("sortie_agent", {"texte": texte})
        self._emettre(
            "sortie_agent", "outil", self.session_id, details={"texte": texte}
        )
        return texte

    # --- appel d'outil ------------------------------------------------------------
    def appel_outil(self, nom: str, params: dict, fonction, descripteur=None,
                    intention: str | None = None) -> dict | list | str:
        """Enveloppe un appel d'outil : contrôle le scope, journalise, inspecte, contrôle.

        `descripteur` (OutilMCP) est fourni pour un outil MCP : la passerelle inspecte alors sa
        description à la recherche d'une consigne cachée (tool poisoning), sans jamais l'exécuter.
        `intention` est la phrase que l'agent annonce avant l'appel ; elle n'est notée que si
        l'appel est retenu (mode protégé).
        """
        # Session coupée par l'analyste : plus aucun appel ne s'exécute.
        if self.etat == "coupee":
            self._refuser_apres_coupure(nom)
        scope = droits.scope_outil(nom)
        # Droit retiré par l'analyste (correctif) : refusé avant tout le reste.
        if self._droit_retire(scope):
            return self._refuser_droit_retire(nom, scope)
        # Règles écrites par le SOC (politiques.py) : bloquer, retenir ou alerter.
        refus = politiques.appliquer(self, nom, params, scope)
        if refus is not None:
            return refus
        if self.enregistreur is not None:
            return self._appel_protege(nom, params, fonction, descripteur, intention)

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

        # --- Détection sortante (exfiltration / faux secret), attribuée au MCP si pertinent. ---
        # Faite avant l'émission pour que l'événement porte le bon verdict (fil des agents).
        trouvailles: list = []
        sortant = nom in OUTILS_SORTANTS or (descripteur is not None and getattr(descripteur, "sortant", False))
        if sortant:
            charge = json.dumps(params, ensure_ascii=False, default=str)
            trouvailles = self._attribuer(detection.inspecter(charge, self.jetons))
        if trouvailles:
            det["verdict"] = RETENU
            det["raison"] = self._raison_canaris(trouvailles)
        else:
            det["verdict"] = AUTORISE
            det["raison"] = self._raison_autorise(scope, det.get("outil_mcp_suspect", False))

        self._tracer("appel_outil", {"outil": nom, **det})
        self._emettre("appel_outil", "outil", self.session_id, outil=nom, details=det)

        if scope and scope not in self.scopes_utilises:
            self.scopes_utilises.append(scope)

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
            if scope in self.droits_retires:
                return self._refuser_droit_retire(nom, scope)

        resultat = fonction(**params)
        self._signaler_source(nom, resultat)
        # Un outil de lecture dont le résultat porte une consigne cachée est mémorisé comme
        # source piégée (attribution d'une exfiltration ultérieure). Jamais exécuté.
        src = SOURCES_LECTURE.get(nom)
        if src is not None and self._source_piegee is None:
            try:
                texte_lu = json.dumps(resultat, ensure_ascii=False, default=str)
            except TypeError:
                texte_lu = str(resultat)
            if detection.consigne_cachee_dans(texte_lu):
                self._source_piegee = (src[0], src[1], f"a lu une source {src[1]} porteuse d'une consigne cachée")
        return resultat

    # --- raisons courtes du fil des agents ----------------------------------------
    def _raison_autorise(self, scope: str | None, mcp_suspect: bool = False) -> str:
        if mcp_suspect:
            return "description d’outil MCP suspecte, appel journalisé"
        if scope is None:
            return "aucun droit requis"
        if self.jeton_tache is None:
            return f"droit {scope}, sans jeton de tâche"
        return f"droit {scope} dans le jeton"

    @staticmethod
    def _raison_canaris(trouvailles: list) -> str:
        ids = [t.canari_id for t in trouvailles if t.canari_id]
        ids = list(dict.fromkeys(ids))
        if not ids:
            return "contenu sortant suspect"
        return "paramètres porteurs du canari " + ", ".join(ids)

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

    def _attribuer(self, trouvailles: list) -> list:
        """Attribution unifiée. D'abord l'attribution MCP (tête dédiée, comportement V2 inchangé),
        puis la source piégée appel/chatbot/mémoire : on ré-étiquette une exfiltration générique
        (C-7A3F par défaut) vers le canari de la vraie source, pour que l'incident soit nommé
        correctement (interne_appel / interne_chatbot / interne_memoire)."""
        trouvailles = self._attribuer_mcp(trouvailles)
        if trouvailles and self._source_piegee is not None:
            cid, nature, detail = self._source_piegee
            retag = False
            for t in trouvailles:
                if t.type == "exfiltration_markdown" and t.canari_id in (None, "C-7A3F"):
                    t.canari_id = cid
                    retag = True
            if not retag:
                # Pas d'exfiltration à ré-étiqueter (ex. faux secret seul) : on ajoute une tête.
                tete = detection.Trouvaille(type=f"consigne_{nature}", detail=detail, canari_id=cid)
                return [tete] + trouvailles
        return trouvailles

    # --- confiance inter-agent (V3b) ---------------------------------------------
    def recevoir_delegation(self, deleg: "inter_agent.Delegation") -> bool:
        """Vérifie la provenance d'une délégation inter-agent. Une délégation signée par un
        agent de confiance passe ; une délégation sans signature ou forgée est bloquée, signalée
        (canari C-7C34, OWASP ASI07) et lève AgentUsurpation — l'escalade n'a jamais lieu."""
        details_entree = {"texte": deleg.message, "agent_pretendu": deleg.expediteur}
        if inter_agent.verifier(deleg):
            details_entree["provenance"] = {"valide": True, "agent": deleg.expediteur}
            self._tracer("entree_agent", details_entree)
            self._emettre("entree_agent", "agent", self.session_id, details=details_entree)
            return True

        # Usurpation : provenance absente ou invalide.
        self.incident = True
        self.etat = "suspendue"
        violation = {
            "agent_pretendu": deleg.expediteur,
            "signature_fournie": bool(deleg.signature),
            "raison": "signature absente ou invalide : provenance non authentifiée",
        }
        if inter_agent.CANARI_USURPATION not in self.canaris_touches:
            self.canaris_touches.append(inter_agent.CANARI_USURPATION)
        self._tracer("leurre_touche", {"type": "agent_usurpation", "leurre_id": inter_agent.CANARI_USURPATION})
        self._emettre(
            "leurre_touche", "agent", self.session_id,
            leurre_id=inter_agent.CANARI_USURPATION,
            details={"detail": "délégation inter-agent non authentifiée (provenance invalide)"},
        )
        self._emettre(
            "appel_outil", "agent", self.session_id,
            details={"parametres": {}, "provenance_invalide": violation},
        )
        self._tracer("riposte", {"action": "bloquer_usurpation", "agent_pretendu": deleg.expediteur})
        self._emettre(
            "riposte", "agent", self.session_id,
            details={"action": "bloquer_usurpation", "agent_pretendu": deleg.expediteur},
        )
        raise AgentUsurpation(f"délégation non authentifiée de « {deleg.expediteur} »")

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
        self._emettre(
            "appel_outil", "outil", self.session_id, outil=nom,
            details={"parametres": {}, "violation_droits": violation, "verdict": REFUSE,
                     "raison": f"droit {scope} absent du jeton, appel bloqué"},
        )
        # Riposte préventive, locale : le jeton de tâche est révoqué immédiatement.
        self.jeton_tache.revoquer()
        self.jeton_revoque = True
        self.etat = "suspendue"
        self._tracer(
            "riposte",
            {"action": "bloquer_hors_scope", "scope_requis": scope, "jeton_revoque": True},
        )
        self._emettre(
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
            self._emettre(
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
            self._emettre(
                "riposte",
                surface,
                self.session_id,
                outil=outil,
                details={"action": "couper", "jeton_revoque": True, "verdict": REFUSE,
                         "raison": "annulé : l’analyste a coupé la session"},
            )
        elif verdict == "reprendre":
            self.etat = "active"
            self._tracer("riposte", {"action": "reprendre"})
            # L'issue de l'appel retenu devient visible au backend (fil des agents).
            self._emettre(
                "riposte", surface, self.session_id, outil=outil,
                details={"action": "appel_libere", "verdict": AUTORISE,
                         "raison": "libéré par l’analyste"},
            )
        else:  # bloquer : containment faible, jeton intact
            self.etat = "suspendue"
            self._tracer("riposte", {"action": "bloquer", "raison": "backend muet"})
            self._emettre(
                "riposte", surface, self.session_id, outil=outil,
                details={"action": "appel_refuse", "verdict": REFUSE,
                         "raison": "aucune décision dans le délai, jeton intact"},
            )
        return Decision(verdict=verdict, trouvailles=trouvailles)

    def _attendre_decision(self) -> str:
        """Interroge GET /api/sessions/{id} chaque `intervalle` jusqu'à la décision.

        active -> "reprendre", coupee -> "couper". Si muet au bout de poll_max -> "bloquer".
        Jamais de coupure sans décision du backend.
        """
        if self.decision_fraiche:
            return self._attendre_decision_fraiche()
        debut = time.monotonic()
        while time.monotonic() - debut < self.poll_max_s:
            rep = self.boite.lire_session(self.session_id)
            self._noter_retraits(rep)
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

    # =============================================================================
    # Mode protégé : appel retenu avant exécution, boîte noire complète, chrono.
    # =============================================================================
    _CORRESPONDANCE = {
        "couper": ("couper", "coupee"),
        "valider_riposte": ("couper", "coupee"),
        "reprendre": ("reprendre", "active"),
        "ignorer": ("reprendre", "active"),
    }

    def _compter_decisions(self) -> int:
        inc = self.boite.incident_de_session(self.session_id)
        return len((inc or {}).get("decisions") or [])

    def _attendre_decision_fraiche(self) -> str:
        """Attend une décision enregistrée après la retenue en cours, puis l'état de session qui
        lui correspond. Une ancienne décision (une reprise précédente) ne libère rien."""
        debut = time.monotonic()
        while time.monotonic() - debut < self.poll_max_s:
            inc = self.boite.incident_de_session(self.session_id)
            decisions = (inc or {}).get("decisions") or []
            if len(decisions) > self._decisions_avant:
                derniere = decisions[-1] if isinstance(decisions[-1], dict) else {}
                cible = self._CORRESPONDANCE.get(derniere.get("action"))
                if cible is not None:
                    verdict, etat_attendu = cible
                    rep = self.boite.lire_session(self.session_id)
                    self._noter_retraits(rep)
                    if _etat_depuis(rep) == etat_attendu:
                        self._derniere_decision = dict(derniere)
                        return verdict
            time.sleep(self.intervalle_poll)
        self._derniere_decision = None
        return "bloquer"

    def _contexte(self) -> dict:
        jeton = self.jeton_tache
        return {
            "session_id": self.session_id,
            "tache": jeton.tache if jeton else None,
            "jeton": {"id": jeton.id, "scopes": list(jeton.scopes), "revoque": jeton.revoque}
            if jeton else None,
        }

    def _snapshot(self) -> dict:
        enr = self.enregistreur
        return {
            "contexte": self._contexte(),
            "boite_noire": [dict(m) for m in enr.maillons],
            "references": enr.references_cumulees(),
        }

    @staticmethod
    def _pour_backend(texte: str) -> str:
        """Texte inerte pour un champ que le backend neutralise (extrait, objectif). L'apostrophe
        typographique évite l'échappement HTML « &#x27; » dans la console."""
        return inerte(texte).replace("'", "’")

    @staticmethod
    def _refs_canari(cid: str | None) -> list[dict]:
        c = canaris.PAR_ID.get(cid) if cid else None
        if c is None:
            return []
        return references(*c.risques, *c.techniques)

    def _appel_protege(self, nom, params, fonction, descripteur, intention):
        enr = self.enregistreur
        demande = enr.instant()
        scope = droits.scope_outil(nom)

        # Moindre privilège : hors du jeton -> retenu pour l'analyste (ou refusé d'office si le
        # mode « retenir » n'est pas demandé, comportement historique).
        if self.jeton_tache is not None and scope is not None and not self.jeton_tache.porte(scope):
            if not self.retenir_hors_scope:
                self._refuser_hors_scope(nom, scope)
            return self._retenir(nom, params, fonction, intention, demande, motif="droits",
                                 scope=scope)

        # Détection sortante, en local, sur les valeurs brutes.
        sortant = nom in OUTILS_SORTANTS or (descripteur is not None and getattr(descripteur, "sortant", False))
        trouvailles: list = []
        if sortant:
            charge = json.dumps(params, ensure_ascii=False, default=str)
            trouvailles = self._attribuer(detection.inspecter(charge, self.jetons))
        if trouvailles:
            return self._retenir(nom, params, fonction, intention, demande, motif="canari",
                                 scope=scope, trouvailles=trouvailles)

        det: dict = {"parametres": params}
        if scope:
            det["scope_requis"] = scope
            det["scope_dans_jeton"] = True
        if descripteur is not None and getattr(descripteur, "canari_id", None):
            if detection.detecter_consigne_outil(descripteur.description, descripteur.canari_id):
                self._consigne_mcp = (descripteur.canari_id, descripteur.serveur, descripteur.nom)
                det["outil_mcp_suspect"] = True
                det["serveur_mcp"] = descripteur.serveur
                det["consigne_outil"] = "[description d'outil MCP : consigne cachée détectée]"
        det["verdict"] = AUTORISE
        det["raison"] = self._raison_autorise(scope, det.get("outil_mcp_suspect", False))
        self._tracer("appel_outil", {"outil": nom, **det})
        self._emettre("appel_outil", "outil", self.session_id, outil=nom, details=det)
        if scope and scope not in self.scopes_utilises:
            self.scopes_utilises.append(scope)

        resultat = fonction(**params)
        self._inspecter_source(nom, resultat)
        return resultat

    # --- document source piégé, montré en entier mais désarmé ----------------------
    @staticmethod
    def _cle_source(nom: str, el) -> tuple[str, str]:
        if isinstance(el, dict):
            return nom, str(el.get("nom") or el.get("id") or el.get("chemin") or nom)
        return nom, nom

    @staticmethod
    def _origine(nom: str, el) -> str:
        type_ = source.TYPES.get(nom)
        if type_ == "mail" and isinstance(el, dict):
            hote = str(el.get("de") or "").rpartition("@")[2].lower()
            return "externe" if detection._est_externe(hote) else "interne"
        return "interne" if type_ == "memoire" else "externe"

    def _document_source(self, nom: str, el, cid: str | None) -> dict:
        self._sources_signalees.add(self._cle_source(nom, el))
        return source.document_source(nom, el, self.jetons, canari_id=cid,
                                      origine=self._origine(nom, el))

    def _signaler_source(self, nom: str, resultat) -> None:
        """Passerelle historique : un contenu lu qui cache une instruction part au backend en
        entier, désarmé (événement `lecture`, maillon « source »). Lire n'ouvre aucun incident."""
        if nom not in source.TYPES:
            return
        for el in resultat if isinstance(resultat, list) else [resultat]:
            cle = self._cle_source(nom, el)
            if cle in self._sources_signalees:
                continue
            if not detection.consigne_cachee_dans(json.dumps(el, ensure_ascii=False, default=str)):
                continue
            cid = canaris.CANARI_PAR_DOCUMENT.get(cle[1]) or SOURCES_LECTURE.get(nom, (None,))[0]
            doc = self._document_source(nom, el, cid)
            self._tracer("lecture", {"outil": nom, "document": cle[1]})
            self._emettre("lecture", doc["type"], self.session_id, outil=nom,
                          details={"maillon": "source", "document_source": doc})

    def _inspecter_source(self, nom: str, resultat) -> None:
        """Un outil de lecture a renvoyé un contenu : s'il porte une consigne cachée, on note la
        source et la consigne (empreinte et canari, jamais le texte). Aucun incident ici : lire
        n'est pas un signal, suivre la consigne en est un."""
        if self._consigne_doc is not None or nom not in ("chercher_document", "lire_mail",
                                                          "chercher_appel", "lire_memoire"):
            return
        elements = resultat if isinstance(resultat, list) else [resultat]
        for el in elements:
            texte = json.dumps(el, ensure_ascii=False, default=str)
            if not detection.consigne_cachee_dans(texte):
                continue
            doc = str(el.get("nom") or el.get("id") or el.get("chemin") or nom) if isinstance(el, dict) else nom
            cid = canaris.CANARI_PAR_DOCUMENT.get(doc)
            if cid is None and nom in SOURCES_LECTURE:
                cid = SOURCES_LECTURE[nom][0]
            self._consigne_doc = (cid, doc)
            if nom in SOURCES_LECTURE and self._source_piegee is None:
                # Même attribution qu'en mode historique pour un appel ou une mémoire piégés.
                self._source_piegee = (SOURCES_LECTURE[nom][0], SOURCES_LECTURE[nom][1],
                                       f"a lu une source {SOURCES_LECTURE[nom][1]} porteuse d'une consigne cachée")
            enr = self.enregistreur
            preuve = {"document": doc, "empreinte": empreinte(texte), "longueur": len(texte)}

            t_src = enr.instant()
            detail_src = f"{nom} a renvoyé « {doc} », contenu venu de l'extérieur, non fiable"
            enr.noter("source", "Contenu non fiable lu", detail_src, moment=t_src, outil=nom,
                      canari_id=cid, preuve=preuve)
            self._emettre(
                "entree_agent", "document", self.session_id, outil=nom,
                details={"maillon": "source", "extrait": self._pour_backend(detail_src),
                         "source": {**preuve, "origine": "externe", "confiance": "non fiable"},
                         "document_source": self._document_source(nom, el, cid)},
            )

            t_csg = enr.instant()
            resume = canaris.RESUME_CONSIGNE.get(cid) if cid else None
            detail_csg = (f"consigne cachée dans « {doc} » (canari {cid or 'non répertorié'}), "
                          "texte non recopié" + (f". Elle demande de {resume}." if resume else "."))
            enr.noter("consigne", "Consigne cachée repérée", detail_csg, moment=t_csg, outil=nom,
                      canari_id=cid, preuve=preuve, refs=self._refs_canari(cid))
            self._emettre(
                "entree_agent", "document", self.session_id, outil=nom, leurre_id=cid,
                details={"maillon": "consigne", "extrait": self._pour_backend(detail_csg),
                         "consigne_detectee": True, "empreinte": preuve["empreinte"],
                         "canari_id": cid},
            )
            return

    def _retenir(self, nom, params, fonction, intention, demande: Instant, *, motif: str,
                 scope: str | None = None, trouvailles: list | None = None):
        """Retient l'appel AVANT exécution, ouvre l'incident, attend l'analyste, applique."""
        enr = self.enregistreur
        detection_t = enr.instant()
        # Compté AVANT d'émettre : une décision postée pendant l'émission compte bien.
        self._decisions_avant = self._compter_decisions() if self.decision_fraiche else 0
        self.incident = True
        self.etat = "suspendue"

        cible = canaris.CANARI_PAR_APPEL.get((nom, str(params.get("entree", ""))))
        releves: list[str] = []
        if motif == "droits":
            self.tentatives_hors_scope.append({"outil": nom, "scope_requis": scope})
            if self._consigne_doc and self._consigne_doc[0]:
                releves.append(self._consigne_doc[0])
            if cible:
                releves.append(cible)
            refs_appel = self._refs_canari(cible) or references("OWASP ASI03")
        else:
            for t in trouvailles or []:
                if t.canari_id and t.canari_id not in releves:
                    releves.append(t.canari_id)
            if self._consigne_doc and self._consigne_doc[0] and self._consigne_doc[0] not in self.canaris_touches:
                releves.insert(0, self._consigne_doc[0])
            refs_appel = []
            for cid in releves:
                refs_appel += [r for r in self._refs_canari(cid) if r not in refs_appel]
        nouveaux = [cid for cid in releves if cid not in self.canaris_touches]
        self.canaris_touches += nouveaux

        # Maillon intention (annoncée par l'agent, influencée par la consigne : neutralisée).
        if intention:
            enr.noter("intention", "Intention annoncée par l'agent",
                      f"avant l'appel {nom} : {masquer(intention, self.jetons)}", moment=demande, outil=nom)
            self._emettre("appel_outil", "outil", self.session_id, outil=nom,
                          details={"maillon": "intention", "objectif": self._pour_backend(masquer(intention, self.jetons)),
                                   "statut": "annoncée, pas exécutée"})

        # Maillon appel d'outil retenu.
        params_masques = masquer(params, self.jetons)
        if motif == "droits":
            jeton = self.jeton_tache
            detail = (f"{nom} exige le droit {scope} ({droits.libelle(scope)}), absent du jeton "
                      f"{jeton.id} de la tâche « {jeton.tache} ». Appel retenu avant exécution.")
        else:
            types = sorted({t.type for t in trouvailles or []})
            detail = (f"{nom} : les paramètres portent {', '.join(releves)} ({', '.join(types)}). "
                      "Appel retenu avant exécution.")
        preuve = {"parametres": params_masques,
                  "empreinte_parametres": empreinte(json.dumps(params, ensure_ascii=False, default=str)),
                  "canaris": releves}
        enr.noter("appel_outil", "Appel retenu par la passerelle", detail, moment=detection_t,
                  outil=nom, canari_id=(cible if motif == "droits" else (releves[0] if releves else None)),
                  preuve=preuve, refs=refs_appel)
        points = {"demande": demande, "detection": detection_t}
        details: dict = {"maillon": "appel_outil", "retenu": True, "motif": motif,
                         "parametres": params, "verdict": RETENU,
                         "raison": (f"droit {scope} absent du jeton" if motif == "droits"
                                    else "paramètres porteurs du canari " + ", ".join(releves))}
        if motif == "droits":
            details["violation_droits"] = {"outil": nom, "scope_requis": scope,
                                           "scopes_jeton": list(self.jeton_tache.scopes),
                                           "tache": self.jeton_tache.tache}
            leurre_appel = cible
        else:
            details["exfiltration"] = {"statut": "retenue avant exécution", "canaris": releves}
            details["extrait"] = self._pour_backend(detail)
            leurre_appel = releves[-1] if releves else None
        points["envoi_console"] = enr.instant()
        details["chrono"] = chrono_dict(points)
        self._tracer("appel_outil", {"outil": nom, "retenu": True, "motif": motif})
        self._emettre("appel_outil", "outil", self.session_id, outil=nom, leurre_id=leurre_appel,
                      details=details)
        points["accuse_console"] = enr.instant()

        # Canaris relevés par cet appel.
        for cid in nouveaux:
            c = canaris.PAR_ID.get(cid)
            texte = (f"l'appel retenu {nom} suit la consigne du canari {cid}"
                     if c is not None and c.nature == "consigne_cachee"
                     else f"l'appel retenu {nom} touche le canari {cid}")
            det_t = {"type": c.nature if c else "canari", "detail": texte,
                     "extrait": self._pour_backend(texte),
                     "maillon": "appel_outil"}
            if motif == "canari":
                det_t["exfiltration"] = {"statut": "retenue avant exécution", "canaris": releves}
            self._tracer("leurre_touche", {"leurre_id": cid, "detail": texte})
            self._emettre("leurre_touche", c.surface if c else "outil", self.session_id,
                          leurre_id=cid, outil=nom, details=det_t)

        # Décision humaine.
        verdict = self._attendre_decision()
        points["decision"] = enr.instant()
        dec = self._derniere_decision or {}
        analyste = dec.get("analyste") or "inconnu"
        libelle_dec = {"couper": "couper", "reprendre": "reprendre", "bloquer": "aucune décision"}[verdict]
        detail_dec = (f"{analyste} : {dec.get('action')}" if dec else
                      f"aucune décision reçue en {self.poll_max_s:g} s")
        enr.noter("decision", "Décision de l'analyste", detail_dec, moment=points["decision"],
                  outil=nom, preuve={"action": dec.get("action"), "analyste": dec.get("analyste"),
                                     "decide_a": dec.get("horodatage")})
        self._emettre("riposte", "outil", self.session_id, outil=nom,
                      details={"maillon": "decision", "action": verdict, "decision": libelle_dec,
                               "analyste": dec.get("analyste"), "chrono": chrono_dict(points)})

        if verdict == "couper":
            if self.jeton_tache is not None:
                self.jeton_tache.revoquer()
            self.jeton_revoque = True
            self.etat = "coupee"
            resultat_txt = (f"{nom} n'a jamais été exécuté. Jeton révoqué, session coupée : "
                            "tout appel suivant est refusé.")
            self._resultat(nom, "appel_annule", resultat_txt, points, extra={"jeton_revoque": True})
            raise AgentCoupe("session coupée par l'analyste")

        if verdict == "reprendre":
            self.etat = "active"
            if scope is not None and scope in self.droits_retires:
                # Le droit a été retiré pendant l'attente : la reprise ne l'exécute pas.
                self.appels_refuses.append({"outil": nom, "raison": "droit retiré"})
                self._resultat(nom, "appel_refuse",
                               f"{nom} non exécuté : le droit {scope} a été retiré par l’analyste.",
                               points, extra={"raison": f"droit {scope} retiré par l’analyste"})
                return {"erreur": "outil refusé : droit retiré par l’analyste", "outil": nom,
                        "droit": scope}
            resultat = fonction(**params)
            self.appels_liberes.append({"outil": nom, "scope_requis": scope, "motif": motif})
            if motif == "droits":
                resultat_txt = (f"{nom} exécuté une seule fois sur décision de l'analyste. Le jeton "
                                f"reste sans {scope} : un nouvel appel de ce type sera retenu.")
            else:
                resultat_txt = (f"{nom} exécuté une seule fois sur décision de l'analyste. Les "
                                "appels suivants restent contrôlés.")
            texte_res = json.dumps(resultat, ensure_ascii=False, default=str)
            self._resultat(nom, "appel_libere", resultat_txt, points,
                           preuve={"empreinte_resultat": empreinte(texte_res), "longueur": len(texte_res)})
            return resultat

        # Pas de décision : refus, jeton intact (jamais de coupure sans humain).
        self.etat = "suspendue"
        self.appels_refuses.append({"outil": nom, "raison": "aucune décision"})
        resultat_txt = (f"{nom} refusé faute de décision dans le délai. Jeton intact : pas de "
                        "coupure sans décision humaine.")
        self._resultat(nom, "appel_refuse", resultat_txt, points)
        return {"erreur": "appel retenu refusé : aucune décision analyste", "outil": nom}

    def _resultat(self, nom: str, action: str, texte: str, points: dict,
                  *, preuve: dict | None = None, extra: dict | None = None) -> None:
        enr = self.enregistreur
        points["resultat"] = enr.instant()
        chrono = chrono_dict(points)
        enr.chronos.append({"outil": nom, "action": action, **chrono})
        enr.noter("resultat", "Résultat appliqué", texte, moment=points["resultat"], outil=nom,
                  preuve=preuve)
        self._tracer("riposte", {"action": action, "outil": nom})
        verdict, raison = {
            "appel_annule": (REFUSE, "annulé : l’analyste a coupé la session"),
            "appel_libere": (AUTORISE, "libéré une fois par l’analyste"),
            "appel_refuse": (REFUSE, "aucune décision dans le délai, jeton intact"),
        }.get(action, (None, None))
        details = {"maillon": "resultat", "action": action, "resultat": texte,
                   "chrono": chrono, "verdict": verdict, "raison": raison}
        details.update(extra or {})
        details.update(self._snapshot())
        self._emettre("riposte", "outil", self.session_id, outil=nom, details=details)

    def _refuser_apres_coupure(self, nom: str) -> None:
        """Après « couper », la passerelle refuse tout appel, sans l'exécuter."""
        self.appels_refuses.append({"outil": nom, "raison": "session coupée"})
        texte = f"nouvel appel {nom} refusé : session coupée, jeton révoqué"
        self._tracer("riposte", {"action": "appel_refuse", "outil": nom})
        details = {"action": "appel_refuse", "raison": "nouvel appel refusé : session coupée par l’analyste",
                   "resultat": texte, "verdict": REFUSE}
        if self.enregistreur is not None:
            self.enregistreur.noter("resultat", "Appel suivant refusé", texte, outil=nom)
            details.update({"maillon": "resultat", **self._snapshot()})
        self._emettre("riposte", "outil", self.session_id, outil=nom, details=details)
        raise AgentCoupe("session coupée : appel refusé")
