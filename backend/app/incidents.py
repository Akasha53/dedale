"""Boîte noire : reconstruction de la chaîne d'un incident.

À partir des événements d'une session (ou d'un canari touché), on recompose l'enchaînement
  document/mail piégé -> consigne lue -> action -> tentative de sortie de données.
Chaque étape porte un résumé NEUTRALISÉ : le texte piégé n'est jamais réinjecté tel quel.
La neutralisation a lieu une seule fois, à l'ingestion (`store.ingerer`). Ici on se contente
de raccourcir le texte déjà neutralisé ; le neutraliser une seconde fois doublait le préfixe
et échappait deux fois le HTML (« &amp;amp; » dans la console).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from . import gouvernance

# Ordre canonique des étapes de la boîte noire.
ORDRE_ETAPES = ["appat", "desarme", "consigne_lue", "action", "regle", "anomalie", "tentative_sortie",
                "riposte", "correctif"]

_LIBELLES = {
    "appat": "Document/mail piégé rencontré",
    "desarme": "Désarmé avant lecture",
    "consigne_lue": "Consigne cachée lue",
    "action": "Action sur une route ou un outil découvert",
    "tentative_sortie": "Tentative de sortie de données",
    "riposte": "Riposte appliquée",
    "correctif": "Correctif : droit retiré",
    "regle": "Règle du SOC déclenchée",
    "anomalie": "Comportement inhabituel",
}

# Correspondance étape interne -> phase lue par la console.
_PHASE = {
    "appat": "entree",
    "desarme": "desarme",
    "consigne_lue": "consigne",
    "action": "outil",
    "tentative_sortie": "sortie",
    "riposte": "riposte",
    "correctif": "correctif",
    "regle": "regle",
    "anomalie": "anomalie",
}


def instant(horodatage) -> datetime:
    """Horodatage comparable, quel que soit son fuseau (la passerelle date en heure locale,
    le backend en UTC). Un horodatage illisible passe en tête plutôt que de casser le tri."""
    if isinstance(horodatage, str) and horodatage:
        try:
            dt = datetime.fromisoformat(horodatage.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def cle_chronologique(etape: dict, ordre_etapes: list[str]) -> tuple:
    """Tri de la boîte noire : l'heure d'abord, puis l'étape logique pour départager un même
    instant (un avertissement porte action, avertissement et choix à la même heure)."""
    nom = etape.get("etape")
    return (instant(etape.get("horodatage")),
            ordre_etapes.index(nom) if nom in ordre_etapes else 99,
            etape.get("evenement_id") or 0)


def _cadre_technique(ident: str) -> str:
    return "ATLAS" if ident.upper().startswith(("AML", "ATLAS")) else "ATT&CK"


def _techniques(leurre) -> list[dict]:
    if leurre is None:
        return []
    return [{"id": t, "nom": t, "cadre": _cadre_technique(t)} for t in getattr(leurre, "techniques", [])]


def _risques(leurre) -> list[dict]:
    if leurre is None:
        return []
    return [{"id": r, "nom": r} for r in getattr(leurre, "risques", [])]


# Techniques MITRE ATT&CK (Enterprise) que le backend ajoute aux maillons d'un agent interne,
# selon ce que montre le maillon. Les leurres apportent déjà leurs repères OWASP agentique et
# ATLAS ; ATT&CK décrit le geste côté système d'information. `a_confirmer` vaut True quand la
# correspondance est plausible sans être établie : à vérifier sur attack.mitre.org avant la
# fiche défense. Aucun identifiant ici n'est inventé, seuls les rapprochements sont discutables.
_ATTACK = {
    # Lire le coffre de clés : identifiants tirés d'un magasin de secrets.
    "T1555": ("Credentials from Password Stores", False),
    # Agir hors de son jeton avec l'identité légitime de l'agent.
    "T1078": ("Valid Accounts", True),
    # Virement demandé hors de la tâche.
    "T1657": ("Financial Theft", True),
    # Données poussées vers une adresse ou un domaine externe (mail, lien, image).
    "T1048": ("Exfiltration Over Alternative Protocol", True),
    # Outil MCP tiers piégé, installé comme une dépendance.
    "T1195": ("Supply Chain Compromise", True),
}

# Droit demandé hors jeton -> technique propre à ce droit (en plus de T1078).
_ATTACK_PAR_SCOPE = {
    "coffre:lire": "T1555",
    "paiement:executer": "T1657",
}

_ASI03 = {"id": "OWASP ASI03", "nom": "Identity and Privilege Abuse"}

# Types de trouvaille de l'inspection sortante (interne/orbis/detection.py) : le contenu
# était en train de quitter l'agent par un envoi ou une réponse.
_TYPES_SORTANTS = ("exfiltration_markdown", "faux_secret")


def _technique_attack(ident: str) -> dict:
    nom, a_confirmer = _ATTACK[ident]
    return {"id": ident, "nom": nom, "cadre": "ATT&CK", "a_confirmer": a_confirmer}


def _attack_pour(ev: dict, etape: str, leurre) -> list[str]:
    """Techniques ATT&CK d'un maillon d'agent interne. Rien pour les autres sources."""
    if ev.get("source") != "interne":
        return []
    details = ev.get("details") or {}
    nature = getattr(leurre, "nature", None) or ev.get("leurre_nature")
    ids: list[str] = []
    violation = details.get("violation_droits")
    if isinstance(violation, dict):
        ids.append("T1078")
        propre = _ATTACK_PAR_SCOPE.get(str(violation.get("scope_requis")))
        if propre:
            ids.append(propre)
    if nature == "canari_coffre":
        ids.append("T1555")
    if details.get("outil_mcp_suspect") or nature == "outil_mcp_piege":
        ids.append("T1195")
    # Contenu sortant : étape de sortie, exfiltration retenue, ou canari relevé par
    # l'inspection sortante de la passerelle (lien/image externe, faux secret dans l'envoi).
    if (
        etape == "tentative_sortie"
        or details.get("exfiltration")
        or details.get("type") in _TYPES_SORTANTS
    ):
        ids.append("T1048")
    return ids


def _ajouter_techniques(techniques: list[dict], ids: list[str]) -> list[dict]:
    """Ajoute les techniques ATT&CK sans doublon. Une technique déjà posée par le leurre
    garde sa place et reçoit le nom officiel s'il lui manquait."""
    sortie = [dict(t) for t in techniques]
    for ident in ids:
        ajout = _technique_attack(ident)
        existante = next((t for t in sortie if t.get("id") == ident), None)
        if existante is None:
            sortie.append(ajout)
            continue
        if existante.get("nom") in (None, "", ident):
            existante["nom"] = ajout["nom"]
        existante.setdefault("a_confirmer", ajout["a_confirmer"])
    return sortie


