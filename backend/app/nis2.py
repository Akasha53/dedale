"""Brouillon factuel d'alerte précoce NIS2, à relire avant tout envoi.

La qualification d'incident significatif et l'obligation de notifier restent humaines.
Le texte ne déduit ni fuite de données ni blocage d'un poste à partir d'un simple signal.
"""

from __future__ import annotations

from datetime import datetime, timezone

from . import config, securite


_GESTES = {
    "humain_phishing": "Un salarié a poursuivi l'ouverture d'un lien suspect après avertissement.",
    "humain_secret": "Un salarié a poursuivi un geste impliquant un secret après avertissement.",
    "humain_mail_externe": "Un salarié a poursuivi un envoi vers une adresse externe après avertissement.",
    "humain_upload_ia": "Un salarié a poursuivi un dépôt vers un service d'IA après avertissement.",
    "humain_intrusion_physique": "Un accès à un actif-leurre physique a été détecté.",
}

_ACTIONS = {
    "couper": "L'analyste a coupé la session de l'agent.",
    "valider_riposte": "L'analyste a validé la riposte et coupé la session de l'agent.",
    "reprendre": "L'analyste a repris la session de l'agent sous surveillance.",
    "ignorer": "L'analyste a classé le signal sans suite.",
    "clore": "L'analyste a clos l'incident humain ; aucun blocage du poste n'est attesté.",
}


def _fait(valeur: object, limite: int = 120) -> str:
    """Aplatit une valeur issue des événements sans la traiter comme une instruction."""
    if valeur is None:
        return "à confirmer"
    return securite.neutraliser(valeur, limite).removeprefix("[leurre, neutralisé] ")


def _faits(incident: dict) -> dict:
    sess = incident.get("session") or {}
    typ = incident.get("type") or ""
    est_humain = typ.startswith("humain_")
    etapes = [e.get("etape") for e in incident.get("chaine", []) if e.get("etape")]
    action = incident.get("action")
    etat = sess.get("etat")
    if action in _ACTIONS:
        mesure = _ACTIONS[action]
    elif est_humain:
        mesure = "Avertissement affiché et signal transmis au SOC ; décision de l'analyste en attente."
    elif etat == "suspendue":
        mesure = "La session de l'agent est suspendue dans sAIfe ; décision de l'analyste en attente."
    elif etat == "coupee":
        mesure = "La session de l'agent est coupée dans sAIfe."
    else:
        mesure = "Mesures de confinement et décision de l'analyste à confirmer."

    if est_humain:
        nature = _GESTES.get(typ, "Un geste à risque sur le poste a été signalé au SOC.")
        impact = "Conséquences du geste et éventuelle fuite de données : à confirmer."
    else:
        nature = "Une activité suspecte impliquant un agent IA a été signalée par sAIfe."
        impact = (
            "Tentative de sortie de données observée ; aboutissement et données concernées à confirmer."
            if "tentative_sortie" in etapes
            else "Aucune tentative de sortie documentée dans la chaîne ; impact à confirmer."
        )

    return {
        "reference": _fait(incident.get("id")),
        "type_incident": _fait(typ),
        "cree_a": _fait(incident.get("cree_a")),
        "classement": _fait(sess.get("classement")),
        "statut": _fait(incident.get("statut")),
        "nature": nature,
        "impact": impact,
        "mesure": mesure,
        "etapes": [_fait(e, 80) for e in etapes],
        "leurres": [_fait(l, 80) for l in incident.get("leurres_touches", [])],
    }


def gabarit(incident: dict) -> str:
    f = _faits(incident)
    maintenant = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    etapes = " → ".join(f["etapes"]) if f["etapes"] else "chaîne en cours de reconstruction"
    leurres = ", ".join(f["leurres"]) if f["leurres"] else "aucun leurre signalé"
    return f"""ALERTE PRÉCOCE NIS2 (article 23) — BROUILLON À RELIRE

Qualification préalable : déterminer si l'incident est significatif et si l'entité relève de l'obligation de notification. Ce brouillon n'a pas été transmis.

Destinataire envisagé : CSIRT ou autorité compétente
Entité concernée : {config.ENTITE} (entité fictive, exercice Secure Horizons)
Date de rédaction : {maintenant}
Référence interne : {f['reference']}
Création de l'incident dans sAIfe : {f['cree_a']}

1. Nature de l'incident
   {f['nature']}
   Type sAIfe : {f['type_incident']}. Classement de la session : {f['classement']}.

2. Chronologie observée
   {etapes}
   Leurres ou canaris déclenchés : {leurres}.

3. Impact à qualifier
   {f['impact']}
   Services affectés, données concernées et personnes touchées : à confirmer.

4. Caractère transfrontalier
   À confirmer ; le journal sAIfe ne suffit pas à le déterminer.

5. Mesures et suivi
   {f['mesure']}
   Statut du dossier : {f['statut']}.

Si l'incident est significatif et soumis à NIS2, vérifier les échéances applicables : alerte précoce sous 24 h après prise de connaissance, notification sous 72 h et rapport final dans le mois suivant la notification.

Brouillon généré par sAIfe. L'analyste doit vérifier les faits et la qualification avant tout envoi.
"""


async def generer(incident: dict) -> dict:
    """Le gabarit garde l'incertitude explicite et évite les faits ajoutés par un modèle."""
    return {"texte": gabarit(incident), "origine": "gabarit"}
