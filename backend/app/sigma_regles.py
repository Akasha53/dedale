"""Règles Sigma réutilisables, une par type d'incident, sur les champs ECS de l'export.

Ce module remplace l'ancienne règle « calquée sur la session » (elle ne valait que pour cette
session) par un catalogue stable :

- une règle par type d'incident (`interne_canari`, `humain_phishing`…), plus quatre règles de
  geste (virement ou export à double validation, coffre de clés lu par un agent, virement tenté
  par un agent). Chacune porte un `id` UUID stable (uuid5 de sa clé), un `logsource` avec
  `product: dedale` et une `category` par famille, une détection sur des champs ECS réels
  (ceux que produit `ecs.py`), des faux positifs, un niveau et des étiquettes ATT&CK ;
- des variantes `proxy` et `webserver` quand le signal se lit aussi dans les journaux du client :
  domaine sosie de la marque, dépôt vers une IA publique, envoi vers un service de collecte,
  routes-leurres. Elles n'ont pas de `product` : elles tournent sur les journaux du proxy ou du
  serveur web, au format ECS ;
- pour un incident, `regles_incident` rend la règle de son type, les règles du catalogue qui
  attrapent au moins un de ses événements, la variante générique et la variante spécialisée sur
  ce qu'il a vu (le domaine sosie ouvert, par exemple), reliée à la première par
  `related: derived`.

`correspond(regle, document)` évalue une règle sur un document ECS. Il couvre ce que ce
catalogue utilise (égalité insensible à la casse, listes, `contains`, `startswith`,
`endswith`, `gte`, conditions `and`/`or`/`not`, parenthèses, `1 of`/`all of`). Les tests s'en
servent pour vérifier que chaque règle attrape l'export réel d'un incident de son type ;
`sigma check` et `sigma convert` (sigma-cli) valident la syntaxe et la conversion.

    cd backend && uv run python -m app.sigma_regles --ecrire ../sigma/types
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

AUTEUR = "sAIfe (Secure Horizons)"
DATE = "2026-10-10"
_ESPACE = uuid.NAMESPACE_URL

# ---------------------------------------------------------------- Techniques ATT&CK
# (nom, identifiant de tactique, tactique, étiquette Sigma de la tactique)
TECHNIQUES: dict[str, tuple[str, str, str, str]] = {
    "T1595": ("Active Scanning", "TA0043", "Reconnaissance", "reconnaissance"),
    "T1566": ("Phishing", "TA0001", "Initial Access", "initial-access"),
    "T1566.001": ("Spearphishing Attachment", "TA0001", "Initial Access", "initial-access"),
    "T1566.002": ("Spearphishing Link", "TA0001", "Initial Access", "initial-access"),
    "T1566.003": ("Spearphishing via Service", "TA0001", "Initial Access", "initial-access"),
    "T1566.004": ("Spearphishing Voice", "TA0001", "Initial Access", "initial-access"),
    "T1195": ("Supply Chain Compromise", "TA0001", "Initial Access", "initial-access"),
    "T1195.002": ("Compromise Software Supply Chain", "TA0001", "Initial Access", "initial-access"),
    "T1078": ("Valid Accounts", "TA0004", "Privilege Escalation", "privilege-escalation"),
    "T1555": ("Credentials from Password Stores", "TA0006", "Credential Access", "credential-access"),
    "T1552.001": ("Credentials In Files", "TA0006", "Credential Access", "credential-access"),
    # ATT&CK 19 : l'usurpation d'identité (ex-T1656) est T1684.001, tactique « Stealth ».
    "T1684.001": ("Impersonation", "TA0005", "Stealth", "stealth"),
    "T1565.001": ("Stored Data Manipulation", "TA0040", "Impact", "impact"),
    "T1048": ("Exfiltration Over Alternative Protocol", "TA0010", "Exfiltration", "exfiltration"),
    "T1567": ("Exfiltration Over Web Service", "TA0010", "Exfiltration", "exfiltration"),
    "T1657": ("Financial Theft", "TA0040", "Impact", "impact"),
    "T1200": ("Hardware Additions", "TA0001", "Initial Access", "initial-access"),
}


def _reference(tid: str) -> str:
    return "https://attack.mitre.org/techniques/" + tid.replace(".", "/") + "/"


def technique(tid: str) -> dict:
    nom, ta_id, ta, _ = TECHNIQUES[tid]
    return {"id": tid, "nom": nom, "tactique_id": ta_id, "tactique": ta, "reference": _reference(tid)}


# ---------------------------------------------------------------- Listes réutilisées
NATURES_CANARI = ["canari_document", "canari_mail", "consigne_cachee"]
SERVICES_IA = [
    "chatgpt.com", "chat.openai.com", "claude.ai", "gemini.google.com", "copilot.microsoft.com",
    "perplexity.ai", "chat.mistral.ai", "chat.deepseek.com", "poe.com", "huggingface.co",
]
SERVICES_COLLECTE = [
    "webhook.site", "pastebin.com", "requestbin.net", "pipedream.net", "transfer.sh",
    "ngrok-free.app", "ngrok.io", "discord.com", "hookbin.com", "beeceptor.com",
]
# Sosies d'Orbis Pay (marque fictive) : ajout de mots, tiret, chiffres, lettres doublées,
# homoglyphe en punycode. À remplacer par la marque du client.
SOSIES_MARQUE = ["orbispay-", "-orbispay", "orbis-pay", "0rbispay", "orb1spay", "orbisspay",
                 "orbispaay", "orbispai", "xn--rbispay"]
DOMAINE_LEGITIME = "orbispay.example"
ROUTES_LEURRES = ["/api/internal/export-clients", "/api/internal/debug", "/.git/config",
                  "/sauvegardes/orbis-prod.sql", "/.well-known/ai-plugin.json"]


@dataclass
class Fiche:
    cle: str
    titre: str
    famille: str
    description: str
    detection: dict
    niveau: str
    techniques: list[str]
    faux_positifs: list[str]
    champs: list[str]
    variantes: list[str] = field(default_factory=list)
    logsource: dict | None = None  # variante : logsource sans product
    statut: str = "test"
    etiquettes: list[str] = field(default_factory=list)


def _base(dataset: str | None, action: str | list[str]) -> dict:
    b = {"event.module": "dedale", "event.action": action}
    if dataset:
        b["event.dataset"] = dataset
    return b


def _piege(dataset: str, natures: list[str] | str) -> dict:
    return {"selection": {**_base(dataset, "leurre_touche"), "rule.name": natures}, "condition": "selection"}


def _geste(categorie: str) -> dict:
    return {"selection": {**_base("dedale.humain", "avertissement"), "labels.categorie": categorie,
                          "event.type": "allowed"},
            "condition": "selection"}


_CHAMPS_AGENT = ["user.name", "rule.id", "rule.name", "labels.outil", "dedale.incident.id"]
_CHAMPS_HUMAIN = ["user.name", "user.group.name", "url.domain", "destination.domain", "dedale.incident.id"]

CATALOGUE: dict[str, Fiche] = {}


def _ajouter(f: Fiche) -> None:
    CATALOGUE[f.cle] = f


# ---------------------------------------------------------------- Surface exposée
_ajouter(Fiche(
    "externe_agent_ia", "Agent IA attaquant pris par un leurre de la surface exposée", "surface_exposee",
    "Un visiteur a suivi un piège que seul un agent IA suit : consigne cachée, fausse route listée "
    "dans robots.txt, faux secret ou faux outil MCP. Un humain ne voit pas ces pièges.",
    {"selection": _base("dedale.externe", "leurre_touche"), "condition": "selection"},
    "high", ["T1595"], ["Robot d'indexation qui lit robots.txt et suit une route interdite"],
    ["source.ip", "user_agent.original", "url.path", "rule.id", "rule.name"],
    variantes=["externe_agent_ia/webserver"],
))
_ajouter(Fiche(
    "externe_agent_ia/webserver", "Requête vers une route-leurre, journaux du serveur web", "webserver",
    "Requête sur une route qui n'existe que comme piège (listée dans robots.txt ou dans un commentaire "
    "caché). Adapter la liste aux routes-leurres déployées sur le site.",
    {"selection": {"url.path": ROUTES_LEURRES}, "condition": "selection"},
    "high", ["T1595"], ["Audit de sécurité autorisé qui parcourt les routes cachées"],
    ["source.ip", "user_agent.original", "url.path", "http.response.status_code"],
    logsource={"category": "webserver"},
))

# ---------------------------------------------------------------- Agents internes : contenu piégé
_ajouter(Fiche(
    "interne_canari", "Agent IA interne qui suit une consigne cachée dans un mail ou un document",
    "injection",
    "L'agent a lu un mail ou un document qui portait une consigne cachée et l'a suivie : le piège "
    "posé dans ce contenu a été touché. Injection indirecte (MITRE ATLAS AML.T0051).",
    _piege("dedale.interne", NATURES_CANARI), "high", ["T1566.001"],
    ["Test de résistance lancé par l'équipe sécurité (campagne du banc)"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_outil_mcp", "Agent IA interne piégé par la description d'un outil MCP", "chaine_approvisionnement",
    "La description d'un outil MCP branché à l'agent portait une consigne cachée, et l'agent l'a suivie "
    "(empoisonnement d'outil).",
    _piege("dedale.interne", ["outil_mcp_piege", "faux_outil_mcp"]), "high", ["T1195.002"],
    ["Serveur MCP de test volontairement piégé"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_outil_modifie", "Outil MCP modifié en cours de session", "chaine_approvisionnement",
    "La description ou les paramètres d'un outil ont changé après que l'agent l'a chargé. La passerelle "
    "a retenu l'appel suivant.",
    _piege("dedale.interne", "outil_modifie"), "high", ["T1195.002"],
    ["Mise à jour légitime d'un serveur MCP pendant une session"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_outil_inconnu", "Appel d'un outil absent de l'inventaire de l'agent", "chaine_approvisionnement",
    "L'agent a voulu appeler un outil qui ne figure pas dans son inventaire déclaré. La passerelle l'a "
    "retenu avant exécution.",
    _piege("dedale.interne", "outil_inconnu"), "medium", ["T1195"],
    ["Outil ajouté au serveur MCP avant sa déclaration à l'inventaire"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_appel", "Agent IA interne piégé par la transcription d'un appel", "injection",
    "La transcription d'un appel téléphonique lue par l'agent portait une consigne, et l'agent l'a suivie.",
    _piege("dedale.interne", "canari_appel"), "high", ["T1566.004"],
    ["Test de résistance lancé par l'équipe sécurité"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_chatbot", "Chatbot interne détourné par un message", "injection",
    "Un message adressé au chatbot portait une consigne qui l'a détourné de sa tâche.",
    _piege("dedale.interne", "injection_chatbot"), "high", ["T1566.003"],
    ["Test de résistance lancé par l'équipe sécurité"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_memoire", "Agent IA interne détourné par sa mémoire", "injection",
    "Une entrée empoisonnée de la mémoire longue de l'agent a modifié son comportement.",
    _piege("dedale.interne", "memoire_empoisonnee"), "high", ["T1565.001"],
    ["Test de résistance lancé par l'équipe sécurité"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_inter_agent", "Délégation d'un faux collègue agent", "injection",
    "Un agent a reçu une demande présentée comme venant d'un autre agent, sans provenance authentifiée.",
    {"base": {"event.module": "dedale", "event.dataset": "dedale.interne"},
     "selection_piege": {"event.action": "leurre_touche", "rule.name": "agent_usurpation"},
     "selection_provenance": {"labels.provenance": "non_authentifiee"},
     "condition": "base and 1 of selection_*"},
    "high", ["T1684.001", "T1078"], ["Agent de test sans signature de délégation"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_desarme", "Consigne cachée retirée avant lecture par l'agent", "injection",
    "sAIfe a retiré une consigne cachée d'un contenu avant que l'agent le lise. L'agent n'a rien suivi : "
    "c'est une tentative.",
    {"selection": _base("dedale.interne", "desarmement"), "condition": "selection"},
    "low", ["T1566.001"], ["Contenu légitime qui ressemble à une consigne (modèle de mail, procédure)"],
    _CHAMPS_AGENT,
))

# ---------------------------------------------------------------- Agents internes : droits et sorties
_ajouter(Fiche(
    "interne_droits", "Agent IA interne hors de son périmètre de droits", "droits",
    "L'agent a tenté un appel d'outil qui exige un droit absent de son jeton de tâche. La passerelle l'a "
    "refusé.",
    {"selection": {**_base("dedale.interne", "appel_outil"), "labels.hors_perimetre": "oui"},
     "condition": "selection"},
    "high", ["T1078"], ["Tâche mal déclarée : le droit manquait dans le jeton"],
    _CHAMPS_AGENT + ["labels.droit_requis"],
))
_ajouter(Fiche(
    "interne_politique", "Règle du SOC déclenchée par un agent IA", "gouvernance",
    "Un appel d'outil a déclenché une règle écrite par le SOC (blocage, retenue ou droit retiré).",
    {"selection": {**_base("dedale.interne", "appel_outil"), "rule.ruleset": "dedale-regles-soc"},
     "condition": "selection"},
    "medium", ["T1078"], ["Règle trop large qui attrape un usage prévu"], _CHAMPS_AGENT + ["rule.description"],
))
_ajouter(Fiche(
    "interne_anomalie", "Agent IA qui s'écarte de son habitude", "gouvernance",
    "Pic d'appels, outil jamais utilisé ou volume lu inhabituel pour cet agent.",
    {"selection": {**_base("dedale.interne", "appel_outil"),
                   "labels.anomalie": ["pic_appels", "outil_inhabituel", "volume_lu"]},
     "condition": "selection"},
    "low", ["T1078"], ["Nouvelle tâche confiée à l'agent", "Fin de mois ou clôture comptable"],
    _CHAMPS_AGENT + ["labels.anomalie"], etiquettes=["detection.threat-hunting"],
))
_ajouter(Fiche(
    "agent_coffre_cles", "Coffre de clés lu ou demandé par un agent IA", "identifiants",
    "Un agent a appelé l'outil de lecture du coffre de clés d'API, ou demandé le droit qui l'ouvre.",
    {"base": {"event.module": "dedale", "event.action": "appel_outil"},
     "selection_outil": {"labels.outil": "lire_coffre"},
     "selection_droit": {"labels.droit_requis": "coffre:lire"},
     "condition": "base and 1 of selection_*"},
    "high", ["T1555"], ["Agent d'exploitation autorisé à faire tourner les clés"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "agent_virement", "Virement tenté par un agent IA, arrêté", "fraude",
    "Un agent a demandé un virement et la passerelle l'a retenu ou refusé.",
    {"selection": {"event.module": "dedale", "event.action": "appel_outil",
                   "labels.outil": ["executer_paiement", "emettre_virement"], "event.outcome": "failure"},
     "condition": "selection"},
    "critical", ["T1657"], ["Paiement fournisseur prévu, retenu par une règle trop stricte"], _CHAMPS_AGENT,
))
_ajouter(Fiche(
    "interne_envoi_externe", "Envoi de données hors de l'entreprise par un agent IA", "exfiltration",
    "L'agent a tenté d'envoyer des données vers l'extérieur. La passerelle a retenu l'envoi avant "
    "exécution.",
    {"base": {"event.module": "dedale", "event.dataset": "dedale.interne"},
     "selection_piege": {"event.action": "leurre_touche", "rule.name": "envoi_externe"},
     "selection_sortie": {"event.action": "sortie_agent", "labels.exfiltration": "oui"},
     "condition": "base and 1 of selection_*"},
    "critical", ["T1048"], ["Envoi prévu vers un partenaire, absent de la liste des destinataires"],
    _CHAMPS_AGENT + ["destination.domain"], variantes=["exfiltration/proxy"],
))
_ajouter(Fiche(
    "interne_canal_detourne", "Outil détourné en canal de sortie", "exfiltration",
    "Un outil prévu pour autre chose (recherche, note) a servi à faire sortir des données.",
    _piege("dedale.interne", "canal_detourne"), "high", ["T1567"],
    ["Outil de recherche qui envoie légitimement une requête longue"], _CHAMPS_AGENT,
    variantes=["exfiltration/proxy"],
))
_ajouter(Fiche(
    "exfiltration/proxy", "Envoi vers un service de collecte de données, journaux du proxy", "proxy",
    "Requête POST ou PUT vers un service souvent utilisé pour récupérer des données volées (webhook "
    "jetable, collage de texte, tunnel). C'est là qu'un agent détourné envoie ce qu'il a lu.",
    {"selection": {"url.domain|endswith": SERVICES_COLLECTE, "http.request.method": ["POST", "PUT"]},
     "condition": "selection"},
    "high", ["T1567"], ["Développeur qui teste un webhook sur webhook.site", "Intégration Discord validée"],
    ["source.ip", "user.name", "url.domain", "url.path", "http.request.body.bytes"],
    logsource={"category": "proxy"},
))

# ---------------------------------------------------------------- Salariés (garde du poste)
_ajouter(Fiche(
    "humain_phishing", "Salarié qui passe outre l'alerte sur un lien de phishing", "phishing",
    "Le poste a affiché une alerte sur un lien de phishing ou un site sosie, et le salarié a continué.",
    _geste("phishing"), "high", ["T1566.002"], ["Site partenaire légitime au nom proche de la marque"],
    _CHAMPS_HUMAIN, variantes=["humain_phishing/proxy"],
))
_ajouter(Fiche(
    "humain_phishing/proxy", "Domaine sosie de la marque ouvert depuis le réseau, journaux du proxy", "proxy",
    "Un poste a ouvert un domaine qui imite la marque (tiret, chiffre à la place d'une lettre, "
    "lettre doublée, homoglyphe en punycode). Remplacer la marque fictive Orbis Pay par la vôtre.",
    {"selection_sosie": {"url.domain|contains": SOSIES_MARQUE},
     "selection_sous_domaine": {"url.domain|startswith": "orbispay."},
     "filtre_legitime": [{"url.domain": DOMAINE_LEGITIME}, {"url.domain|endswith": "." + DOMAINE_LEGITIME}],
     "condition": "1 of selection_* and not filtre_legitime"},
    "high", ["T1566.002"], ["Domaine de campagne marketing enregistré par l'entreprise elle-même"],
    ["source.ip", "user.name", "url.domain", "url.original"], logsource={"category": "proxy"},
))
_ajouter(Fiche(
    "humain_secret", "Salarié qui expose un secret malgré l'alerte", "identifiants",
    "Le poste a repéré un mot de passe ou une clé d'API sur le point de partir (collé dans un chat, "
    "un mail, un document) et le salarié a continué.",
    _geste("secret"), "high", ["T1552.001"], ["Clé de test sans droit, déjà révoquée"], _CHAMPS_HUMAIN,
))
_ajouter(Fiche(
    "humain_mail_externe", "Données sensibles envoyées vers une adresse extérieure", "exfiltration",
    "Le salarié a envoyé des données sensibles à une adresse hors de l'entreprise après l'alerte.",
    _geste("mail_externe"), "high", ["T1048"], ["Envoi prévu à un cabinet comptable ou un avocat"],
    _CHAMPS_HUMAIN,
))
_ajouter(Fiche(
    "humain_upload_ia", "Fichier confidentiel déposé vers une IA non autorisée", "exfiltration",
    "Le salarié a déposé un fichier confidentiel dans un service d'IA générative que l'entreprise "
    "n'autorise pas, malgré l'alerte.",
    _geste("upload_ia"), "medium", ["T1567"], ["Service d'IA approuvé depuis, pas encore dans la liste"],
    _CHAMPS_HUMAIN, variantes=["humain_upload_ia/proxy"],
))
_ajouter(Fiche(
    "humain_upload_ia/proxy", "Gros envoi vers une IA générative publique, journaux du proxy", "proxy",
    "Requête POST de plus de 100 ko vers un service d'IA générative grand public : souvent un fichier "
    "déposé dans la conversation.",
    {"selection": {"url.domain|endswith": SERVICES_IA, "http.request.method": "POST",
                   "http.request.body.bytes|gte": 100000},
     "condition": "selection"},
    "medium", ["T1567"], ["Abonnement entreprise au service d'IA, avec contrat de traitement"],
    ["source.ip", "user.name", "url.domain", "http.request.body.bytes"], logsource={"category": "proxy"},
))
_ajouter(Fiche(
    "humain_intrusion_physique", "Accès physique à un actif-leurre", "physique",
    "Un équipement-leurre (port, serveur factice) a été branché ou ouvert sur place.",
    {"selection": {"event.module": "dedale", "event.dataset": ["dedale.physique", "dedale.humain"],
                   "labels.categorie": "intrusion_physique"},
     "condition": "selection"},
    "critical", ["T1200"], ["Intervention d'un technicien prévue sur le matériel-leurre"], _CHAMPS_HUMAIN,
))
_ajouter(Fiche(
    "humain_signalement", "Mail signalé par un salarié", "phishing",
    "Un salarié a signalé un mail suspect depuis son poste. Utile surtout quand l'analyseur l'avait "
    "jugé sûr.",
    {"selection": _base("dedale.humain", "signalement"), "condition": "selection"},
    "low", ["T1566"], ["Mail commercial légitime signalé par prudence"], _CHAMPS_HUMAIN,
))
_ajouter(Fiche(
    "geste_critique_virement", "Virement soumis à double validation", "fraude",
    "Un salarié a demandé un virement que sAIfe a suspendu pour une double validation : relecture, "
    "puis décision d'un responsable.",
    {"selection": {**_base("dedale.humain", "avertissement"), "labels.quatre_yeux": "demande",
                   "labels.geste": "virement"},
     "condition": "selection"},
    "critical", ["T1657"], ["Virement fournisseur habituel au-dessus du seuil de double validation"],
    _CHAMPS_HUMAIN,
))
_ajouter(Fiche(
    "geste_critique_export", "Export de données clients soumis à double validation", "exfiltration",
    "Un salarié a demandé un export de données clients que sAIfe a suspendu pour une double validation.",
    {"selection": {**_base("dedale.humain", "avertissement"), "labels.quatre_yeux": "demande",
                   "labels.geste": "export_clients"},
     "condition": "selection"},
    "high", ["T1048"], ["Export prévu pour un audit ou une migration"], _CHAMPS_HUMAIN,
))

# Types d'incident (backend) → fiche. Les quatre règles de geste et les variantes s'y ajoutent.
TYPES_INCIDENT = [c for c in CATALOGUE if "/" not in c and not c.startswith(("geste_", "agent_"))]


def techniques_incident(type_inc: str, geste: str | None = None) -> list[dict]:
    """Techniques ATT&CK d'un type d'incident, précisées par le geste (virement, export)."""
    ids: list[str] = []
    fiche = CATALOGUE.get(type_inc)
    if fiche:
        ids += fiche.techniques
    if geste == "virement":
        ids += CATALOGUE["geste_critique_virement"].techniques
    elif geste == "export_clients":
        ids += CATALOGUE["geste_critique_export"].techniques
    return [technique(t) for t in dict.fromkeys(ids)]


# ---------------------------------------------------------------- Règle Sigma
def identifiant(cle: str) -> str:
    return str(uuid.uuid5(_ESPACE, f"urn:dedale:sigma:{cle}"))


def _etiquettes(f: Fiche) -> list[str]:
    tags = []
    for tid in f.techniques:
        tags.append("attack." + TECHNIQUES[tid][3])
        tags.append("attack." + tid.lower())
    return list(dict.fromkeys(tags + f.etiquettes))


def regle(cle: str) -> dict:
    """Règle Sigma (dict ordonné) de la fiche `cle`."""
    f = CATALOGUE[cle]
    logsource = f.logsource or {"product": "dedale", "category": f.famille}
    return {
        "title": f"sAIfe : {f.titre}",
        "id": identifiant(cle),
        "status": f.statut,
        "description": f.description,
        "references": [_reference(t) for t in f.techniques],
        "author": AUTEUR,
        "date": DATE,
        "tags": _etiquettes(f),
        "logsource": logsource,
        "detection": f.detection,
        "fields": f.champs,
        "falsepositives": f.faux_positifs,
        "level": f.niveau,
    }


def catalogue() -> list[dict]:
    return [regle(c) for c in CATALOGUE]


def vers_yaml(regles: list[dict]) -> str:
    """Une ou plusieurs règles, séparées par `---` (sigma-cli lit un fichier à plusieurs règles)."""
    return "---\n".join(yaml.safe_dump(r, allow_unicode=True, sort_keys=False, width=110) for r in regles)


def nom_fichier(cle: str) -> str:
    return "dedale_" + cle.replace("/", "_") + ".yml"


# ---------------------------------------------------------------- Évaluation sur un document ECS
def _valeurs(doc: dict, chemin: str) -> list:
    """Valeurs d'un champ pointé (`event.type`), aplaties ; liste vide si le champ manque."""
    noeud = doc
    if chemin in doc:  # champ à plat (`@timestamp`, ou document ECS aplati)
        noeud = doc[chemin]
    else:
        for morceau in chemin.split("."):
            if isinstance(noeud, dict) and morceau in noeud:
                noeud = noeud[morceau]
            else:
                return []
    if isinstance(noeud, list):
        return noeud
    return [noeud]


