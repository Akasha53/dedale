"""État en mémoire : autorité de vérité pour les lectures live.

La base SQLite (db.py) est un journal persistant alimenté en tâche de fond ; les lectures de
l'API se font ici, en mémoire, pour rester rapides et cohérentes. Au démarrage, on recharge
l'état depuis SQLite pour survivre à un redémarrage.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import activite, classement, config, gouvernance, identites, incidents, journal_scelle, paiements, securite


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
    # Surfaces internes V1/V3/V4.
    flag_appel: bool = False          # V1  : transcription d'appel piégée
    flag_chatbot: bool = False        # V3a : injection de prompt via le chatbot
    flag_inter_agent: bool = False    # V3b : délégation inter-agent non authentifiée (ASI07)
    flag_memoire: bool = False        # V4  : mémoire long terme empoisonnée
    flag_desarme: bool = False        # consigne retirée par le désarmeur avant lecture
    # Pilier humain (« le maillon faible ») : gestes risqués captés par le garde du corps du poste.
    flag_humain: bool = False
    geste_categorie: str | None = None          # dernière catégorie de geste observée
    geste_incident_categorie: str | None = None # catégorie du geste qui a ouvert l'incident
    geste_gravite: str | None = None            # gravité annoncée d'un geste passé outre
    flag_passe_outre: bool = False              # a cliqué « continuer » sur un avertissement
    # Geste critique retenu par le relecteur sur un signal de fraude, avant toute pop-up : le
    # salarié n'a rien vu ni rien choisi, la boîte noire ne lui prête aucun « continuer ».
    flag_geste_retenu: bool = False
    flag_intrusion_physique: bool = False       # accès d'un intrus à un actif/port-leurre
    flag_signalement: bool = False              # le salarié a signalé un mail lui-même
    geste_contexte: str | None = None           # contexte du geste passé outre (« telechargement »…)
    gestes_arretes: int = 0                     # gestes annulés (bon réflexe)
    gestes_passes_outre: int = 0                # gestes passés outre (signal fort)
    # Moindre privilège (V2) : droits accordés / jeton de tâche / utilisés / tentatives hors scope.
    tache: str | None = None
    droits_accordes: list = field(default_factory=list)
    droits_necessaires: list = field(default_factory=list)
    droits_jeton: list = field(default_factory=list)
    scopes_utilises: list = field(default_factory=list)
    tentatives_hors_scope: list = field(default_factory=list)
    flag_droits: bool = False
    # Agent fictif annoncé par la passerelle (details.agent) et droits que l'analyste lui a
    # retirés : {code, libelle, agent, incident_id, session_id, analyste, horodatage}.
    agent: str | None = None
    droits_retires: list = field(default_factory=list)
    # Gouvernance (gouvernance.py) : règles du SOC déclenchées, écarts à l'habitude de l'agent.
    regles_declenchees: list = field(default_factory=list)
    anomalies: list = field(default_factory=list)

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
            "agent": self.agent,
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
        # Un droit retiré par l'analyste n'est plus accordé : il sort des accordés, du jeton
        # et du surplus, et reste visible dans « retires ».
        retires = {r.get("code") for r in self.droits_retires}
        accordes = [s for s in self.droits_accordes if self._code(s) not in retires]
        necessaires = self.droits_necessaires or self.droits_jeton
        codes_necessaires = {self._code(s) for s in necessaires}
        surplus = [self._code(s) for s in accordes if self._code(s) not in codes_necessaires]
        return {
            "accordes": accordes,
            "utilises": list(self.scopes_utilises),
            "necessaires": necessaires,
            "jeton": [c for c in self.droits_jeton if c not in retires],
            "tache": self.tache,
            "surplus": surplus,
            "tentatives_hors_scope": list(self.tentatives_hors_scope),
            "retires": [dict(r) for r in self.droits_retires],
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
    # Sceau de l'incident (journal_scelle.py) : None pour un incident antérieur au scellement.
    sceau: str | None = None


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
        # Diagnostic de reprise des anciennes bases dont le résumé et le journal divergent.
        self.journaux_incomplets: dict[str, dict[str, int]] = {}
        # Index de résolution route/outil -> leurre (pour l'enchaînement lecture->action).
        self.routes_leurres: dict[str, str] = {}
        self.outils_leurres: dict[str, str] = {}
        # Droits retirés par agent fictif (clé : `cle_agent`). Reconstruit au démarrage à
        # partir des sessions, qui portent chacune les retraits qui les concernent.
        self.retraits: dict[str, list[dict]] = {}
        # Têtes des chaînes de hachage du journal (événements, décisions).
        self.tete_evenements = journal_scelle.GENESE
        self.tete_decisions = journal_scelle.GENESE

    @staticmethod
    def cle_agent(sess: Session) -> str:
        """Identité de l'agent : celle annoncée par la passerelle, sinon une par session."""
        return sess.agent or f"orbis-{sess.id}"

    def restaurer(self, donnees: dict) -> None:
        """Prépare un état complet avant de remplacer la mémoire courante.

        Les bases anciennes ne stockaient qu'un résumé de session. Leurs événements
        permettent de retrouver les drapeaux et droits, sans rejouer les décisions.
        """
        from .models import EvenementIn

        def date(valeur):
            if valeur is None:
                return None
            dt = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        nouveau = Store()
        try:
            nouveau.enregistrer_leurres([Leurre(**l) for l in donnees["leurres"]])
            lignes_sessions = {s["id"]: s for s in donnees["sessions"]}
            ids_par_session = {sid: [] for sid in lignes_sessions}
            for ligne in donnees["evenements"]:
                ev = deepcopy(ligne)
                sid = ev["session_id"]
                if sid not in lignes_sessions:
                    raise ValueError(f"Événement {ev['id']} sans session {sid}")
                ids_par_session[sid].append(ev["id"])
                leurre = nouveau.leurres.get(ev["leurre_id"])
                if ev.get("leurre_nature") is None and leurre is not None:
                    ev["leurre_nature"] = leurre.nature
                if lignes_sessions[sid]["etat_json"] is None:
                    nouveau.ingerer(EvenementIn.model_validate(ev), _enregistre=ev)
                else:
                    nouveau.evenements[ev["id"]] = ev

            for sid, ligne in lignes_sessions.items():
                sauvegarde = ligne["etat_json"]
                if sauvegarde is not None:
                    valeurs = deepcopy(sauvegarde)
                    for nom in ("premier_vu", "dernier_vu", "detecte_a", "confine_a",
                                "contre_injection_servie", "flag_lecture"):
                        if nom in valeurs:
                            valeurs[nom] = date(valeurs[nom])
                    for nom in ("leurres_touches", "user_agents"):
                        valeurs[nom] = set(valeurs.get(nom, []))
                    sess = Session(**valeurs)
                    if sess.id != sid or sess.evenement_ids != ids_par_session[sid]:
                        raise ValueError(f"État de session incohérent : {sid}")
                else:
                    sess = nouveau.sessions.get(sid) or Session(id=sid)
                    reels = len(sess.evenement_ids)
                    annonces = ligne["n_evenements"]
                    if reels != annonces:
                        # Ancien writer : un résumé peut être en avance ou en retard sur
                        # les événements réellement écrits. Les deux restent des faits.
                        nouveau.journaux_incomplets[sid] = {
                            "evenements_annonces": annonces,
                            "evenements_persistes": reels,
                        }
                    # Une décision analyste enregistrée dans la session prime le replay.
                    # Si le résumé mentionne plus d'événements que le journal, il garde
                    # aussi son classement : les événements absents ne sont pas inventés.
                    champs = ("source", "etat", "verite_terrain")
                    if reels <= annonces:
                        champs += ("classement", "score", "signaux")
                    for nom in champs:
                        setattr(sess, nom, ligne[nom])
                    for nom in ("premier_vu", "dernier_vu", "detecte_a", "confine_a"):
                        setattr(sess, nom, date(ligne[nom]))
                    sess.leurres_touches |= set(ligne["leurres_touches"])
                if sauvegarde is not None and len(sess.evenement_ids) != ligne["n_evenements"]:
                    raise ValueError(f"Journal incomplet dans un état complet : {sid}")
                nouveau.sessions[sid] = sess

            # Les anciens écrivains ne persistaient pas les touches après ingestion.
            for ligne in donnees["leurres"]:
                leurre = Leurre(**ligne)
                touches = [e for e in nouveau.evenements.values()
                           if e["type"] == "leurre_touche" and e["leurre_id"] == leurre.id]
                if len(touches) > leurre.touches:
                    leurre.touches = len(touches)
                    leurre.premier_touche = touches[0]["horodatage"]
                    leurre.dernier_touche = touches[-1]["horodatage"]
                nouveau.leurres[leurre.id] = leurre

            for sess in nouveau.sessions.values():
                for retrait in sess.droits_retires:
                    liste = nouveau.retraits.setdefault(nouveau.cle_agent(sess), [])
                    if retrait.get("code") not in {r.get("code") for r in liste}:
                        liste.append(dict(retrait))

            nouveau.incidents.clear()
            for ligne in donnees["incidents"]:
                valeurs = deepcopy(ligne)
                sess = nouveau.sessions[valeurs["session_id"]]
                valeurs["cree_a"] = date(valeurs["cree_a"])
                valeurs["decide_a"] = date(valeurs["decide_a"])
                valeurs["riposte_validee"] = bool(valeurs["riposte_validee"])
                inc = Incident(**valeurs)
                if inc.gravite is None:
                    inc.gravite = (incidents.gravite_humaine(inc.type, sess.geste_gravite)
                                   if sess.source in ("humain", "physique")
                                   else incidents.gravite(inc.chaine, sess.source))
                if inc.resume is None:
                    inc.resume = (incidents.resume_humain(inc.chaine, inc.type, sess.flag_passe_outre, sess.flag_geste_retenu)
                                  if sess.source in ("humain", "physique")
                                  else incidents.resume(inc.chaine, sess.classement, sess.source))
                absents = {
                    e.get("evenement_id") for e in inc.chaine
                    if e.get("evenement_id") is not None
                    and e["evenement_id"] not in nouveau.evenements
                }
                if absents:
                    tracage_ancien = lignes_sessions[sess.id]["etat_json"] is None
                    if not tracage_ancien and not all(
                        e.get("source_non_persistee")
                        for e in inc.chaine if e.get("evenement_id") in absents
                    ):
                        raise ValueError(f"Chaîne d'incident sans événement dans un état complet : {inc.id}")
                    if tracage_ancien:
                        for etape in inc.chaine:
                            if etape.get("evenement_id") in absents:
                                etape["source_non_persistee"] = True
                    nouveau.journaux_incomplets.setdefault(sess.id, {
                        "evenements_annonces": lignes_sessions[sess.id]["n_evenements"],
                        "evenements_persistes": len(sess.evenement_ids),
                    })
                nouveau.incidents[inc.id] = inc
            for ligne in donnees["decisions"]:
                if ligne["incident_id"] not in nouveau.incidents:
                    raise ValueError(f"Décision sans incident : {ligne['incident_id']}")
                nouveau.decisions.append({k: v for k, v in ligne.items() if k != "id"})
            nouveau._compteur = max(nouveau.evenements, default=0)
            nouveau.tete_evenements = journal_scelle.tete_journal(nouveau.evenements.values())
            nouveau.tete_decisions = journal_scelle.tete_journal(nouveau.decisions)
            nouveau._incident_seq = max(
                (int(i.removeprefix("INC-")) for i in nouveau.incidents), default=0)
        except Exception as exc:
            raise RuntimeError("État sAIfe incohérent : démarrage interrompu, base conservée") from exc

        with self.lock:
            for nom, valeur in vars(nouveau).items():
                if nom != "lock":
                    setattr(self, nom, valeur)

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

    def ingerer(self, ev, *, _enregistre: dict | None = None) -> dict:
        """Traite un événement (synchrone, rapide) et renvoie le résultat à persister/diffuser."""
        with self.lock:
            horo = _parse_horo(ev.horodatage)
            eid = self._nouvel_id() if _enregistre is None else _enregistre["id"]
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
            # Agent fictif : une nouvelle session hérite des droits déjà retirés à cet agent.
            agent = details.get("agent")
            if sess.source == "interne" and sess.agent is None and isinstance(agent, str) and agent.strip():
                sess.agent = activite._court(agent, 80)
                deja = {r.get("code") for r in sess.droits_retires}
                for retrait in self.retraits.get(sess.agent, []):
                    if retrait.get("code") not in deja:
                        sess.droits_retires.append(dict(retrait))

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
                    # Appel piégé (V1), injection chatbot (V3a), mémoire empoisonnée (V4) :
                    # chacun porte une consigne cachée et spécialise le type d'incident interne.
                    if leurre.nature == "canari_appel":
                        sess.flag_appel = True
                        sess.flag_consigne_cachee = True
                        sess.consigne_leurre_id = sess.consigne_leurre_id or leurre.id
                    if leurre.nature == "injection_chatbot":
                        sess.flag_chatbot = True
                        sess.flag_consigne_cachee = True
                        sess.consigne_leurre_id = sess.consigne_leurre_id or leurre.id
                    if leurre.nature == "memoire_empoisonnee":
                        sess.flag_memoire = True
                        sess.flag_consigne_cachee = True
                        sess.consigne_leurre_id = sess.consigne_leurre_id or leurre.id
                    # Usurpation inter-agent (V3b) : provenance non authentifiée (ASI07).
                    if leurre.nature == "agent_usurpation":
                        sess.flag_inter_agent = True

            # Provenance d'une délégation inter-agent invalide (V3b, OWASP ASI07).
            if isinstance(details.get("provenance_invalide"), dict):
                sess.flag_inter_agent = True

            # Désarmeur de la passerelle : une consigne retirée avant que l'agent la lise.
            desarme = details.get("desarmement")
            if (ev.type == "desarmement" and sess.source == "interne" and isinstance(desarme, dict)
                    and desarme.get("consigne") is True):
                sess.flag_desarme = True

            # --- Pilier humain : le garde du corps du poste ---
            # Un avertissement porte le geste risqué et le choix du salarié (continuer/annuler).
            # Passer outre un avertissement sérieux est un signal fort ; annuler est le bon réflexe.
            if ev.type == "avertissement" and sess.source in ("humain", "physique"):
                sess.flag_humain = True
                cat = details.get("categorie")
                choix = details.get("choix")
                if cat:
                    sess.geste_categorie = cat
                if details.get("origine") == "relecteur" and details.get("quatre_yeux") == "demande":
                    sess.flag_geste_retenu = True
                    if cat:
                        sess.geste_incident_categorie = cat
                    if details.get("gravite") in ("faible", "moyenne", "haute", "critique"):
                        sess.geste_gravite = details["gravite"]
                if choix == "annuler":
                    sess.gestes_arretes += 1
                elif choix == "continuer":
                    sess.gestes_passes_outre += 1
                    sess.flag_passe_outre = True
                    if cat:
                        sess.geste_incident_categorie = cat
                    if isinstance(details.get("contexte"), str):
                        sess.geste_contexte = details["contexte"][:40]
                    g = details.get("gravite")
                    if g in ("faible", "moyenne", "haute", "critique"):
                        sess.geste_gravite = g
                # Intrusion physique : un intrus, pas le salarié protégé. L'accès EST l'incident,
                # même sans « continuer » (personne n'annule à la place de l'intrus).
                if cat == "intrusion_physique" and choix != "annuler":
                    sess.flag_intrusion_physique = True
                    sess.geste_incident_categorie = "intrusion_physique"
            # Le salarié signale un mail (app Mac) : un dossier s'ouvre pour l'analyste, plus
            # grave quand l'analyseur de mails l'avait laissé passer.
            if ev.type == "signalement" and sess.source in ("humain", "physique"):
                sess.flag_humain = True
                sess.flag_signalement = True
                sess.geste_categorie = sess.geste_categorie or "signalement"
                sess.geste_incident_categorie = sess.geste_incident_categorie or "signalement"
                if sess.geste_gravite is None:
                    sess.geste_gravite = ("faible" if details.get("verdict_analyseur") == "frauduleux"
                                          else "moyenne")
            # Canari physique touché (serveur/port-leurre) : intrusion matérielle avérée.
            if ev.type == "leurre_touche" and leurre is not None and (
                leurre.nature == "canari_physique" or sess.source == "physique"
            ):
                sess.flag_intrusion_physique = True
                sess.geste_incident_categorie = "intrusion_physique"

            if details.get("consigne") or details.get("consigne_lue"):
                sess.flag_consigne_cachee = True
                sess.consigne_leurre_id = sess.consigne_leurre_id or ev.leurre_id

            if ev.surface in ("doc", "document", "mail", "appel", "chatbot", "memoire") or ev.type == "entree_agent":
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
                     "charge_utile", "payload", "consigne_outil",
                     # Pilier humain : lien de phishing, secret collé, texte de la pop-up, cible.
                     "message", "lien", "secret", "url_phishing", "cible"),
                ),
            }
            if "document_source" in details:
                # Mail ou document piégé : montré en entier à l'analyste, mais désarmé.
                enreg["details"]["document_source"] = securite.desarmer_document(details["document_source"])
            if "desarmement" in details:
                # Ce que le désarmeur a retiré : gardé pour l'analyste, jamais actionnable.
                enreg["details"]["desarmement"] = securite.desarmer_desarmement(details["desarmement"])
            if cadence_s is not None:
                enreg["details"]["cadence_s"] = cadence_s
            # Virement demandé : montant, bénéficiaire et IBAN masqué, lisibles par le SOC.
            virement = paiements.resumer(ev.outil, details.get("parametres")) if ev.type == "appel_outil" else None
            if virement is not None:
                enreg["details"]["virement"] = virement
            if _enregistre is not None:
                # Le journal est déjà neutralisé ; conserver aussi ses ID et dates de réception.
                enreg = deepcopy(_enregistre)
            self.evenements[eid] = enreg
            sess.evenement_ids.append(eid)
            gouvernance.apres_ingestion(self, sess, enreg, rejeu=_enregistre is not None)

            # Classement.
            sess.classement, sess.score, sess.signaux = classement.classer(sess)
            if sess.classement == "agent_ia" and sess.detecte_a is None:
                sess.detecte_a = horo

            # Scellement : après toute mise à jour de l'événement, avant la boîte noire qui cite
            # son sceau. Un événement relu depuis la base garde le sceau qu'il avait.
            if _enregistre is None:
                self.tete_evenements = journal_scelle.sceller_evenement(enreg, self.tete_evenements)

            # Incident ?
            n_incidents = len(self.incidents)
            incident = self._maj_incident(sess)

            # Consigne à renvoyer à la surface.
            consigne = self._consigne(sess, incident)
            if consigne == "contre_injection" and sess.contre_injection_servie is None:
                sess.contre_injection_servie = horo

            diffusions = [("evenement", enreg), ("session", self._session_vue(sess))]
            if incident is not None:
                diffusions.append(("incident", self._incident_dict(incident)))
            # Fil des agents : l'appel d'outil et son verdict, poussés sur le WS.
            act = activite.entree(enreg, agent=sess.agent,
                                  incident_id=incident.id if incident is not None else None)
            if act is not None:
                diffusions.append(("activite", act))

            session_rep = {
                "id": sess.id,
                "classement": sess.classement,
                "score": sess.score,
                "etat": sess.etat,
            }
            if sess.droits_retires:
                # La passerelle lit ici les droits retirés et refuse les outils qui les exigent.
                session_rep["droits_retires"] = [r.get("code") for r in sess.droits_retires]

            return {
                "reponse": {
                    "session": session_rep,
                    "consigne": consigne,
                },
                "evenement": enreg,
                "session": sess,
                "incident": incident,
                # Vrai quand cet événement vient d'ouvrir l'incident (alerte de décision attendue).
                "incident_nouveau": len(self.incidents) > n_incidents,
                "diffusions": diffusions,
            }

    @staticmethod
    def _type_titre(sess: Session) -> tuple[str, str]:
        """Type d'incident et titre, spécialisés par source et par nature du piège (V2)."""
        # Pilier humain (le maillon faible) : type selon le geste du salarié (ou l'intrusion).
        if sess.source in ("humain", "physique"):
            cat = sess.geste_incident_categorie or sess.geste_categorie
            typ = incidents.type_humain(cat, sess.flag_intrusion_physique)
            return typ, incidents.titre_humain(typ, sess.id, sess.geste_contexte)
        if sess.source != "interne":
            return "externe_agent_ia", f"Agent IA attaquant sur la surface exposée ({sess.id})"
        # Usurpation inter-agent (V3b) : provenance non authentifiée, sans canari « contenu ».
        if sess.flag_inter_agent and not (
            sess.flag_outil_mcp or sess.flag_appel or sess.flag_chatbot or sess.flag_memoire
        ):
            return "interne_inter_agent", f"Agent interne usurpé : délégation non authentifiée (canari {sess.canari_id or '—'})"
        if sess.flag_outil_mcp:
            return "interne_outil_mcp", f"Agent interne piégé par un outil MCP (canari {sess.canari_id or '—'})"
        if sess.flag_appel:
            return "interne_appel", f"Agent interne piégé par une transcription d'appel (canari {sess.canari_id or '—'})"
        if sess.flag_chatbot:
            return "interne_chatbot", f"Chatbot interne détourné par injection de prompt (canari {sess.canari_id or '—'})"
        if sess.flag_memoire:
            return "interne_memoire", f"Agent interne détourné par sa mémoire empoisonnée (canari {sess.canari_id or '—'})"
        if sess.flag_droits and not sess.flag_canari:
            scope = sess.tentatives_hors_scope[-1]["scope_requis"] if sess.tentatives_hors_scope else "—"
            return "interne_droits", f"Agent interne hors de son périmètre de droits (droit {scope})"
        if not sess.flag_canari and (sess.regles_declenchees or sess.anomalies):
            return gouvernance.type_titre(sess)
        if sess.flag_desarme and not sess.flag_canari:
            return "interne_desarme", "Consigne cachée retirée avant que l’agent la lise"
        if sess.canari_nature == "envoi_externe":
            return "interne_envoi_externe", "Envoi hors d’Orbis Pay retenu avant exécution"
        # Médiation universelle de la passerelle (interne/orbis/mediation.py) : règle C-8A61, C-5B27
        # ou C-3F90 en premier canari touché.
        mediation = {
            "outil_inconnu": ("interne_outil_inconnu", "Outil absent de l’inventaire de l’agent, retenu avant exécution"),
            "canal_detourne": ("interne_canal_detourne", "Outil détourné en canal de sortie, retenu avant exécution"),
            "outil_modifie": ("interne_outil_modifie", "Outil MCP modifié en cours de session, appel retenu"),
        }.get(sess.canari_nature or "")
        if mediation is not None:
            return mediation
        return "interne_canari", f"Agent IA piégé en interne (canari {sess.canari_id or '—'})"

    def _maj_incident(self, sess: Session) -> Incident | None:
        inc = next((i for i in self.incidents.values() if i.session_id == sess.id), None)
        if sess.source in ("humain", "physique"):
            # Pilier humain : ouvre sur un geste passé outre, ou une intrusion physique.
            # Un geste annulé (bon réflexe) n'ouvre rien.
            est_incident = (sess.flag_passe_outre or sess.flag_intrusion_physique or sess.flag_signalement
                            or sess.flag_geste_retenu)
        elif sess.source == "externe":
            est_incident = sess.classement == "agent_ia"
        else:  # interne
            est_incident = (
                sess.flag_canari
                or sess.flag_droits
                or sess.flag_inter_agent
                or sess.flag_desarme
                or sess.classement == "agent_ia"
                or bool(sess.regles_declenchees or sess.anomalies)
            )
        if not est_incident and inc is None:
            return None
        typ, titre = self._type_titre(sess)
        if inc is not None and sess.id in self.journaux_incomplets and (
            not est_incident or (typ == "interne_canari" and inc.type != "interne_canari")
        ):
            # Le signal qui a spécialisé l'incident peut manquer dans l'ancien journal.
            typ, titre = inc.type, inc.titre
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
            if sess.source == "interne" and sess.etat == "active" and gouvernance.suspendre_a_l_ouverture(typ):
                sess.etat = "suspendue"
        # Type et titre se rafraîchissent à chaque passage : les drapeaux évoluent (le canari MCP
        # peut tomber après l'ouverture, et un incident droits peut se préciser).
        if inc.type != "externe_agent_ia":
            inc.type, inc.titre = typ, titre
        evs = [self.evenements[i] for i in sess.evenement_ids]
        ancienne_chaine = inc.chaine
        if sess.source in ("humain", "physique"):
            inc.chaine = incidents.construire_chaine_humaine(evs, self.leurres)
            inc.gravite = incidents.gravite_humaine(typ, sess.geste_gravite)
            inc.resume = incidents.resume_humain(inc.chaine, typ, sess.flag_passe_outre, sess.flag_geste_retenu)
        else:
            inc.chaine = incidents.construire_chaine(evs, self.leurres)
            inc.gravite = incidents.gravite(inc.chaine, sess.source)
            inc.resume = incidents.resume(inc.chaine, sess.classement, sess.source)
        if sess.id in self.journaux_incomplets:
            # Un ancien incident peut garder une étape dont l'événement source n'a
            # jamais été écrit. Ne pas l'effacer lors d'un événement ultérieur.
            manquantes = [
                e for e in ancienne_chaine
                if e.get("evenement_id") not in self.evenements and e not in inc.chaine
            ]
            if manquantes:
                ordre = (
                    ["contexte", "action_risquee", "avertissement", "choix", "consequence"]
                    if sess.source in ("humain", "physique") else incidents.ORDRE_ETAPES
                )
                inc.chaine.extend(manquantes)
                inc.chaine.sort(key=lambda e: incidents.cle_chronologique(e, ordre))
                for position, etape in enumerate(inc.chaine):
                    etape["ordre"] = position
                if sess.source in ("humain", "physique"):
                    inc.gravite = incidents.gravite_humaine(typ, sess.geste_gravite)
                    inc.resume = incidents.resume_humain(inc.chaine, typ, sess.flag_passe_outre, sess.flag_geste_retenu)
                else:
                    inc.gravite = incidents.gravite(inc.chaine, sess.source)
                    inc.resume = incidents.resume(inc.chaine, sess.classement, sess.source)
        gouvernance.ajuster(inc, sess)
        journal_scelle.sceller_incident(inc, self.decisions, self.evenements)
        return inc

    def _incident_dict(self, inc: Incident) -> dict:
        """Objet incident au format lu par la console (+ champs internes tolérés)."""
        sess = self.sessions.get(inc.session_id)
        decisions = [
            {"action": d["action"], "analyste": d["analyste"], "horodatage": d["horodatage"]}
            for d in self.decisions
            if d["incident_id"] == inc.id
        ]
        vue_droits = sess.droits_console() if sess else None
        d = {
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
            "droits": vue_droits,
            # Correctif en un clic : droits en trop que l'analyste peut retirer à l'agent.
            "droits_retirables": self._retirables(vue_droits),
            "correctifs": [dict(r) for r in (sess.droits_retires if sess else [])
                           if r.get("incident_id") == inc.id],
        }
        if sess is None:
            return d
        evs = [self.evenements[i] for i in sess.evenement_ids if i in self.evenements]
        # Actes de la console sur ce dossier (motifs, identité levée, remédiations), scellés.
        d["journal_console"] = self._journal_console(inc.id, evs)
        if sess.source in ("humain", "physique"):
            d.update(self._vue_humaine(sess, evs, d["journal_console"]))
            from . import relecteur  # import local : le relecteur dépend du store
            # Relecteur IA : dernier geste relu et suivi de l'analyste (« à confirmer » tant que rien).
            d["relecteur"] = relecteur.resume_incident(inc.id, evs, self.decisions)
            d = identites.masqueur(sess.id, evs)(d)
        return d

    @staticmethod
    def _journal_console(iid: str, evs: list[dict]) -> list[dict]:
        sortie = []
        for e in evs:
            det = e.get("details") or {}
            if e.get("type") != "console" or det.get("incident_id") != iid:
                continue
            sortie.append({k: det[k] for k in ("acte", "analyste", "action", "motif", "message", "domaine")
                           if det.get(k) is not None} | {"horodatage": e.get("horodatage"),
                                                         "evenement_id": e.get("id")})
        return sortie

    @staticmethod
    def _vue_humaine(sess: Session, evs: list[dict], journal: list[dict]) -> dict:
        """Ce que la console lit d'un dossier salarié : identité pseudonyme, contexte du geste,
        demande de quatre yeux et son issue."""
        ident = identites.identite(sess.id, evs)
        ident["revelations"] = [{k: j.get(k) for k in ("analyste", "horodatage", "motif")}
                                for j in journal if j.get("acte") == "reveler_identite"]
        avert = [e for e in evs if e.get("type") == "avertissement"]
        principal = next((e for e in reversed(avert) if (e.get("details") or {}).get("choix") == "continuer"),
                         avert[-1] if avert else None)
        contexte = (principal.get("details") or {}).get("contexte") if principal else None
        if sess.flag_signalement and not sess.flag_passe_outre:
            contexte = "signalement"
        demande = next((e for e in evs if (e.get("details") or {}).get("quatre_yeux") == "demande"), None)
        quatre_yeux = None
        if demande is not None:
            dd = demande.get("details") or {}
            issue = next(((e.get("details") or {}).get("quatre_yeux") for e in reversed(evs)
                          if e.get("type") == "riposte"
                          and (e.get("details") or {}).get("quatre_yeux") in ("accorde", "refuse", "expire")), None)
            quatre_yeux = {"demande_id": dd.get("demande_id"), "delai_s": dd.get("delai_s"),
                           "horodatage": demande.get("horodatage"), "issue": issue}
        return {"identite": ident, "contexte_humain": contexte if isinstance(contexte, str) else None,
                "quatre_yeux": quatre_yeux}

    @staticmethod
    def _retirables(vue: dict | None) -> list[dict]:
        if not vue:
            return []
        libelles = {
            Session._code(s): (s.get("libelle") if isinstance(s, dict) else None)
            for s in vue["accordes"]
        }
        return [{"code": c, "libelle": libelles.get(c) or c} for c in vue["surplus"]]

    def _consigne(self, sess: Session, incident: Incident | None) -> str:
        if sess.etat == "coupee":
            return "bloquer"
        if sess.etat == "suspendue":
            return "suspendre"
        # Pilier humain : le garde du corps du poste prévient et escalade, il ne bloque jamais le PC.
        if sess.source in ("humain", "physique"):
            return "aucune"
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
            d = sess.detail(evs)
            if sess.source in ("humain", "physique"):
                # Poste d'un salarié : pseudonyme à la place du nom, URL sans paramètres.
                d["identite"] = identites.identite(sess.id, evs)
                d = identites.masqueur(sess.id, evs)(d)
            return d

    def _session_vue(self, sess: Session) -> dict:
        """Session telle que l'API la montre : pseudonymisée pour le poste d'un salarié."""
        d = sess.abrege()
        if sess.source in ("humain", "physique"):
            evs = [self.evenements[i] for i in sess.evenement_ids if i in self.evenements]
            d["identite"] = identites.identite(sess.id, evs)
            d = identites.masqueur(sess.id, evs)(d)
        return d

    def etat_session(self, sid: str) -> dict | None:
        with self.lock:
            sess = self.sessions.get(sid)
            if sess is None:
                return None
            return {"id": sess.id, "etat": sess.etat, "classement": sess.classement, "score": sess.score}

    def liste_sessions(self) -> list[dict]:
        with self.lock:
            return [self._session_vue(s) for s in self.sessions.values()]

    def liste_incidents(self) -> list[dict]:
        with self.lock:
            return [self._incident_dict(i) for i in self.incidents.values()]

    def documents_source(self, iid: str) -> dict | None:
        """Documents piégés lus par l'agent de l'incident, complets et désarmés."""
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            documents = [
                {"maillon": e.get("ordre"), "evenement_id": e.get("evenement_id"),
                 "horodatage": e.get("horodatage"), **e["document_source"]}
                for e in inc.chaine if isinstance(e.get("document_source"), dict)
            ]
            return {"incident_id": iid, "documents": documents}

    def liste_activite(self, limite: int = 50) -> list[dict]:
        """Derniers appels d'outil vus par la passerelle interne, du plus récent au plus ancien."""
        with self.lock:
            incident_par_session: dict[str, str] = {}
            for inc in self.incidents.values():
                incident_par_session.setdefault(inc.session_id, inc.id)
            sortie: list[dict] = []
            for ev in reversed(self.evenements.values()):
                if len(sortie) >= limite:
                    break
                sess = self.sessions.get(ev.get("session_id"))
                act = activite.entree(ev, agent=sess.agent if sess else None,
                                      incident_id=incident_par_session.get(ev.get("session_id")))
                if act is not None:
                    sortie.append(act)
            return sortie

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
                        "agent": sess.agent,
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
            d["session"] = self._session_vue(sess) if sess else None
            d["signaux"] = sess.signaux if sess else []
            d["leurres_touches"] = sorted(sess.leurres_touches) if sess else []
            return d

    def decider(self, iid: str, action: str, analyste: str, motif: str = "") -> dict | None:
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            est_humain = inc.type.startswith("humain_")
            if est_humain and action not in ("clore", "ignorer", "accorder", "refuser"):
                raise ValueError("Une décision sur un salarié ne peut pas couper son poste")
            if action in ("accorder", "refuser"):
                # Quatre yeux : seul un geste suspendu du salarié s'accorde ou se refuse.
                if not est_humain:
                    raise ValueError("« accorder » et « refuser » valent pour le geste d’un salarié.")
                evs = [self.evenements[i] for i in (sess.evenement_ids if sess else [])]
                if not any((e.get("details") or {}).get("quatre_yeux") == "demande" for e in evs):
                    raise ValueError("Aucun geste de ce dossier n’attend la validation d’un analyste.")
            # Sur un agent, « clore » ferme le dossier sans toucher à la session : c'est la
            # suite d'une action déjà refusée d'office. Un appel encore retenu le reste.
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
                if sess and not est_humain:
                    sess.etat = "active"
                inc.statut = "ignore"
            elif action in ("clore", "accorder", "refuser"):
                inc.statut = "clos"
            inc.analyste = analyste
            inc.decide_a = moment
            inc.action = action
            journal = {
                "incident_id": iid,
                "action": action,
                "analyste": analyste,
                "horodatage": moment.isoformat(),
            }
            self.tete_decisions = journal_scelle.sceller_decision(journal, self.tete_decisions)
            self.decisions.append(journal)
            notes = []
            if motif and motif.strip() and sess is not None:
                # Le motif entre au journal scellé, à côté de la décision qu'il justifie.
                notes.append(self._note_console(inc, sess, "decision", analyste,
                                                {"action": action, "motif": activite._court(motif, 200)}))
            journal_scelle.sceller_incident(inc, self.decisions, self.evenements)
            diffusions = [("incident", self._incident_dict(inc))]
            if sess:
                diffusions.append(("session", self._session_vue(sess)))
            return {"incident": self.incident_detail(iid), "diffusions": diffusions, "journal": journal,
                    "evenements": notes}

    # ----- Actes de la console, scellés -----
    def _note_console(self, inc: Incident, sess: Session, acte: str, analyste: str, details: dict) -> dict:
        """Ajoute au journal scellé un acte de l'analyste sur ce dossier (événement `console`).
        Il ne passe pas par le tri et n'entre pas dans la boîte noire."""
        moment = maintenant()
        eid = self._nouvel_id()
        enreg = {
            "id": eid, "horodatage": moment.isoformat(), "recu_a": moment.isoformat(),
            "source": sess.source, "surface": "console", "type": "console", "session_id": sess.id,
            "leurre_id": None, "leurre_nature": None, "ip": None, "user_agent": None,
            "methode": None, "chemin": None, "outil": None,
            "details": {"acte": acte, "analyste": activite._court(analyste or "inconnu", 60),
                        "incident_id": inc.id, **details},
        }
        self.tete_evenements = journal_scelle.sceller_evenement(enreg, self.tete_evenements)
        self.evenements[eid] = enreg
        sess.evenement_ids.append(eid)
        return enreg

    def reveler_identite(self, iid: str, motif: str, analyste: str) -> dict | None:
        """Lève l'anonymat du salarié d'un dossier. Le motif est obligatoire ; l'acte est
        scellé, le nom n'est jamais écrit au journal et ne sort que dans cette réponse."""
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            if sess is None or sess.source not in ("humain", "physique"):
                raise ValueError("Ce dossier ne concerne pas un salarié.")
            motif = (motif or "").strip()
            if len(motif) < 5:
                raise ValueError("Un motif est obligatoire pour révéler une identité (5 caractères au moins).")
            evs = [self.evenements[i] for i in sess.evenement_ids]
            ident = identites.identite(sess.id, evs)
            note = self._note_console(inc, sess, "reveler_identite", analyste,
                                      {"motif": activite._court(motif, 200),
                                       "pseudonyme": ident["pseudonyme"]})
            p = identites.personne(sess.id, evs)
            reponse = {
                "incident_id": iid, "pseudonyme": ident["pseudonyme"], "service": ident["service"],
                "nom": p["nom"] if p else None, "poste": p["poste"] if p else None,
                "analyste": note["details"]["analyste"], "motif": note["details"]["motif"],
                "horodatage": note["horodatage"],
                "message": (f"Identité révélée à {note['details']['analyste']}. L’acte est noté au journal scellé."
                            if p else "Ce poste n’est rattaché à aucun salarié de l’annuaire. L’acte est noté."),
            }
            inc_vue = self._incident_dict(inc)
            return {"reponse": reponse, "evenement": note, "session": sess, "incident": inc,
                    "diffusions": [("incident", inc_vue)]}

    _REMEDIATIONS = {
        "reinitialiser_mot_de_passe": "Mot de passe de {qui} réinitialisé : il en choisira un nouveau à sa prochaine connexion.",
        "fermer_sessions": "Sessions ouvertes de {qui} fermées sur tous ses appareils.",
        "bloquer_domaine": "{domaine} est bloqué pour tous les salariés d’Orbis Pay.",
    }

    @staticmethod
    def _domaine_en_cause(evs: list[dict]) -> str | None:
        """Domaine du lien, du site sosie ou de l'expéditeur en cause, désarmé (`[.]`)."""
        import re as _re
        for e in reversed(evs):
            det = e.get("details") or {}
            doc = det.get("document_source") if isinstance(det.get("document_source"), dict) else {}
            for brut in (det.get("lien"), det.get("url"), det.get("url_phishing"), det.get("cible"),
                         doc.get("expediteur"), det.get("expediteur")):
                if not isinstance(brut, str):
                    continue
                texte = brut.replace("[leurre, neutralisé]", "").replace("[.]", ".")
                m = _re.search(r"(?:@|//)?((?:[a-z0-9-]+\.)+[a-z]{2,})", texte, _re.IGNORECASE)
                if m and not m.group(1).lower().endswith(config.ENTITE_DOMAINE):
                    return m.group(1).lower().replace(".", "[.]")
        return None

    def remedier(self, iid: str, action: str, analyste: str) -> dict | None:
        """Action simulée sur le compte d'un salarié ou sur un domaine, notée au journal scellé."""
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            if sess is None or sess.source not in ("humain", "physique"):
                raise ValueError("Ces actions valent pour le dossier d’un salarié.")
            if action not in self._REMEDIATIONS:
                raise ValueError(f"Action inconnue : {activite._court(action, 40)}")
            evs = [self.evenements[i] for i in sess.evenement_ids]
            deja = next((j for j in self._journal_console(iid, evs)
                         if j.get("acte") == "remediation" and j.get("action") == action), None)
            if deja is not None:
                raise ValueError(f"Déjà fait par {deja.get('analyste')} à {str(deja.get('horodatage'))[11:16]}.")
            domaine = self._domaine_en_cause(evs) if action == "bloquer_domaine" else None
            if action == "bloquer_domaine" and domaine is None:
                raise ValueError("Aucun domaine extérieur n’est en cause dans ce dossier.")
            qui = identites.identite(sess.id, evs)["pseudonyme"]
            message = self._REMEDIATIONS[action].format(qui=qui, domaine=domaine)
            details = {"action": action, "message": message, "simulation": True}
            if domaine:
                details["domaine"] = domaine
            note = self._note_console(inc, sess, "remediation", analyste, details)
            return {"reponse": {"incident_id": iid, "action": action, "message": message,
                                "domaine": domaine, "simulation": True,
                                "analyste": note["details"]["analyste"], "horodatage": note["horodatage"],
                                "incident": self.incident_detail(iid)},
                    "evenement": note, "session": sess, "incident": inc,
                    "diffusions": [("incident", self._incident_dict(inc))]}


    # ----- Correctif en un clic : moindre privilège -----
    def retirer_droit(self, iid: str, droit: str, analyste: str) -> dict | None:
        """Retire à l'agent un droit en trop pour sa tâche. Le retrait vaut pour cette session et
        pour les sessions à venir du même agent fictif ; il entre dans la boîte noire comme un
        maillon « correctif ». Lève ValueError si le droit n'est pas retirable."""
        with self.lock:
            inc = self.incidents.get(iid)
            if inc is None:
                return None
            sess = self.sessions.get(inc.session_id)
            if sess is None or sess.source != "interne":
                raise ValueError("Cet incident ne concerne pas un agent interne : aucun droit à retirer.")
            avant = sess.droits_console()
            if avant is None:
                raise ValueError("Aucun droit connu pour l’agent de cet incident.")
            nom = activite._court(droit, 60)
            if droit in {r.get("code") for r in sess.droits_retires}:
                raise ValueError(f"Le droit {nom} est déjà retiré à cet agent.")
            if droit not in avant["surplus"]:
                retirables = ", ".join(avant["surplus"]) or "aucun"
                raise ValueError(
                    f"{nom} n’est pas un droit en trop pour la tâche {avant['tache'] or 'en cours'}. "
                    f"Droits retirables : {retirables}."
                )

            # Le correctif suit le dernier maillon même si l'horloge de la passerelle avance.
            moment = max(maintenant(), sess.dernier_vu)
            cle = self.cle_agent(sess)
            libelle = next(
                (s.get("libelle") for s in sess.droits_accordes
                 if isinstance(s, dict) and s.get("code") == droit and s.get("libelle")),
                droit,
            )
            # Outils vus dans la session qui exigeaient ce droit (refusés désormais).
            outils = {t.get("outil") for t in sess.tentatives_hors_scope if t.get("scope_requis") == droit}
            for i in sess.evenement_ids:
                ev = self.evenements[i]
                d = ev.get("details") or {}
                if ev.get("outil") and d.get("scope_requis") == droit:
                    outils.add(ev["outil"])
            outils_tries = sorted(o for o in outils if o)
            retrait = {
                "code": droit, "libelle": libelle, "agent": cle, "incident_id": iid,
                "session_id": sess.id, "analyste": activite._court(analyste or "inconnu", 60),
                "horodatage": moment.isoformat(),
            }
            self.retraits.setdefault(cle, []).append(retrait)
            touchees = [s for s in self.sessions.values()
                        if s.source == "interne" and self.cle_agent(s) == cle]
            for s in touchees:
                if droit not in {r.get("code") for r in s.droits_retires}:
                    s.droits_retires.append(dict(retrait))

            # Maillon « correctif » : un événement de la session, sans passer par le tri
            # (il ne dit rien du comportement de l'agent).
            eid = self._nouvel_id()
            enreg = {
                "id": eid,
                "horodatage": moment.isoformat(),
                "recu_a": moment.isoformat(),
                "source": sess.source,
                "surface": "console",
                "type": "correctif",
                "session_id": sess.id,
                "leurre_id": None,
                "leurre_nature": None,
                "ip": None,
                "user_agent": None,
                "methode": None,
                "chemin": None,
                "outil": None,
                "details": {
                    "maillon": "correctif", "action": "retirer_droit", "droit": droit,
                    "libelle": libelle, "agent": cle, "analyste": retrait["analyste"],
                    "incident_id": iid, "outils": outils_tries,
                    "accordes_avant": [Session._code(s) for s in avant["accordes"]],
                },
            }
            # La vue « après » ne dépend que des retraits : elle complète l'événement avant son
            # scellement, puis le maillon correctif cite ce sceau.
            apres = sess.droits_console()
            enreg["details"]["accordes_apres"] = [Session._code(s) for s in apres["accordes"]]
            self.tete_evenements = journal_scelle.sceller_evenement(enreg, self.tete_evenements)
            self.evenements[eid] = enreg
            sess.evenement_ids.append(eid)
            self._maj_incident(sess)
            maillon = next((e for e in inc.chaine if e.get("evenement_id") == eid), None)

            incidents_maj = [inc]
            for s in touchees:
                autre = next((i for i in self.incidents.values() if i.session_id == s.id), None)
                if autre is not None and autre not in incidents_maj:
                    incidents_maj.append(autre)
            diffusions = [("evenement", enreg)]
            diffusions += [("session", self._session_vue(s)) for s in touchees]
            diffusions += [("incident", self._incident_dict(i)) for i in incidents_maj]

            refuses = ", ".join(outils_tries) if outils_tries else "tout outil qui l’exige"
            reponse = {
                "incident_id": iid,
                "droit": droit,
                "libelle": libelle,
                "agent": cle,
                "avant": avant,
                "apres": apres,
                "maillon": maillon,
                "sessions_concernees": [s.id for s in touchees],
                "message": (f"Droit {droit} retiré à l’agent {cle}. La passerelle refusera "
                            f"{refuses} dans cette session et dans ses prochaines sessions."),
                "incident": self.incident_detail(iid),
            }
            return {"reponse": reponse, "evenement": enreg, "sessions": touchees,
                    "incidents": incidents_maj, "diffusions": diffusions}


store = Store()