def gravite(chaine: list[dict], source: str) -> str:
    phases = {e.get("etape") for e in chaine}
    if "tentative_sortie" in phases:
        return "critique"
    # Consigne retirée avant lecture, rien d'autre : l'attaque a été empêchée.
    if "desarme" in phases and not phases & {"consigne_lue", "regle", "anomalie"} and not any(
            str(e.get("detail", "")).startswith("action hors périmètre") for e in chaine):
        return "moyenne"
    if "consigne_lue" in phases or source == "interne":
        return "haute"
    if "action" in phases:
        return "moyenne"
    return "faible"


def resume(chaine: list[dict], classement: str, source: str) -> str:
    exfil = any(e.get("etape") == "tentative_sortie" for e in chaine)
    return (
        f"Session classée {classement} sur la surface {source}. "
        f"Chaîne de {len(chaine)} étape(s). "
        f"Tentative d'exfiltration : {'oui' if exfil else 'non constatée'}."
    )

# Champs de details susceptibles de contenir du texte piégé (à neutraliser avant exposition).
# Les quatre derniers viennent du pilier humain : lien de phishing, secret collé, texte de la
# pop-up du garde du corps, cible du geste — tous inertes, jamais réexécutés.
_CHAMPS_PIEGES = (
    "consigne", "consigne_lue", "contenu", "extrait", "objectif", "charge_utile", "payload",
    "consigne_outil", "message", "lien", "secret", "url_phishing", "cible",
)


