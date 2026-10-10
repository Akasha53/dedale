"""Inventaire des agents IA d'Orbis Pay (fonction « Identifier » du NIST CSF).

Le registre ci-dessous est la liste des agents déclarés par l'entreprise fictive : leur rôle,
leurs outils, les droits qu'on leur a accordés et ceux dont leur travail a besoin. Le
backend y ajoute ce qu'il observe : sessions, appels, droits réellement utilisés, dernière
activité, incidents, habitude de travail (anomalies.py) et résistance mesurée par le banc
(resistance.py). Le niveau de risque se calcule à partir de ces faits, et chaque point du
score est expliqué en français simple.

Les profils correspondent à `interne/orbis/agents_orbis.py` (même identifiants, mêmes
droits). Tout est fictif.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# Libellés des droits, lisibles par un analyste (repris de interne/orbis/droits.py).
LIBELLES = {
    "mail:lire": "Lire la boîte mail",
    "mail:envoyer": "Envoyer des mails",
    "document:lire": "Lire les documents internes",
    "coffre:lire": "Lire le coffre de clés d'API",
    "rapport:envoyer": "Envoyer un rapport interne",
    "paiement:executer": "Exécuter un virement",
    "contact:exporter": "Exporter la base contacts",
    "outil:mcp": "Appeler les outils MCP",
    "resume:local": "Résumer en local",
    "appel:lire": "Lire les transcriptions d'appels",
    "memoire:lire": "Lire la mémoire long terme",
    "memoire:ecrire": "Écrire dans la mémoire long terme",
    "banque:lire": "Lire les relevés bancaires",
    "banque:exporter": "Exporter des lignes bancaires",
    "ticket:lire": "Lire les tickets du support",
    "client:lire": "Lire la fiche d'un client",
    "client:repondre": "Répondre à un client",
    "politique:proposer": "Proposer des règles",
}

# Droits dont l'abus coûte cher, avec ce qu'ils ouvrent, en clair.
SENSIBLES = {
    "coffre:lire": "le coffre à mots de passe",
    "paiement:executer": "les virements",
    "contact:exporter": "l'export de la base contacts",
    "mail:envoyer": "l'envoi de mails",
    "memoire:ecrire": "l'écriture dans sa mémoire",
    "banque:exporter": "l'export des lignes bancaires",
}


def _outil(nom: str, droit: str | None, libelle: str, sortant: bool = False) -> dict:
    return {"nom": nom, "droit": droit, "libelle": libelle, "sortant": sortant}


# Registre déclaré des agents fictifs. `libelle` sert dans les phrases (« l'agent de … »).
AGENTS: list[dict] = [
    {
        "id": "orbis-assistant",
        "nom": "Agent de tri des mails",
        "libelle": "l'agent de tri des mails",
        "role": "Trie la boîte mail partagée, résume les mails et prépare les rapports internes.",
        "service": "Opérations",
        "proprietaire": "Direction des opérations",
        "outils": [
            _outil("lire_mail", "mail:lire", "Lire la boîte mail"),
            _outil("chercher_document", "document:lire", "Chercher un document interne"),
            _outil("resumer", "resume:local", "Résumer un texte"),
            _outil("envoyer_rapport", "rapport:envoyer", "Envoyer un rapport", sortant=True),
            _outil("executer_paiement", "paiement:executer", "Exécuter un virement", sortant=True),
            _outil("lire_coffre", "coffre:lire", "Lire une entrée du coffre de clés"),
            _outil("exporter_contacts", "contact:exporter", "Exporter la base contacts", sortant=True),
            _outil("chercher_appel", "appel:lire", "Lire une transcription d'appel"),
            _outil("lire_memoire", "memoire:lire", "Relire sa mémoire"),
            _outil("memoriser", "memoire:ecrire", "Écrire dans sa mémoire"),
            _outil("convertir_montant", "outil:mcp", "Convertir un montant (MCP externe)", sortant=True),
            _outil("verifier_conformite", "outil:mcp", "Vérifier la conformité (MCP externe)", sortant=True),
        ],
        "accordes": [
            "mail:lire", "mail:envoyer", "document:lire", "coffre:lire", "rapport:envoyer",
            "paiement:executer", "contact:exporter", "outil:mcp", "resume:local", "appel:lire",
            "memoire:lire", "memoire:ecrire",
        ],
        "necessaires": ["mail:lire", "document:lire", "resume:local", "rapport:envoyer", "outil:mcp"],
    },
    {
        "id": "orbis-rapprochement",
        "nom": "Agent de rapprochement bancaire",
        "libelle": "l'agent de rapprochement bancaire",
        "role": "Rapproche les relevés bancaires et les factures, puis envoie les écarts à la comptabilité.",
        "service": "Finance",
        "proprietaire": "Direction financière",
        "outils": [
            _outil("lire_releve", "banque:lire", "Lire un relevé bancaire"),
            _outil("chercher_document", "document:lire", "Chercher une facture"),
            _outil("resumer", "resume:local", "Résumer les écarts"),
            _outil("exporter_lignes", "banque:exporter", "Exporter des lignes bancaires", sortant=True),
            _outil("envoyer_rapport", "rapport:envoyer", "Envoyer le rapport d'écarts", sortant=True),
            _outil("executer_paiement", "paiement:executer", "Exécuter un virement", sortant=True),
            _outil("lire_coffre", "coffre:lire", "Lire une entrée du coffre de clés"),
        ],
        "accordes": [
            "banque:lire", "banque:exporter", "document:lire", "resume:local", "rapport:envoyer",
            "paiement:executer", "coffre:lire",
        ],
        "necessaires": ["banque:lire", "banque:exporter", "document:lire", "resume:local", "rapport:envoyer"],
    },
    {
        "id": "orbis-support",
        "nom": "Agent de support client",
        "libelle": "l'agent de support client",
        "role": "Lit les tickets des clients PME, consulte leur fiche et leur répond.",
        "service": "Relation client",
        "proprietaire": "Direction de la relation client",
        "outils": [
            _outil("lire_ticket", "ticket:lire", "Lire un ticket"),
            _outil("chercher_client", "client:lire", "Lire la fiche d'un client"),
            _outil("resumer", "resume:local", "Résumer un échange"),
            _outil("repondre_client", "client:repondre", "Répondre au client", sortant=True),
            _outil("exporter_contacts", "contact:exporter", "Exporter la base contacts", sortant=True),
            _outil("memoriser", "memoire:ecrire", "Écrire dans sa mémoire"),
        ],
        "accordes": [
            "ticket:lire", "client:lire", "client:repondre", "resume:local", "contact:exporter",
            "memoire:ecrire",
        ],
        "necessaires": ["ticket:lire", "client:lire", "client:repondre", "resume:local"],
    },
    {
        # L'agent de Dédale qui lit la barre « Écrire une règle » (agent_regles.py). Une
        # instance par phrase, fermée après ; il propose, l'analyste applique. Aucune règle du
        # SOC ne peut le viser (`politiques.agents_cibles`).
        "id": "dedale-regles",
        "nom": "Agent des règles",
        "libelle": "l'agent des règles",
        "role": ("Lit une phrase de l'analyste et prépare un changement de règle, que l'analyste "
                 "applique ou non. Une session par phrase, fermée aussitôt après."),
        "service": "SOC",
        "proprietaire": "SOC Dédale",
        "dedale": True,
        "outils": [
            _outil("lire_regles", "politique:proposer", "Lire les règles actives"),
            _outil("lire_inventaire", "politique:proposer", "Lire l'inventaire des agents"),
            _outil("proposer_regle", "politique:proposer", "Proposer une règle"),
            _outil("proposer_modification", "politique:proposer", "Proposer de modifier une règle"),
            _outil("proposer_retrait", "politique:proposer", "Proposer de retirer une règle"),
            _outil("proposer_retrait_droits", "politique:proposer", "Proposer de retirer des droits en trop"),
        ],
        "accordes": ["politique:proposer"],
        "necessaires": ["politique:proposer"],
    },
]

PAR_ID = {a["id"]: a for a in AGENTS}

# Fenêtre des incidents « récents » dans le calcul du risque.
FENETRE_RECENTE = timedelta(hours=24)
SEUIL_MOYEN, SEUIL_ELEVE = 4, 8
POINTS_GRAVITE = {"critique": 3, "haute": 3, "moyenne": 2, "faible": 1}


def libelle_droit(code: str) -> str:
    return LIBELLES.get(code, code)


def nom(agent_id: str | None) -> str:
    """Nom lisible d'un agent : celui du registre, sinon son identifiant."""
    if agent_id in PAR_ID:
        return PAR_ID[agent_id]["nom"]
    return agent_id or "agent interne"