def _compare(valeur, attendu, modificateur: str | None) -> bool:
    if attendu is None:
        return valeur is None
    if modificateur in ("gte", "gt", "lte", "lt"):
        try:
            v, a = float(valeur), float(attendu)
        except (TypeError, ValueError):
            return False
        return {"gte": v >= a, "gt": v > a, "lte": v <= a, "lt": v < a}[modificateur]
    if isinstance(attendu, bool) or isinstance(valeur, bool):
        return str(valeur).lower() == str(attendu).lower()
    v, a = str(valeur).lower(), str(attendu).lower()
    if modificateur == "contains":
        return a in v
    if modificateur == "startswith":
        return v.startswith(a)
    if modificateur == "endswith":
        return v.endswith(a)
    if "*" in a or "?" in a:
        return fnmatch.fnmatchcase(v, a)
    return v == a


def _champ_ok(doc: dict, cle: str, attendu) -> bool:
    nom, _, mod = cle.partition("|")
    mods = mod.split("|") if mod else []
    tous = "all" in mods
    mod_principal = next((m for m in mods if m != "all"), None)
    attendus = attendu if isinstance(attendu, list) else [attendu]
    valeurs = _valeurs(doc, nom)
    if not valeurs:
        return any(a is None for a in attendus)

    def un(a):
        return any(_compare(v, a, mod_principal) for v in valeurs)

    return all(un(a) for a in attendus) if tous else any(un(a) for a in attendus)