def _etape_pour(ev: dict, leurres: dict[str, Any]) -> str | None:
    """Classe un événement dans une étape de la chaîne, ou None s'il n'en est pas."""
    nature = None
    if ev.get("leurre_id") and ev["leurre_id"] in leurres:
        nature = leurres[ev["leurre_id"]].nature
    typ = ev.get("type")
    surface = ev.get("surface")
    details = ev.get("details") or {}

    if typ == "riposte":
        return "riposte"
    # Correctif appliqué par l'analyste depuis la console (droit retiré à l'agent).
    if typ == "correctif":
        return "correctif"
    # Désarmeur de la passerelle : la consigne a été retirée avant que l'agent la lise.
    if typ == "desarmement":
        return "desarme"
    # Gouvernance : règle écrite par le SOC, écart à l'habitude de l'agent (gouvernance.py).
    if isinstance(details.get("politique"), dict):
        return "regle"
    if isinstance(details.get("anomalie"), dict):
        return "anomalie"
    if typ == "sortie_agent" or details.get("exfiltration"):
        return "tentative_sortie"
    # Règle de la passerelle : un outil sortant vise une adresse hors d'Orbis Pay.
    if nature == "envoi_externe":
        return "tentative_sortie"
    # Outil MCP piégé : la consigne vit dans la DESCRIPTION de l'outil. Qu'elle soit portée par
    # le canari touché (nature outil_mcp_piege) ou par l'appel qui découvre l'outil, c'est l'étape
    # « consigne lue ».
    if nature == "outil_mcp_piege" or details.get("outil_mcp_suspect"):
        return "consigne_lue"
    # Appel piégé (V1), injection chatbot (V3a), mémoire empoisonnée (V4) : le canari touché
    # marque le moment où l'agent SUIT la consigne cachée de sa source.
    if nature in ("canari_appel", "injection_chatbot", "memoire_empoisonnee"):
        return "consigne_lue"
    # Usurpation inter-agent (V3b) : la délégation forgée est l'instruction non authentifiée.
    if nature == "agent_usurpation" or details.get("provenance_invalide"):
        return "consigne_lue"
    # Tentative d'action hors du périmètre de droits : une action refusée (moindre privilège).
    if details.get("violation_droits"):
        return "action"
    # La consigne lue prime : un leurre peut être l'appât ET porter l'instruction cachée.
    if nature == "consigne_cachee" or details.get("consigne") or details.get("consigne_lue"):
        return "consigne_lue"
    if typ == "leurre_touche" and nature in ("canari_document", "canari_mail", "faux_secret"):
        return "appat"
    if surface in ("doc", "document", "mail", "appel", "chatbot", "memoire") or typ == "entree_agent":
        return "appat"
    if typ in ("appel_outil",) or (typ == "requete" and (details.get("decouvert_dans_doc") or nature == "fausse_route")):
        return "action"
    return None


def _session_prevenue(evenements: list[dict]) -> bool:
    """Une consigne a été désarmée avant lecture et aucun canari n'a été touché ensuite."""
    desarmee = any(e.get("type") == "desarmement"
                   and ((e.get("details") or {}).get("desarmement") or {}).get("consigne") is True
                   for e in evenements)
    return desarmee and not any(e.get("type") == "leurre_touche" for e in evenements)


def _reponse_ordinaire(ev: dict) -> bool:
    details = ev.get("details") or {}
    return (ev.get("type") == "sortie_agent" and ev.get("source") == "interne"
            and not details.get("exfiltration") and not ev.get("leurre_id"))