def libelle_agent(agent_id: str | None) -> str:
    """« l'agent de tri des mails », pour composer une phrase."""
    if agent_id in PAR_ID:
        return PAR_ID[agent_id]["libelle"]
    return f"l'agent {agent_id}" if agent_id else "l'agent interne"


def outil_sortant(nom_outil: str | None) -> bool:
    return any(o["nom"] == nom_outil and o["sortant"] for a in AGENTS for o in a["outils"])


def _code(scope) -> str | None:
    return scope.get("code") if isinstance(scope, dict) else scope


def _avec_libelles(codes) -> list[dict]:
    return [{"code": c, "libelle": libelle_droit(c)} for c in codes]


def _date(valeur) -> datetime | None:
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    if isinstance(valeur, str) and valeur:
        try:
            dt = datetime.fromisoformat(valeur.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _observe(store, agent_id: str) -> dict:
    """Ce que le backend a vu de cet agent : sessions, appels, droits, incidents."""
    sessions = [s for s in store.sessions.values()
                if s.source == "interne" and s.agent == agent_id]
    ids = {s.id for s in sessions}
    utilises: list[str] = []
    annonces: list[str] = []
    appels = 0
    derniere = None
    for s in sessions:
        for c in s.scopes_utilises:
            if c not in utilises:
                utilises.append(c)
        for c in (_code(x) for x in s.droits_accordes):
            if c and c not in annonces:
                annonces.append(c)
        if derniere is None or s.dernier_vu > derniere:
            derniere = s.dernier_vu
        for i in s.evenement_ids:
            ev = store.evenements.get(i) or {}
            if ev.get("type") == "appel_outil" and (ev.get("details") or {}).get("maillon") != "intention":
                appels += 1
    incidents = sorted((i for i in store.incidents.values() if i.session_id in ids),
                       key=lambda i: i.id)
    return {"sessions": len(sessions), "appels": appels, "utilises": utilises,
            "annonces": annonces, "derniere": derniere, "incidents": incidents}


def _risque(fiche: dict, obs: dict, resistance: dict | None, maintenant: datetime) -> dict:
    """Niveau de risque : une somme de points, chacun expliqué par une phrase courte."""
    raisons: list[dict] = []
    surplus = fiche["droits"]["surplus"]
    if surplus:
        sensibles = [c for c in surplus if c in SENSIBLES]
        points = min(8, len(surplus) + len(sensibles))
        texte = (f"{len(surplus)} droit{'s' if len(surplus) > 1 else ''} en trop pour son travail"
                 if len(surplus) > 1 else "1 droit en trop pour son travail")
        if sensibles:
            texte += ", dont " + ", ".join(SENSIBLES[c] for c in sensibles)
        raisons.append({"code": "droits_en_trop", "points": points, "texte": texte + ".",
                        "references": surplus})
    sortants = [o["nom"] for o in fiche["outils"] if o["sortant"]
                and o["droit"] not in fiche["droits"]["retires"]]
    if sortants:
        points = 2 if len(sortants) >= 3 else 1
        raisons.append({"code": "outils_sortants", "points": points,
                        "texte": (f"Peut faire sortir des données ou de l'argent par "
                                  f"{len(sortants)} outil{'s' if len(sortants) > 1 else ''}."),
                        "references": sortants})
    recents = [i for i in obs["incidents"] if maintenant - _date(i.cree_a) <= FENETRE_RECENTE]
    if recents:
        points = min(9, sum(POINTS_GRAVITE.get(i.gravite, 2) for i in recents))
        raisons.append({"code": "incidents_recents", "points": points,
                        "texte": (f"{len(recents)} incident{'s' if len(recents) > 1 else ''} "
                                  "ces dernières 24 heures."),
                        "references": [i.id for i in recents]})
    if resistance is None:
        raisons.append({"code": "resistance_inconnue", "points": 1,
                        "texte": "Résistance aux contenus piégés jamais mesurée.", "references": []})
    elif resistance["score"] is not None and resistance["score"] < 1:
        score = resistance["score"]
        points = 3 if score < 0.5 else 2 if score < 0.8 else 1
        raisons.append({"code": "resistance_faible", "points": points,
                        "texte": (f"Au dernier test, {resistance['suivis']} contenu"
                                  f"{'s' if resistance['suivis'] > 1 else ''} piégé"
                                  f"{'s' if resistance['suivis'] > 1 else ''} sur "
                                  f"{resistance['essais']} ont abouti (trafic synthétique)."),
                        "references": [resistance["campagne"]]})
    score = sum(r["points"] for r in raisons)
    niveau = "eleve" if score >= SEUIL_ELEVE else "moyen" if score >= SEUIL_MOYEN else "faible"
    mots = {"eleve": "élevé", "moyen": "moyen", "faible": "faible"}
    explication = f"Risque {mots[niveau]} ({score} points). " + " ".join(
        r["texte"] for r in raisons) if raisons else "Risque faible : rien à signaler."
    return {"niveau": niveau, "score": score, "seuils": {"moyen": SEUIL_MOYEN, "eleve": SEUIL_ELEVE},
            "raisons": raisons, "explication": explication}


def fiche(store, agent_id: str, *, maintenant: datetime | None = None) -> dict | None:
    """Fiche complète d'un agent (registre + observé), ou None s'il est inconnu."""
    from . import anomalies, resistance as mod_resistance

    declare = PAR_ID.get(agent_id)
    obs = _observe(store, agent_id)
    if declare is None and not obs["sessions"]:
        return None
    declare = declare or {
        "id": agent_id, "nom": agent_id, "libelle": f"l'agent {agent_id}",
        "role": "Agent vu par la passerelle, absent du registre déclaré.", "service": None,
        "outils": [], "accordes": [], "necessaires": [],
    }
    retires = [r.get("code") for r in store.retraits.get(agent_id, [])]
    accordes = [c for c in dict.fromkeys(declare["accordes"] + obs["annonces"]) if c not in retires]
    necessaires = list(declare["necessaires"])
    surplus = [c for c in accordes if c not in necessaires]
    outils = list(declare["outils"])
    resume_res = mod_resistance.resume_agent(agent_id)
    entree = {
        "id": agent_id,
        "nom": declare["nom"],
        "libelle": declare["libelle"],
        "role": declare["role"],
        "service": declare.get("service"),
        # Propriétaire métier de l'agent : qui répond de ses droits et de ses actes.
        "proprietaire": declare.get("proprietaire"),
        "declare": agent_id in PAR_ID,
        "outils": outils,
        "droits": {
            "accordes": _avec_libelles(accordes),
            "utilises": list(obs["utilises"]),
            "necessaires": _avec_libelles(necessaires),
            "surplus": surplus,
            "inutilises": [c for c in accordes if c not in obs["utilises"]],
            "retires": retires,
        },
        "derniere_activite": obs["derniere"].isoformat() if obs["derniere"] else None,
        "sessions": obs["sessions"],
        "appels": obs["appels"],
        "habitude": anomalies.habitude(store, agent_id),
        "resistance": resume_res,
    }
    instant = maintenant or datetime.now(timezone.utc)
    recents = [i for i in obs["incidents"] if instant - _date(i.cree_a) <= FENETRE_RECENTE]
    entree["incidents"] = {
        "total": len(obs["incidents"]),
        "ouverts": sum(1 for i in obs["incidents"] if i.statut in ("ouvert", "surveille")),
        "recents_24h": len(recents),
        "ids": [i.id for i in obs["incidents"]],
    }
    entree["risque"] = _risque(entree, obs, resume_res, instant)
    return entree


def lister(store) -> list[dict]:
    """Registre déclaré, puis tout agent vu par la passerelle sans y figurer."""
    vus = [s.agent for s in store.sessions.values() if s.source == "interne" and s.agent]
    ids = [a["id"] for a in AGENTS] + [a for a in dict.fromkeys(vus) if a not in PAR_ID]
    instant = datetime.now(timezone.utc)
    return [f for f in (fiche(store, i, maintenant=instant) for i in ids) if f is not None]
