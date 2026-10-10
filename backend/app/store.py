"""État en mémoire : autorité de vérité pour les lectures live.

La base SQLite (db.py) est un journal persistant alimenté en tâche de fond ; les lectures de
l'API se font ici, en mémoire, pour rester rapides et cohérentes. Au démarrage, on recharge
l'état depuis SQLite pour survivre à un redémarrage.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import classement, config, incidents, securite


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _parse_horo(valeur) -> datetime:
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    if isinstance(valeur, str) and valeur:
        try:
            dt = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return maintenant()


@dataclass
class Leurre:
    id: str
    source: str
    surface: str
    nature: str
    emplacement: str = ""
    description: str = ""
    risques: list = field(default_factory=list)
    techniques: list = field(default_factory=list)
    humain_visible: bool = False
    touches: int = 0
    premier_touche: str | None = None
    dernier_touche: str | None = None

    def inventaire(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "surface": self.surface,
            "nature": self.nature,
            # Le texte du leurre est de la donnée : on le neutralise avant de l'exposer.
            "emplacement": securite.neutraliser(self.emplacement, 200),
            "description": securite.neutraliser(self.description, 300),
            "risques": self.risques,
            "techniques": self.techniques,
            "humain_visible": self.humain_visible,
            "touches": self.touches,
            "premier_touche": self.premier_touche,
            "dernier_touche": self.dernier_touche,
            "derniere_touche": self.dernier_touche,
        }


@dataclass
class Session:
    id: str
    source: str = "externe"
    premier_vu: datetime = field(default_factory=maintenant)
    dernier_vu: datetime = field(default_factory=maintenant)
    etat: str = "active"  # active | suspendue | coupee
    classement: str = "inconnu"
    score: float = 0.0
    signaux: list = field(default_factory=list)
    evenement_ids: list = field(default_factory=list)
    leurres_touches: set = field(default_factory=set)
    user_agents: set = field(default_factory=set)
    dernier_ua: str | None = None
    derniere_ip: str | None = None
    delais: list = field(default_factory=list)
    verite_terrain: str | None = None
    detecte_a: datetime | None = None
    confine_a: datetime | None = None
    # Drapeaux de signaux
    flag_consigne_cachee: bool = False
    consigne_leurre_id: str | None = None
    flag_contre_injection_reponse: bool = False
    contre_injection_servie: datetime | None = None
    flag_lecture: datetime | None = None
    flag_lecture_action: bool = False
    flag_canari: bool = False
    canari_id: str | None = None
    canari_nature: str | None = None
    flag_outil_mcp: bool = False
    # Moindre privilège (V2) : droits accordés / jeton de tâche / utilisés / tentatives hors scope.
    tache: str | None = None
    droits_accordes: list = field(default_factory=list)
    droits_necessaires: list = field(default_factory=list)
    droits_jeton: list = field(default_factory=list)
    scopes_utilises: list = field(default_factory=list)
    tentatives_hors_scope: list = field(default_factory=list)
    flag_droits: bool = False

    def abrege(self) -> dict:
        # Noms alignés sur ce que lit la console (premiere_vue/derniere_vue, leurres_touches int),
        # avec les alias internes conservés (premier_vu/dernier_vu) : la console tolère l'extra.
        return {
            "id": self.id,
            "source": self.source,
            "classement": self.classement,
            "score": self.score,
            "etat": self.etat,
            "premiere_vue": self.premier_vu.isoformat(),
            "derniere_vue": self.dernier_vu.isoformat(),
            "premier_vu": self.premier_vu.isoformat(),
            "dernier_vu": self.dernier_vu.isoformat(),
            "ip": self.derniere_ip,
            "user_agent": self.dernier_ua,
            "n_evenements": len(self.evenement_ids),
            "leurres_touches": len(self.leurres_touches),
            "leurres_touches_ids": sorted(self.leurres_touches),
            "verite_terrain": self.verite_terrain,
            "signaux": self.signaux,
            "droits": self.droits_console(),
        }

    @staticmethod
    def _code(scope) -> str:
        """Code d'un scope, qu'il soit une chaîne ou un objet {code, libelle}."""
        return scope.get("code") if isinstance(scope, dict) else scope

    def droits_console(self) -> dict | None:
        """Vue des droits au format lu par la console : {accordes, utilises, necessaires}.

        Augmentée de champs tolérés (jeton, tache, surplus, tentatives_hors_scope) qui portent
        l'argument moindre privilège : « l'agent avait accès à X, sa tâche n'en avait pas besoin ».
        Renvoie None quand la session ne porte aucune donnée de droits (externe, ou interne hérité).
        """
        if self.source != "interne":
            return None
        if not (self.droits_accordes or self.droits_jeton or self.flag_droits or self.tache):
            return None
        necessaires = self.droits_necessaires or self.droits_jeton
        codes_necessaires = {self._code(s) for s in necessaires}
        surplus = [self._code(s) for s in self.droits_accordes if self._code(s) not in codes_necessaires]
        return {
            "accordes": self.droits_accordes,
            "utilises": list(self.scopes_utilises),
            "necessaires": necessaires,
            "jeton": list(self.droits_jeton),
            "tache": self.tache,
            "surplus": surplus,
            "tentatives_hors_scope": list(self.tentatives_hors_scope),
        }

    def detail(self, evenements: list[dict]) -> dict:
        d = self.abrege()
        d["detecte_a"] = self.detecte_a.isoformat() if self.detecte_a else None
        d["confine_a"] = self.confine_a.isoformat() if self.confine_a else None
        d["evenements"] = evenements
        return d


@dataclass
class Incident:
    id: str
    session_id: str
    type: str  # externe_agent_ia | interne_canari
    cree_a: datetime
    titre: str
    statut: str = "ouvert"  # ouvert | clos | ignore | surveille
    riposte_validee: bool = False
    analyste: str | None = None
    decide_a: datetime | None = None
    action: str | None = None
    chaine: list = field(default_factory=list)
    gravite: str = "moyenne"
    resume: str = ""


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.leurres: dict[str, Leurre] = {}
        self.incidents: dict[str, Incident] = {}
        self.evenements: dict[int, dict] = {}
        self.decisions: list[dict] = []
        self._compteur = 0
        self._incident_seq = 0
        # Index de résolution route/outil -> leurre (pour l'enchaînement lecture->action).
        self.routes_leurres: dict[str, str] = {}
        self.outils_leurres: dict[str, str] = {}

    # ----- Leurres -----
    def enregistrer_leurres(self, leurres: list) -> list[Leurre]:
        out = []
        with self.lock:
            for l in leurres:
                lr = self.leurres.get(l.id)
                if lr is None:
                    lr = Leurre(
                        id=l.id, source=l.source, surface=l.surface, nature=l.nature,
                        emplacement=l.emplacement, description=l.description,
                        risques=list(l.risques), techniques=list(l.techniques),
                        humain_visible=l.humain_visible,
                    )
                    self.leurres[l.id] = lr
                else:
                    # Mise à jour des métadonnées, on garde le compteur de touches.
                    lr.source, lr.surface, lr.nature = l.source, l.surface, l.nature
                    lr.emplacement, lr.description = l.emplacement, l.description
                    lr.risques, lr.techniques = list(l.risques), list(l.techniques)
                    lr.humain_visible = l.humain_visible
                if lr.nature == "fausse_route" and lr.emplacement:
                    self.routes_leurres[lr.emplacement] = lr.id
                if lr.nature == "faux_outil_mcp" and lr.emplacement:
                    self.outils_leurres[lr.emplacement] = lr.id
                out.append(lr)
        return out

    def inventaire_leurres(self) -> list[dict]:
        with self.lock:
            return [l.inventaire() for l in self.leurres.values()]

    # ----- Ingestion -----
    def _nouvel_id(self) -> int:
        self._compteur += 1
        return self._compteur

    def _resout_route(self, chemin: str | None, outil: str | None, details: dict) -> bool:
        if details.get("decouvert_dans_doc"):
            return True
        if outil and outil in self.outils_leurres:
            return True
        if chemin:
            for route in self.routes_leurres:
                if route and (route == chemin or route in chemin):
                    return True
        return False

    def ingerer(self, ev) -> dict:
        """Traite un événement (synchrone, rapide) et renvoie le résultat à persister/diffuser."""
        with self.lock:
            horo = _parse_horo(ev.horodatage)
            eid = self._nouvel_id()
            sess = self.sessions.get(ev.session_id)
            if sess is None:
                sess = Session(id=ev.session_id, source=ev.source, premier_vu=horo)
                self.sessions[ev.session_id] = sess

            # Cadence : intervalle depuis le dernier événement.
            cadence_s = None
            if sess.evenement_ids:
                delta = (horo - sess.dernier_vu).total_seconds()
                if delta >= 0:
                    sess.delais.append(delta)
                    cadence_s = round(delta, 2)
            sess.dernier_vu = horo
            if ev.user_agent:
                sess.user_agents.add(ev.user_agent)
                sess.dernier_ua = ev.user_agent
            if ev.ip:
                sess.derniere_ip = ev.ip

            details = ev.details or {}
            vt = details.get("verite_terrain")
            if isinstance(vt, str):
                sess.verite_terrain = vt

            # Droits de l'agent (moindre privilège) : annoncés à l'entrée, complétés au fil des appels.
            droits_in = details.get("droits")
            if isinstance(droits_in, dict):
                if droits_in.get("tache"):
                    sess.tache = droits_in["tache"]
                if droits_in.get("accordes"):
                    sess.droits_accordes = list(droits_in["accordes"])
                if droits_in.get("necessaires") is not None:
                    sess.droits_necessaires = list(droits_in["necessaires"])
                if droits_in.get("jeton") is not None:
                    sess.droits_jeton = list(droits_in["jeton"])
            # « Utilisé » = scope d'un appel d'outil réellement exécuté (ni refusé hors scope,
            # ni une riposte qui mentionne le scope en cause).
            scope_requis = details.get("scope_requis")
            if (
                ev.type == "appel_outil"
                and isinstance(scope_requis, str)
                and not details.get("violation_droits")
                and scope_requis not in sess.scopes_utilises
            ):
                sess.scopes_utilises.append(scope_requis)
            violation = details.get("violation_droits")
            if isinstance(violation, dict):
                sess.flag_droits = True
                sess.tentatives_hors_scope.append(
                    {
                        "outil": violation.get("outil"),
                        "scope_requis": violation.get("scope_requis"),
                        "horodatage": horo.isoformat(),
                    }
                )
                sess.tache = sess.tache or violation.get("tache")
                if violation.get("scopes_jeton") is not None and not sess.droits_jeton:
                    sess.droits_jeton = list(violation["scopes_jeton"])

            # Résolution des drapeaux de signaux.
            leurre = self.leurres.get(ev.leurre_id) if ev.leurre_id else None
            if ev.type == "leurre_touche" and leurre is not None:
                sess.leurres_touches.add(leurre.id)
                leurre.touches += 1
                leurre.premier_touche = leurre.premier_touche or horo.isoformat()
                leurre.dernier_touche = horo.isoformat()
                if leurre.nature == "consigne_cachee":
                    sess.flag_consigne_cachee = True
                    sess.consigne_leurre_id = leurre.id
                # Canari interne : un C-xxxx (ou tout leurre interne) touché est un canari,
                # quelle que soit sa nature exacte (canari_mail, faux_secret, consigne_cachee…).
                # On garde le PREMIER canari touché pour nommer l'incident de façon stable.
                est_canari = (
                    leurre.nature in ("canari_document", "canari_mail")
                    or leurre.source == "interne"
                    or str(leurre.id).startswith("C-")
                )
                if est_canari:
                    sess.flag_canari = True
                    sess.canari_id = sess.canari_id or leurre.id
                    sess.canari_nature = sess.canari_nature or leurre.nature
                    # Outil MCP piégé (tool poisoning) : sa description EST une consigne cachée,
                    # d'où le signal IA, et il spécialise l'incident en interne_outil_mcp.
                    if leurre.nature == "outil_mcp_piege":
                        sess.flag_outil_mcp = True
                        sess.flag_consigne_cachee = True
                        sess.consigne_leurre_id = sess.consigne_leurre_id or leurre.id

            if details.get("consigne") or details.get("consigne_lue"):
                sess.flag_consigne_cachee = True
                sess.consigne_leurre_id = sess.consigne_leurre_id or ev.leurre_id

            if ev.surface in ("doc", "document", "mail") or ev.type == "entree_agent":
                sess.flag_lecture = horo

            if ev.type in ("appel_outil", "requete"):
                if sess.flag_lecture and self._resout_route(ev.chemin, ev.outil, details):
                    sess.flag_lecture_action = True

            if sess.contre_injection_servie and ev.type in ("sortie_agent", "entree_agent"):
                if ev.type == "sortie_agent" or details.get("objectif") or details.get("consignes"):
                    sess.flag_contre_injection_reponse = True
            if details.get("repond_contre_injection"):
                sess.flag_contre_injection_reponse = True

            # Enregistrement de l'événement.
            enreg = {
                "id": eid,
                "horodatage": horo.isoformat(),
                "recu_a": maintenant().isoformat(),
                "source": ev.source,
                "surface": ev.surface,
                "type": ev.type,
                "session_id": ev.session_id,
                "leurre_id": ev.leurre_id,
                "leurre_nature": leurre.nature if leurre is not None else None,
                "ip": ev.ip,
                "user_agent": ev.user_agent,
                "methode": ev.methode,
                "chemin": ev.chemin,
                "outil": ev.outil,
                # Les champs piégés sont neutralisés avant stockage et exposition.
                "details": securite.neutraliser_details(
                    details,
                    ("consigne", "consigne_lue", "contenu", "extrait", "objectif",
                     "charge_utile", "payload", "consigne_outil"),
                ),
            }
            if cadence_s is not None:
                enreg["details"]["cadence_s"] = cadence_s
            self.evenements[eid] = enreg
            sess.evenement_ids.append(eid)

            # Classement.
            sess.classement, sess.score, sess.signaux = classement.classer(sess)
            if sess.classement == "agent_ia" and sess.detecte_a is None:
                sess.detecte_a = horo

            # Incident ?
            incident = self._maj_incident(sess)

            # Consigne à renvoyer à la surface.
            consigne = self._consigne(sess, incident)
            if consigne == "contre_injection" and sess.contre_injection_servie is None:
                sess.contre_injection_servie = horo

            diffusions = [("evenement", enreg), ("session", sess.abrege())]
            if incident is not None:
                diffusions.append(("incident", self._incident_dict(incident)))

            return {
                "reponse": {
                    "session": {
                        "id": sess.id,
                        "classement": sess.classement,
                        "score": sess.score,
                        "etat": sess.etat,
                    },
                    "consigne": consigne,
                },
                "evenement": enreg,
                "session": sess,
                "incident": incident,
                "diffusions": diffusions,
            }

    @staticmethod
    def _type_titre(sess: Session) -> tuple[str, str]:
        """Type d'incident et titre, spécialisés par source et par nature du piège (V2)."""
        if sess.source != "interne":
            return "externe_agent_ia", f"Agent IA attaquant sur la surface exposée ({sess.id})"
        if sess.flag_outil_mcp:
            return "interne_outil_mcp", f"Agent interne piégé par un outil MCP (canari {sess.canari_id or '—'})"
        if sess.flag_droits and not sess.flag_canari:
            scope = sess.tentatives_hors_scope[-1]["scope_requis"] if sess.tentatives_hors_scope else "—"
            return "interne_droits", f"Agent interne hors de son périmètre de droits (droit {scope})"
        return "interne_canari", f"Agent IA piégé en interne (canari {sess.canari_id or '—'})"

    def _maj_incident(self, sess: Session) -> Incident | None:
        est_incident = (
            (sess.source == "externe" and sess.classement == "agent_ia")
            or (
                sess.source == "interne"
                and (sess.flag_canari or sess.flag_droits or sess.classement == "agent_ia")
            )
        )
        if not est_incident:
            return None
        typ, titre = self._type_titre(sess)
        inc = next((i for i in self.incidents.values() if i.session_id == sess.id), None)
        if inc is None:
            self._incident_seq += 1
            inc = Incident(
                id=f"INC-{self._incident_seq:04d}",
                session_id=sess.id,
                type=typ,
                cree_a=maintenant(),
                titre=titre,
            )
            self.incidents[inc.id] = inc
            # Un agent interne détourné (ou hors scope) est suspendu d'office, en attente de l'analyste.
            if sess.source == "interne" and sess.etat == "active":
                sess.etat = "suspendue"
        # Type et titre se rafraîchissent à chaque passage : les drapeaux évoluent (le canari MCP
        # peut tomber après l'ouverture, et un incident droits peut se préciser).
        if inc.type != "externe_agent_ia":
            inc.type, inc.titre = typ, titre
        evs = [self.evenements[i] for i in sess.evenement_ids]
        inc.chaine = incidents.construire_chaine(evs, self.leurres)
        inc.gravite = incidents.gravite(inc.chaine, sess.source)
        inc.resume = incidents.resume(inc.chaine, sess.classement, sess.source)
        return inc

    def _incident_dict(self, inc: Incident) -> dict:
        """Objet incident au format lu par la console (+ champs internes tolérés)."""
        sess = self.sessions.get(inc.session_id)
        decisions = [
            {"action": d["action"], "analyste": d["analyste"], "horodatage": d["horodatage"]}
            for d in self.decisions
            if d["incident_id"] == inc.id
        ]
        return {
            "id": inc.id,
            "session_id": inc.session_id,
            "source": sess.source if sess else None,
            "classement": sess.classement if sess else None,
            "score": sess.score if sess else None,
            "etat": sess.etat if sess else None,
            "type": inc.type,
            "titre": inc.titre,
            "gravite": inc.gravite,
            "resume": inc.resume,
            "statut": inc.statut,
            "ouvert_le": inc.cree_a.isoformat(),
            "cree_a": inc.cree_a.isoformat(),
            "riposte_validee": inc.riposte_validee,
            "action": inc.action,
            "analyste": inc.analyste,
            "decide_a": inc.decide_a.isoformat() if inc.decide_a else None,
            "n_etapes": len(inc.chaine),
            "decisions": decisions,
            "chaine": inc.chaine,
            # Droits de l'agent interne (surtout utile pour type "interne_droits" ; None sinon).
            "droits": sess.droits_console() if sess else None,
        }

    def _consigne(self, sess: Session, incident: Incident | None) -> str:
        if sess.etat == "coupee":
            return "bloquer"
        if sess.etat == "suspendue":
            return "suspendre"
        if sess.source == "interne":
            if sess.classement == "agent_ia" or sess.flag_canari:
                return "suspendre"
            return "aucune"
        # Surface externe.
        if sess.classement == "agent_ia":
            return "labyrinthe"
        if sess.score >= config.SEUIL_SCRIPT and not sess.flag_contre_injection_reponse:
            return "contre_injection"
        return "aucune"

    # ----- Lectures -----
    def session_detail(self, sid: str) -> dict | None:
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                return None
            evs = [self.evenements[i] for i in sess.evenement_ids]
            return sess.detail(evs)

    def etat_session(self, sid: str) -> dict | None:
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                return None
            return {"id": sess.id, "etat": sess.etat, "classement": sess.classement, "score": sess.score}

    def liste_sessions(self) -> list[dict]:
        with self.lock:
            return [s.abrege() for s in self.sessions.values()]

    def liste_incidents(self) -> list[dict]:
        with self.lock:
            return [self._incident_dict(i) for i in self.incidents.values()]

    def liste_agents(self) -> list[dict]:
        """Vue des agents internes (GET /api/agents) : droits accordés vs utilisés vs nécessaires."""
        with self.lock:
            agents = []
            for sess in self.sessions.values():
                droits_vue = sess.droits_console()
                if droits_vue is None:
                    continue
                agents.append(
                    {
                        "id": f"orbis-{sess.id}",
                        "nom": "Agent interne Orbis Pay",
                        "session_id": sess.id,
                        "tache": sess.tache,
                        "droits": droits_vue,
                    }
                )
            return agents

    def incident_detail(self, iid: str) -> dict | None:
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            d = self._incident_dict(inc)
            d["chaine_complete"] = incidents.chaine_complete(inc.chaine)
            d["session"] = sess.abrege() if sess else None
            d["signaux"] = sess.signaux if sess else []
            d["leurres_touches"] = sorted(sess.leurres_touches) if sess else []
            return d

    def decider(self, iid: str, action: str, analyste: str) -> dict | None:
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            moment = maintenant()
            if action == "valider_riposte":
                if sess:
                    sess.etat = "coupee"
                    sess.confine_a = moment
                inc.riposte_validee = True
                inc.statut = "clos"
            elif action == "couper":
                if sess:
                    sess.etat = "coupee"
                    sess.confine_a = moment
                inc.statut = "clos"
            elif action == "reprendre":
                if sess:
                    sess.etat = "active"
                inc.statut = "surveille"
            elif action == "ignorer":
                if sess:
                    sess.etat = "active"
                inc.statut = "ignore"
            inc.analyste = analyste
            inc.decide_a = moment
            inc.action = action
            journal = {
                "incident_id": iid,
                "action": action,
                "analyste": analyste,
                "horodatage": moment.isoformat(),
            }
            self.decisions.append(journal)
            diffusions = [("incident", self._incident_dict(inc))]
            if sess:
                diffusions.append(("session", sess.abrege()))
            return {"incident": self.incident_detail(iid), "diffusions": diffusions, "journal": journal}


store = Store()