def construire_chaine(evenements: list[dict], leurres: dict[str, Any]) -> list[dict]:
    """Chaîne de la boîte noire. Chaque étape porte les champs internes (etape, resume) ET les
    champs lus par la console (ordre, phase, titre, detail, techniques, risques)."""
    etapes: list[dict] = []
    prevenue = _session_prevenue(evenements)
    for ev in sorted(evenements, key=lambda e: (e.get("horodatage") or "", e.get("id", 0))):
        etape = _etape_pour(ev, leurres)
        if etape == "tentative_sortie" and prevenue and _reponse_ordinaire(ev):
            # Consigne désarmée avant lecture, aucun canari touché : la réponse finale de l'agent
            # n'est pas une tentative de sortie de données.
            continue
        if etape is None:
            continue
        details = ev.get("details") or {}
        leurre = leurres.get(ev.get("leurre_id")) if ev.get("leurre_id") else None
        violation = details.get("violation_droits") if isinstance(details.get("violation_droits"), dict) else None
        texte_source = next((details[c] for c in _CHAMPS_PIEGES if details.get(c)), None)
        if etape == "correctif":
            detail = detail_correctif(details)
        elif violation is not None:
            # Action hors périmètre : on décrit le droit manquant, jamais de texte piégé.
            detail = (
                f"action hors périmètre : {violation.get('outil')} exige le droit "
                f"{violation.get('scope_requis')}, absent du jeton de tâche"
            )
        elif details.get("outil_mcp_suspect"):
            detail = (
                f"outil MCP {ev.get('outil')} (serveur {details.get('serveur_mcp')}) : "
                "description porteuse d'une consigne cachée (tool poisoning)"
            )
        elif texte_source is None:
            morceaux = [ev.get("type")]
            if ev.get("methode") or ev.get("chemin"):
                morceaux.append(f"{ev.get('methode') or ''} {ev.get('chemin') or ''}".strip())
            if ev.get("outil"):
                morceaux.append(f"outil={ev.get('outil')}")
            if ev.get("leurre_id"):
                morceaux.append(f"leurre={ev.get('leurre_id')}")
            detail = " · ".join(m for m in morceaux if m)
        else:
            # Déjà neutralisé à l'ingestion : on raccourcit, on ne neutralise pas une seconde fois.
            detail = _abrege(texte_source, 240)
        leurre_id = ev.get("leurre_id")
        canari_id = leurre_id if (leurre_id and str(leurre_id).startswith("C-")) else None
        techniques = _ajouter_techniques(_techniques(leurre), _attack_pour(ev, etape, leurre))
        risques = _risques(leurre)
        if violation is not None and not any(str(r.get("id", "")).endswith("ASI03") for r in risques):
            risques.append(dict(_ASI03))
        etapes.append(
            {
                "etape": etape,
                "phase": _PHASE.get(etape, etape),
                "libelle": _LIBELLES[etape],
                "titre": _LIBELLES[etape],
                "horodatage": ev.get("horodatage"),
                "evenement_id": ev.get("id"),
                "resume": detail,
                "detail": detail,
                "leurre_id": leurre_id,
                "canari_id": canari_id,
                "techniques": techniques,
                "risques": risques,
            }
        )
        if etape in gouvernance.ETAPES:
            etapes[-1].update(gouvernance.maillon(etape, ev))
        # Maillon « source » : le document lu, complet et déjà désarmé à l'ingestion.
        if isinstance(details.get("document_source"), dict):
            etapes[-1]["document_source"] = details["document_source"]
        # Maillon « désarmé avant lecture » : ce qui a été retiré, déjà neutralisé à l'ingestion.
        if isinstance(details.get("desarmement"), dict):
            etapes[-1]["desarmement"] = details["desarmement"]
    # Ordre chronologique : la frise se lit dans l'ordre où les choses se sont passées.
    etapes.sort(key=lambda s: cle_chronologique(s, ORDRE_ETAPES))
    for i, e in enumerate(etapes):
        e["ordre"] = i
    return etapes


def detail_correctif(details: dict) -> str:
    """Texte du maillon « correctif » : quel droit, à quel agent, par qui, quels outils."""
    droit = details.get("droit")
    texte = f"droit {droit} ({details.get('libelle') or droit}) retiré à l’agent {details.get('agent')}"
    if details.get("analyste"):
        texte += f" par {details['analyste']}"
    outils = details.get("outils") or []
    if outils:
        texte += f". La passerelle refusera {', '.join(outils)}"
    return texte + "."


def chaine_complete(etapes: list[dict]) -> bool:
    """Vrai si la chaîne couvre l'appât jusqu'à la tentative de sortie."""
    vues = {e["etape"] for e in etapes}
    return "appat" in vues and "tentative_sortie" in vues


# ===================================================================================
# Pilier humain — « le maillon faible »
#
# Le garde du corps du poste observe un geste risqué du salarié AVANT qu'il n'aboutisse,
# prévient, laisse choisir (continuer/annuler) et escalade au SOC si le salarié passe outre.
# La boîte noire du geste humain suit cinq étapes propres :
#   contexte → action_risquee → avertissement → choix → consequence/escalade.
# Comme pour les canaris, tout texte d'origine piégée (lien de phishing, secret, pop-up) est
# déjà neutralisé en amont (store) : on l'affiche tel quel, jamais réinjecté.
# ===================================================================================

