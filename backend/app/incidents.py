"""Boîte noire : reconstruction de la chaîne d'un incident.

À partir des événements d'une session (ou d'un canari touché), on recompose l'enchaînement
  document/mail piégé -> consigne lue -> action -> tentative de sortie de données.
Chaque étape porte un résumé NEUTRALISÉ : le texte piégé n'est jamais réinjecté tel quel.
"""

from __future__ import annotations

from typing import Any

from . import securite

# Ordre canonique des étapes de la boîte noire.
ORDRE_ETAPES = ["appat", "consigne_lue", "action", "tentative_sortie", "riposte"]

_LIBELLES = {
    "appat": "Document/mail piégé rencontré",
    "consigne_lue": "Consigne cachée lue",
    "action": "Action sur une route ou un outil découvert",
    "tentative_sortie": "Tentative de sortie de données",
    "riposte": "Riposte appliquée",
}

# Correspondance étape interne -> phase lue par la console.
_PHASE = {
    "appat": "entree",
    "consigne_lue": "consigne",
    "action": "outil",
    "tentative_sortie": "sortie",
    "riposte": "riposte",
}


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


def gravite(chaine: list[dict], source: str) -> str:
    phases = {e.get("etape") for e in chaine}
    if "tentative_sortie" in phases:
        return "critique"
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
    if typ == "sortie_agent" or details.get("exfiltration"):
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


def construire_chaine(evenements: list[dict], leurres: dict[str, Any]) -> list[dict]:
    """Chaîne de la boîte noire. Chaque étape porte les champs internes (etape, resume) ET les
    champs lus par la console (ordre, phase, titre, detail, techniques, risques)."""
    etapes: list[dict] = []
    for ev in sorted(evenements, key=lambda e: (e.get("horodatage") or "", e.get("id", 0))):
        etape = _etape_pour(ev, leurres)
        if etape is None:
            continue
        details = ev.get("details") or {}
        leurre = leurres.get(ev.get("leurre_id")) if ev.get("leurre_id") else None
        violation = details.get("violation_droits") if isinstance(details.get("violation_droits"), dict) else None
        texte_source = next((details[c] for c in _CHAMPS_PIEGES if details.get(c)), None)
        if violation is not None:
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
            detail = securite.extrait(texte_source)
        leurre_id = ev.get("leurre_id")
        canari_id = leurre_id if (leurre_id and str(leurre_id).startswith("C-")) else None
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
                "techniques": _techniques(leurre),
                "risques": _risques(leurre),
            }
        )
    etapes.sort(key=lambda s: (ORDRE_ETAPES.index(s["etape"]) if s["etape"] in ORDRE_ETAPES else 99, s["horodatage"] or ""))
    for i, e in enumerate(etapes):
        e["ordre"] = i
    return etapes


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

_ORDRE_HUMAIN = ["contexte", "action_risquee", "avertissement", "choix", "consequence"]

_LIBELLES_HUMAIN = {
    "contexte": "Contexte du poste",
    "action_risquee": "Action risquée détectée",
    "avertissement": "Avertissement affiché au salarié",
    "choix": "Choix du salarié",
    "consequence": "Conséquence / escalade",
}

# Catégorie de geste (posée par le poste dans details.categorie) → type d'incident console.
_TYPE_HUMAIN = {
    "secret": "humain_secret",
    "mail_externe": "humain_mail_externe",
    "upload_ia": "humain_upload_ia",
    "phishing": "humain_phishing",
    "intrusion_physique": "humain_intrusion_physique",
}

_TITRE_HUMAIN = {
    "humain_secret": "Secret exposé par un salarié",
    "humain_mail_externe": "Données sensibles envoyées en externe",
    "humain_upload_ia": "Fichier confidentiel déposé vers une IA non autorisée",
    "humain_phishing": "Salarié piégé par un lien de phishing",
    "humain_intrusion_physique": "Intrusion physique sur un actif-leurre",
}

_GESTE_LIBELLE = {
    "secret": "le salarié s'apprête à exposer un secret (mot de passe / clé API)",
    "mail_externe": "le salarié s'apprête à envoyer des données sensibles à un destinataire externe",
    "upload_ia": "le salarié s'apprête à déposer un fichier confidentiel vers une IA non autorisée",
    "phishing": "le salarié s'apprête à cliquer un lien de phishing / ouvrir une pièce jointe piégée",
    "intrusion_physique": "accès à un actif-leurre physique (serveur / port)",
}

_NIVEAUX = ("faible", "moyenne", "haute", "critique")

# Gravité par défaut d'un type de geste humain (surchargée par details.gravite d'un geste passé outre).
_GRAVITE_HUMAIN = {
    "humain_secret": "haute",
    "humain_mail_externe": "haute",
    "humain_upload_ia": "moyenne",
    "humain_phishing": "haute",
    "humain_intrusion_physique": "critique",
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


def type_humain(categorie: str | None, intrusion: bool = False) -> str:
    if intrusion:
        return "humain_intrusion_physique"
    return _TYPE_HUMAIN.get(categorie, "humain_secret")


def titre_humain(type_incident: str, session_id: str) -> str:
    return f"{_TITRE_HUMAIN.get(type_incident, 'Geste humain à risque')} ({session_id})"


def gravite_humaine(type_incident: str, gravite_annoncee: str | None = None) -> str:
    if gravite_annoncee in _NIVEAUX:
        return gravite_annoncee
    return _GRAVITE_HUMAIN.get(type_incident, "moyenne")


def resume_humain(chaine: list[dict], type_incident: str, passe_outre: bool) -> str:
    quoi = _TITRE_HUMAIN.get(type_incident, "geste humain à risque").lower()
    etat = "passé outre (signal fort)" if passe_outre else "respecté par le salarié"
    return (
        f"Pilier humain : {quoi}. Avertissement {etat}. "
        f"Chaîne de {len(chaine)} étape(s)."
    )


def _abrege(valeur: object, n: int = 240) -> str:
    """Tronque un texte DÉJÀ neutralisé en amont (store) pour l'affichage en frise.

    On ne re-neutralise pas : les champs piégés sont inertes dès leur stockage.
    """
    texte = valeur if isinstance(valeur, str) else str(valeur)
    texte = texte.strip()
    if len(texte) <= n:
        return texte or "[vide]"
    return texte[:n].rstrip() + " […]"


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

        if typ == "avertissement":
            geste = _GESTE_LIBELLE.get(cat, "geste à risque détecté sur le poste")
            cible = details.get("cible")
            d_action = geste + (f" — cible : {_abrege(cible, 160)}" if cible else "")
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
                etapes.append(_mk_humain("choix", "décision du salarié : passé outre — a cliqué « continuer » malgré l'avertissement", ev))
            elif choix == "annuler":
                etapes.append(_mk_humain("choix", "décision du salarié : a annulé le geste (« annuler ») — bon réflexe", ev))
        elif typ in ("requete", "entree_agent", "contexte", "note"):
            brut = details.get("note") or details.get("activite") or details.get("contexte")
            if not brut:
                brut = f"{ev.get('methode') or ''} {ev.get('chemin') or ''}".strip() or "activité sur le poste du salarié"
            etapes.append(_mk_humain("contexte", _abrege(brut), ev))
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

    etapes.sort(key=lambda s: (_ORDRE_HUMAIN.index(s["etape"]) if s["etape"] in _ORDRE_HUMAIN else 99, s["horodatage"] or ""))
    for i, e in enumerate(etapes):
        e["ordre"] = i
    return etapes
