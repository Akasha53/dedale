"""Gouvernance des agents IA : le lien entre le Store et les modules politiques/anomalies.

Le Store appelle ces fonctions en quelques lignes, pour que les règles du SOC et les écarts
à l'habitude ouvrent un incident et prennent leur place dans la boîte noire :

- `apres_ingestion` : relève une règle déclenchée (`details.politique`, posé par la
  passerelle) et cherche un écart à l'habitude (`details.anomalie`, posé ici) ;
- `type_titre`, `ajuster` : type, titre, gravité et résumé des incidents `interne_politique`
  et `interne_anomalie` ;
- `maillon` : titre et détail des étapes `regle` et `anomalie` de la chaîne.

Une alerte (règle « alerter » ou écart à l'habitude) ne suspend pas l'agent. Une règle
« retenir » le suspend jusqu'à la décision de l'analyste ; une règle « bloquer » a déjà
arrêté l'appel côté passerelle.
"""

from __future__ import annotations

from . import anomalies, inventaire, politiques

TYPE_POLITIQUE = "interne_politique"
TYPE_ANOMALIE = "interne_anomalie"
TYPES = (TYPE_POLITIQUE, TYPE_ANOMALIE)
ETAPES = ("regle", "anomalie")
_RANG = {"faible": 1, "moyenne": 2, "haute": 3, "critique": 4}


def _court(texte, limite=200) -> str:
    return politiques._court(texte, limite)


def apres_ingestion(store, sess, enreg: dict, *, rejeu: bool = False) -> None:
    """Appelé par `Store.ingerer` une fois l'événement rangé, avant le tri et l'incident."""
    if sess.source != "interne":
        return
    details = enreg.get("details")
    if not isinstance(details, dict):
        return
    if not rejeu:
        # Seul le backend écrit une anomalie : un champ venu de l'extérieur est retiré.
        details.pop("anomalie", None)
        anomalie = anomalies.examiner(store, enreg)
        if anomalie is not None:
            details["anomalie"] = anomalie
    if (not rejeu and not isinstance(details.get("politique"), dict)
            and isinstance(details.get("droit_retire"), str)):
        # Appel refusé pour un droit retiré : la tentative reste visible au SOC (incident,
        # maillon de la boîte noire), rattachée à la règle ou au correctif qui a retiré le droit.
        retrait = politiques.politique_du_retrait(sess, details["droit_retire"])
        if retrait is not None:
            details["politique"] = retrait
    pol = details.get("politique")
    if isinstance(pol, dict):
        connue = politiques.registre.par_id(pol.get("id")) if pol.get("id") else None
        propre = {
            "id": _court(pol.get("id") or "", 20),
            "numero": connue["numero"] if connue else pol.get("numero"),
            "effet": (pol.get("effet") if pol.get("effet") in (*politiques.EFFETS, "droit_retire")
                      else "alerter"),
            "texte": connue["texte"] if connue else _court(pol.get("texte"), 200),
            "enonce": connue["enonce"] if connue else _court(pol.get("enonce"), 200),
            "constat": _court(pol.get("constat"), 200),
        }
        details["politique"] = propre
        sess.regles_declenchees.append({
            **{k: propre[k] for k in ("id", "numero", "effet", "texte", "constat")},
            "outil": enreg.get("outil"), "verdict": details.get("verdict"),
            "evenement_id": enreg.get("id"), "horodatage": enreg.get("horodatage"),
        })
        if (not rejeu and propre["effet"] == "retenir" and details.get("verdict") == "retenu"
                and sess.etat == "active"):
            # L'appel est retenu par la passerelle : la session attend l'analyste.
            sess.etat = "suspendue"
    anomalie = details.get("anomalie")
    if isinstance(anomalie, dict):
        sess.anomalies.append({
            "code": anomalie.get("code"), "codes": anomalie.get("codes"),
            "gravite": anomalie.get("gravite"), "raison": anomalie.get("raison"),
            "outil": enreg.get("outil"), "evenement_id": enreg.get("id"),
            "horodatage": enreg.get("horodatage"),
        })