_ORDRE_HUMAIN = ["contexte", "action_risquee", "avertissement", "choix", "signalement", "consequence"]

_LIBELLES_HUMAIN = {
    "contexte": "Contexte du poste",
    "action_risquee": "Action risquée détectée",
    "avertissement": "Avertissement affiché au salarié",
    "choix": "Choix du salarié",
    "signalement": "Mail signalé par le salarié",
    "consequence": "Conséquence / escalade",
}

# Catégorie de geste (posée par le poste dans details.categorie) → type d'incident console.
_TYPE_HUMAIN = {
    "secret": "humain_secret",
    "mail_externe": "humain_mail_externe",
    "upload_ia": "humain_upload_ia",
    "phishing": "humain_phishing",
    "intrusion_physique": "humain_intrusion_physique",
    # Bénéficiaire leurre (canari virement) : abus de privilège interne, aucune tâche ne le paie.
    "beneficiaire_leurre": "humain_beneficiaire_leurre",
    # Le salarié signale lui-même un mail (app Mac, « Signaler un mail suspect… »).
    "signalement": "humain_signalement",
}

_TITRE_HUMAIN = {
    "humain_secret": "Secret exposé par un salarié",
    "humain_mail_externe": "Données sensibles envoyées en externe",
    "humain_upload_ia": "Fichier confidentiel déposé vers une IA non autorisée",
    "humain_phishing": "Salarié piégé par un lien de phishing",
    "humain_intrusion_physique": "Intrusion physique sur un actif-leurre",
    "humain_beneficiaire_leurre": "Bénéficiaire leurre touché",
    "humain_signalement": "Mail signalé par un salarié",
}

_GESTE_LIBELLE = {
    "secret": "le salarié s'apprête à exposer un secret (mot de passe / clé API)",
    "mail_externe": "le salarié s'apprête à envoyer des données sensibles à un destinataire externe",
    "upload_ia": "le salarié s'apprête à déposer un fichier confidentiel vers une IA non autorisée",
    "phishing": "le salarié s'apprête à cliquer un lien de phishing / ouvrir une pièce jointe piégée",
    "intrusion_physique": "accès à un actif-leurre physique (serveur / port)",
}

_NIVEAUX = ("faible", "moyenne", "haute", "critique")

# Geste critique (quatre yeux) : le récit suit le geste, pas la catégorie de l'alerte. Un virement
# réclamé par mail est rangé en « phishing », mais personne n'a cliqué sur un lien.
_GESTES_CRITIQUES = {"virement": "un virement", "export_clients": "un export de données clients"}
_RELECTURE_HUMAIN = {
    "refuse": "relu par sAIfe : refusé, le geste n'a pas eu lieu",
    "accorde": "relu par sAIfe : accordé, le geste a pu avoir lieu",
    "retenu": "relu par sAIfe : retenu, le geste attend la décision d'un analyste",
}


def geste_critique(details: dict, categorie: str | None) -> str | None:
    """Libellé d'un virement ou d'un export de données clients, ou None pour un autre geste."""
    g = _GESTES_CRITIQUES.get(details.get("geste"))
    if g is None:
        return None
    if details.get("verdict") in ("suspect", "frauduleux") and not details.get("choix"):
        return f"un mail jugé {details['verdict']} réclame {g}"
    texte = (f"le salarié veut faire {g} réclamé par un mail jugé frauduleux" if categorie == "phishing"
             else f"le salarié demande {g}")
    if details.get("quatre_yeux") == "demande":
        texte += ", geste critique soumis à double validation"
    return texte

# Gravité par défaut d'un type de geste humain (surchargée par details.gravite d'un geste passé outre).
_GRAVITE_HUMAIN = {
    "humain_secret": "haute",
    "humain_mail_externe": "haute",
    "humain_upload_ia": "moyenne",
    "humain_phishing": "haute",
    "humain_intrusion_physique": "critique",
    "humain_beneficiaire_leurre": "haute",
    "humain_signalement": "moyenne",
}