def _bloc_ok(doc: dict, bloc) -> bool:
    if isinstance(bloc, list):  # liste de maps : OU
        return any(_bloc_ok(doc, b) for b in bloc)
    return all(_champ_ok(doc, k, v) for k, v in bloc.items())


_JETON = re.compile(r"\s*(\(|\)|\b(?:and|or|not)\b|\b(?:1|all|any) of\s+[\w*]+|[\w*]+)\s*", re.IGNORECASE)


def _evaluer_condition(condition: str, blocs: dict[str, bool]) -> bool:
    jetons = [j.strip() for j in _JETON.findall(condition) if j.strip()]
    pos = 0

    def courant():
        return jetons[pos].lower() if pos < len(jetons) else None

    def avancer():
        nonlocal pos
        pos += 1

    def primaire() -> bool:
        j = courant()
        if j is None:
            raise ValueError(f"condition incomplète : {condition!r}")
        if j == "not":
            avancer()
            return not primaire()
        if j == "(":
            avancer()
            v = ou()
            if courant() != ")":
                raise ValueError(f"parenthèse non fermée : {condition!r}")
            avancer()
            return v
        avancer()
        brut = jetons[pos - 1]
        m = re.match(r"(?i)(1|all|any) of\s+([\w*]+)", brut)
        if m:
            motif = m.group(2)
            noms = [n for n in blocs if fnmatch.fnmatchcase(n, motif) or (motif == "them")]
            vals = [blocs[n] for n in noms]
            return all(vals) if m.group(1).lower() == "all" else any(vals)
        if brut not in blocs:
            raise ValueError(f"bloc inconnu dans la condition : {brut}")
        return blocs[brut]

    def et() -> bool:
        v = primaire()
        while courant() == "and":
            avancer()
            v = primaire() and v
        return v

    def ou() -> bool:
        v = et()
        while courant() == "or":
            avancer()
            v = et() or v
        return v

    resultat = ou()
    if pos != len(jetons):
        raise ValueError(f"condition mal formée : {condition!r}")
    return resultat