def type_titre(sess) -> tuple[str, str]:
    """Type et titre quand seule la gouvernance a ouvert l'incident (ni canari, ni droits)."""
    nom = inventaire.nom(sess.agent)
    if sess.regles_declenchees:
        r = sess.regles_declenchees[0]
        if r.get("effet") == "droit_retire":
            return TYPE_POLITIQUE, (f"Tentative bloquée : {inventaire.libelle_agent(sess.agent)} a voulu "
                                    f"{politiques.verbe_outil(r.get('outil'))}, droit retiré par "
                                    f"{politiques.origine_du_retrait(r)}")
        return TYPE_POLITIQUE, f"Règle n°{r.get('numero')} du SOC déclenchée ({nom})"
    a = sess.anomalies[0]
    libelle = anomalies.LIBELLES.get(a.get("code"), "écart à l'habitude")
    return TYPE_ANOMALIE, f"Comportement inhabituel : {libelle} ({nom})"


def ajuster(inc, sess) -> None:
    """Gravité et résumé propres aux deux types de gouvernance (faible ou moyenne)."""
    if inc.type not in TYPES:
        return
    gravites = []
    if sess.regles_declenchees:
        gravites += ["moyenne" if r.get("effet") in ("bloquer", "retenir", "droit_retire") else "faible"
                     for r in sess.regles_declenchees]
    gravites += [a.get("gravite") or "faible" for a in sess.anomalies]
    inc.gravite = max(gravites or ["faible"], key=lambda g: _RANG.get(g, 1))
    if inc.type == TYPE_POLITIQUE and sess.regles_declenchees[-1].get("effet") == "droit_retire":
        r = sess.regles_declenchees[-1]
        n = sum(1 for x in sess.regles_declenchees if x.get("effet") == "droit_retire")
        inc.resume = (f"Tentative{'s' if n > 1 else ''} bloquée{'s' if n > 1 else ''} ({n}) : "
                      f"{politiques.verbe_outil(r.get('outil'))}, droit retiré par "
                      f"{politiques.origine_du_retrait(r)}. L'agent poursuit sa tâche.")
    elif inc.type == TYPE_POLITIQUE:
        r = sess.regles_declenchees[-1]
        issue = {"refuse": "bloqué", "retenu": "mis en attente", "autorise": "laissé passer"}.get(
            r.get("verdict"), "signalé")
        inc.resume = (f"Règle n°{r.get('numero')} déclenchée {len(sess.regles_declenchees)} fois. "
                      f"Dernier appel : {_court(r.get('outil') or 'inconnu', 60)}, {issue}.")
    else:
        a = sess.anomalies[-1]
        inc.resume = f"Écart à l'habitude de {inventaire.libelle_agent(sess.agent)} : {a.get('raison')}."


def suspendre_a_l_ouverture(typ: str) -> bool:
    """Une alerte de gouvernance n'arrête pas l'agent ; « retenir » suspend à l'ingestion."""
    return typ not in TYPES


def maillon(etape: str, ev: dict) -> dict:
    """Titre et détail d'une étape `regle` ou `anomalie` de la boîte noire."""
    if etape == "regle":
        return politiques.maillon(ev)
    a = (ev.get("details") or {}).get("anomalie") or {}
    libelle = a.get("libelle") or anomalies.LIBELLES.get(a.get("code"), "écart à l'habitude")
    raison = _court(a.get("raison"), 240)
    titre = f"Comportement inhabituel : {libelle}"
    return {"titre": titre, "libelle": titre, "detail": raison + ".", "resume": raison + ".",
            "anomalie_codes": a.get("codes") or [a.get("code")], "anomalie_gravite": a.get("gravite")}


def vider() -> None:
    """Remise à zéro complète (tests)."""
    anomalies.vider()
    politiques.registre.vider()
    from . import resistance

    resistance.registre.vider()