# Techniques MITRE ATT&CK (couche humaine) rattachées au geste. Plausibles, À CONFIRMER sur
# attack.mitre.org avant la fiche défense (voir note en bas de CONTRATS.md).
_TECH_HUMAIN = {
    "humain_phishing": [{"id": "T1566", "nom": "Phishing", "cadre": "ATT&CK"}],
    "humain_secret": [{"id": "T1552", "nom": "Unsecured Credentials", "cadre": "ATT&CK"}],
    "humain_mail_externe": [{"id": "T1048", "nom": "Exfiltration Over Alternative Protocol", "cadre": "ATT&CK"}],
    "humain_upload_ia": [{"id": "T1567", "nom": "Exfiltration Over Web Service", "cadre": "ATT&CK"}],
    "humain_intrusion_physique": [{"id": "T1200", "nom": "Hardware Additions", "cadre": "ATT&CK"}],
}

# Risques OWASP. Le fit « humain » est partiel : seuls secret/upload_ia touchent clairement la
# divulgation d'information sensible (OWASP LLM02). À confirmer, le reste reste côté ATT&CK.
_RISQUE_HUMAIN = {
    "humain_secret": [{"id": "OWASP LLM02", "nom": "Sensitive Information Disclosure"}],
    "humain_upload_ia": [{"id": "OWASP LLM02", "nom": "Sensitive Information Disclosure"}],
}


# Verdict de l'analyseur de mails (`messagerie/`) au moment du signalement.
_VERDICT_ANALYSEUR = {"sur": "sûr", "suspect": "suspect", "frauduleux": "frauduleux"}


def type_humain(categorie: str | None, intrusion: bool = False) -> str:
    if intrusion:
        return "humain_intrusion_physique"
    return _TYPE_HUMAIN.get(categorie, "humain_secret")


def titre_humain(type_incident: str, session_id: str, contexte: str | None = None) -> str:
    if contexte == "telechargement":
        return f"Fichier à risque gardé par le salarié ({session_id})"
    return f"{_TITRE_HUMAIN.get(type_incident, 'Geste humain à risque')} ({session_id})"


# Téléchargement (app Mac) : type du fichier, avec son article, pour les phrases.
TYPES_FICHIER = {
    "application": "un programme", "script": "un script", "image_disque": "une image disque",
    "installeur": "un installeur", "raccourci": "un raccourci", "document_macros": "un document à macros",
    "archive_chiffree": "une archive chiffrée", "document": "un document",
}


def domaine_propre(valeur) -> str | None:
    """Hôte seul, lettres, chiffres, points et tirets : rien d'autre ne passe."""
    if not isinstance(valeur, str):
        return None
    import re as _re
    m = _re.fullmatch(r"[A-Za-z0-9.-]{1,253}", valeur.strip())
    return m.group(0).lower() if m else None


def detail_telechargement(details: dict) -> str:
    """Le fichier gardé, sans son nom : type, domaine d'origine, empreinte abrégée."""
    quoi = TYPES_FICHIER.get(details.get("type_fichier"), "un fichier")
    texte = f"fichier à risque téléchargé : {quoi}"
    dom = domaine_propre(details.get("domaine"))
    if dom:
        texte += f" venu de {dom}"
    sha = details.get("sha256")
    if isinstance(sha, str) and len(sha) >= 12 and all(c in "0123456789abcdef" for c in sha.lower()):
        texte += f" · empreinte SHA-256 {sha.lower()[:12]}…"
    return texte


def gravite_humaine(type_incident: str, gravite_annoncee: str | None = None) -> str:
    if gravite_annoncee in _NIVEAUX:
        return gravite_annoncee
    return _GRAVITE_HUMAIN.get(type_incident, "moyenne")


def resume_humain(chaine: list[dict], type_incident: str, passe_outre: bool, retenu: bool = False) -> str:
    quoi = _TITRE_HUMAIN.get(type_incident, "geste humain à risque").lower()
    if type_incident == "humain_signalement":
        return f"Pilier humain : {quoi}. Chaîne de {len(chaine)} étape(s)."
    if retenu and not passe_outre:
        return (f"Pilier humain : {quoi}. Geste critique suspendu par sAIfe sur un signal de fraude, "
                f"avant toute alerte au salarié. Chaîne de {len(chaine)} étape(s).")
    etat = "passé outre (signal fort)" if passe_outre else "respecté par le salarié"
    return (
        f"Pilier humain : {quoi}. Avertissement {etat}. "
        f"Chaîne de {len(chaine)} étape(s)."
    )