def correspond(regle_sigma: dict, doc: dict) -> bool:
    """Vrai si la règle attrape ce document ECS (sous-ensemble de Sigma, voir l'en-tête)."""
    det = regle_sigma["detection"]
    blocs = {k: _bloc_ok(doc, v) for k, v in det.items() if k != "condition"}
    return _evaluer_condition(det["condition"], blocs)


# ---------------------------------------------------------------- Règles d'un incident
def _ioc_variante(cle_variante: str, documents: list[dict]) -> dict | None:
    """Variante spécialisée sur l'indicateur vu dans l'incident (domaine, route), ou None."""
    f = CATALOGUE[cle_variante]
    if cle_variante == "externe_agent_ia/webserver":
        chemins = sorted({p for d in documents for p in _valeurs(d, "url.path")
                          if d.get("event", {}).get("action") == "leurre_touche" and isinstance(p, str)})
        if not chemins:
            return None
        detection = {"selection": {"url.path": chemins}, "condition": "selection"}
        quoi = "ces routes-leurres"
    else:
        domaines = sorted({h for d in documents for h in _valeurs(d, "url.domain") + _valeurs(d, "destination.domain")
                           if isinstance(h, str) and h and not h.endswith(DOMAINE_LEGITIME)})
        if not domaines:
            return None
        detection = {"selection": {"url.domain": domaines}, "condition": "selection"}
        quoi = "ce domaine" if len(domaines) == 1 else "ces domaines"
    empreinte = hashlib.sha256(repr(detection).encode()).hexdigest()[:12]
    base = regle(cle_variante)
    return {
        "title": f"{base['title']} ({quoi}, vu par sAIfe)"[:110],
        "id": identifiant(f"{cle_variante}/{empreinte}"),
        "related": [{"id": base["id"], "type": "derived"}],
        "status": "experimental",
        "description": f"{f.description} Indicateur relevé par sAIfe sur un incident réel.",
        "references": base["references"],
        "author": AUTEUR,
        "date": DATE,
        "tags": base["tags"],
        "logsource": base["logsource"],
        "detection": detection,
        "fields": base["fields"],
        "falsepositives": base["falsepositives"],
        "level": base["level"],
    }