# Entité HTML coupée en fin de texte (« &am », « &#x2 ») : on la retire plutôt que de
# laisser un fragment illisible après troncature.
_ENTITE_COUPEE = re.compile(r"&#?[0-9A-Za-z]{0,8}$")


def _abrege(valeur: object, n: int = 240) -> str:
    """Tronque un texte DÉJÀ neutralisé en amont (store) pour l'affichage en frise.

    On ne re-neutralise pas : les champs piégés sont inertes dès leur stockage. Utilisé par
    les deux chaînes, agent IA et geste humain.
    """
    texte = valeur if isinstance(valeur, str) else str(valeur)
    texte = texte.strip()
    if len(texte) <= n:
        return texte or "[vide]"
    coupe = _ENTITE_COUPEE.sub("", texte[:n])
    return coupe.rstrip() + " […]"


def _mk_humain(etape: str, detail: str, ev: dict, techniques=None, risques=None) -> dict:
    leurre_id = ev.get("leurre_id")
    canari_id = leurre_id if (leurre_id and str(leurre_id).startswith("C-")) else None
    return {
        "etape": etape,
        "phase": etape,  # phases propres au pilier humain (voir CONTRATS.md pour la console).
        "libelle": _LIBELLES_HUMAIN.get(etape, etape),
        "titre": _LIBELLES_HUMAIN.get(etape, etape),
        "horodatage": ev.get("horodatage"),
        "evenement_id": ev.get("id"),
        "resume": detail,
        "detail": detail,
        "leurre_id": leurre_id,
        "canari_id": canari_id,
        "techniques": techniques or [],
        "risques": risques or [],
    }


def construire_chaine_humaine(evenements: list[dict], leurres: dict[str, Any]) -> list[dict]:
    """Boîte noire d'un geste humain : contexte → action risquée → avertissement → choix → conséquence."""
    etapes: list[dict] = []
    a_continuer = False
    a_consequence = False
    ev_continuer: dict | None = None

    for ev in sorted(evenements, key=lambda e: (e.get("horodatage") or "", e.get("id", 0))):
        details = ev.get("details") or {}
        typ = ev.get("type")
        cat = details.get("categorie")
        leurre = leurres.get(ev.get("leurre_id")) if ev.get("leurre_id") else None
        intrusion = (
            cat == "intrusion_physique"
            or (leurre is not None and leurre.nature == "canari_physique")
            or (ev.get("surface") == "physique" and typ == "leurre_touche")
        )
        type_inc = type_humain(cat, intrusion)

        if typ == "avertissement" and details.get("origine") == "relecteur" and details.get("quatre_yeux") == "demande":
            # Geste vérifié par l'app et retenu sur un signal de fraude : le salarié n'a vu aucune
            # alerte avant, et n'a rien choisi. Seul le geste entre au récit, puis sa conséquence.
            g = _GESTES_CRITIQUES.get(details.get("geste"), "un geste critique")
            etapes.append(_mk_humain(
                "action_risquee", f"le salarié demande {g}, vérifié par sAIfe avant exécution", ev,
                list(_TECH_HUMAIN.get(type_inc, [])), list(_RISQUE_HUMAIN.get(type_inc, []))))
        elif typ == "avertissement":
            geste = geste_critique(details, cat) or _GESTE_LIBELLE.get(cat, "geste à risque détecté sur le poste")
            cible = details.get("cible")
            d_action = geste + (f" — cible : {_abrege(cible, 160)}" if cible else "")
            if details.get("contexte") == "telechargement":
                d_action = detail_telechargement(details)
            etapes.append(
                _mk_humain(
                    "action_risquee", d_action, ev,
                    list(_TECH_HUMAIN.get(type_inc, [])),
                    list(_RISQUE_HUMAIN.get(type_inc, [])),
                )
            )
            msg = next((details.get(c) for c in _CHAMPS_PIEGES if details.get(c)
                        and c in ("message", "lien", "secret", "url_phishing", "contenu", "extrait", "charge_utile")), None)
            d_av = _abrege(msg) if msg else "avertissement affiché au salarié (garde du corps du poste)"
            grav = details.get("gravite")
            if grav in _NIVEAUX:
                d_av += f" · gravité annoncée : {grav}"
            etapes.append(_mk_humain("avertissement", d_av, ev))
            choix = details.get("choix")
            if choix == "continuer":
                a_continuer = True
                ev_continuer = ev
                d_choix = ("décision du salarié : passé outre — a gardé le fichier (« continuer ») malgré l'avertissement"
                           if details.get("contexte") == "telechargement" else
                           "décision du salarié : passé outre — a cliqué « continuer » malgré l'avertissement")
                etapes.append(_mk_humain("choix", d_choix, ev))
            elif choix == "annuler":
                etapes.append(_mk_humain("choix", "décision du salarié : a annulé le geste (« annuler ») — bon réflexe", ev))
        elif typ in ("requete", "entree_agent", "contexte", "note"):
            brut = details.get("note") or details.get("activite") or details.get("contexte")
            if not brut:
                brut = f"{ev.get('methode') or ''} {ev.get('chemin') or ''}".strip() or "activité sur le poste du salarié"
            etapes.append(_mk_humain("contexte", _abrege(brut), ev))
        elif typ == "signalement":
            # Le salarié signale un mail : le mail reçu, puis son signalement et ce que
            # l'analyseur en pensait. Le texte libre est déjà neutralisé à l'ingestion.
            doc = details.get("document_source") if isinstance(details.get("document_source"), dict) else {}
            objet = doc.get("titre")
            d_ctx = "mail reçu" + (f" : « {_abrege(objet, 120)} »" if objet else "")
            if details.get("cible"):
                d_ctx += f" — expéditeur : {_abrege(details['cible'], 120)}"
            etape_ctx = _mk_humain("contexte", d_ctx, ev)
            if doc:
                etape_ctx["document_source"] = doc
            etapes.append(etape_ctx)
            verdict = _VERDICT_ANALYSEUR.get(details.get("verdict_analyseur"), "inconnu")
            etapes.append(_mk_humain(
                "signalement", f"le salarié a signalé ce mail ; verdict de l'analyseur : {verdict}", ev,
                list(_TECH_HUMAIN["humain_phishing"])))
        elif typ == "relecture" and details.get("acte") == "quatre_yeux" and details.get("decision") in _RELECTURE_HUMAIN:
            # Le relecteur IA a tranché le geste critique : c'est son vrai état, cité par le récit.
            etapes.append(_mk_humain("consequence", _RELECTURE_HUMAIN[details["decision"]], ev))
            a_consequence = True
        elif typ == "leurre_touche" and intrusion:
            tech = list(_TECH_HUMAIN["humain_intrusion_physique"])
            if leurre is not None:
                tech += [{"id": t, "nom": t, "cadre": _cadre_technique(t)} for t in getattr(leurre, "techniques", [])]
            risk = [{"id": r, "nom": r} for r in getattr(leurre, "risques", [])] if leurre is not None else []
            etapes.append(_mk_humain("action_risquee", "accès à un actif-leurre physique (canari) — intrusion détectée", ev, tech, risk))

        # Conséquence / escalade portée par un événement dédié (sortie, riposte, escalade).
        if typ in ("sortie_agent", "riposte") or details.get("exfiltration") or details.get("escalade") or details.get("consequence"):
            brut = details.get("consequence")
            if not brut:
                brut = "escalade au SOC" if (typ == "riposte" or details.get("escalade")) else "le geste a abouti (sortie de données)"
            etapes.append(_mk_humain("consequence", _abrege(brut), ev))
            a_consequence = True

    # Passé outre sans événement de conséquence : on matérialise l'escalade (le geste a abouti).
    if a_continuer and not a_consequence and ev_continuer is not None:
        etapes.append(_mk_humain("consequence", "geste abouti malgré l'avertissement — escalade au SOC", ev_continuer))

    etapes.sort(key=lambda s: cle_chronologique(s, _ORDRE_HUMAIN))
    for i, e in enumerate(etapes):
        e["ordre"] = i
    return etapes