def regles_incident(type_inc: str, documents: list[dict]) -> list[dict]:
    """Règle du type, règles du catalogue qui attrapent un événement de l'incident, variantes."""
    cles: list[str] = []
    if type_inc in CATALOGUE:
        cles.append(type_inc)
    for cle, f in CATALOGUE.items():
        if f.logsource is not None or cle in cles:
            continue
        r = regle(cle)
        if any(correspond(r, d) for d in documents):
            cles.append(cle)
    if not cles:
        cles.append("externe_agent_ia" if type_inc.startswith("externe") else "interne_canari")
    regles = [regle(c) for c in cles]
    variantes = list(dict.fromkeys(v for c in cles for v in CATALOGUE[c].variantes))
    for v in variantes:
        # La variante générique tourne telle quelle chez le client ; la spécialisée porte
        # l'indicateur vu par Dédale (domaine, route), reliée à la première par `derived`.
        regles.append(regle(v))
        precise = _ioc_variante(v, documents)
        if precise:
            regles.append(precise)
    return regles


# ---------------------------------------------------------------- Ligne de commande
def ecrire(dossier: Path) -> list[Path]:
    dossier.mkdir(parents=True, exist_ok=True)
    chemins = []
    for cle in CATALOGUE:
        chemin = dossier / nom_fichier(cle)
        temporaire = chemin.with_suffix(".yml.tmp")
        temporaire.write_text(vers_yaml([regle(cle)]), encoding="utf-8")
        temporaire.replace(chemin)
        chemins.append(chemin)
    return chemins


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Catalogue des règles Sigma de sAIfe.")
    p.add_argument("--ecrire", metavar="DOSSIER", help="écrit une règle par fichier dans ce dossier")
    args = p.parse_args(argv)
    if args.ecrire:
        for c in ecrire(Path(args.ecrire)):
            print(c)
        return 0
    sys.stdout.write(vers_yaml(catalogue()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
