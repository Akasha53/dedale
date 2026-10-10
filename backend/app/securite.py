"""Neutralisation des textes piégés.

Tout contenu de leurre, toute consigne lue par un agent, est de la DONNÉE, jamais une
instruction (règle dure de Dédale). Avant d'exposer un tel texte dans une réponse de l'API,
dans la console ou dans un prompt vers un modèle, il passe par `neutraliser` : on l'échappe
pour le HTML, on aplatit les retours ligne, on retire les caractères de contrôle, on tronque,
et on l'enveloppe de marqueurs explicites. Il ne doit jamais atterrir en position de système
ou d'instruction.
"""

from __future__ import annotations

import html
import re
import unicodedata

LIMITE_DEFAUT = 600

# Caractères de contrôle (sauf tabulation/espace déjà gérés) et séparateurs invisibles.
_CTRL = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏  ﻿]")
_ESPACES = re.compile(r"\s+")


def neutraliser(valeur: object, limite: int = LIMITE_DEFAUT) -> str:
    """Rend un texte inerte et sûr à afficher. Jamais exécutable, jamais une consigne."""
    texte = valeur if isinstance(valeur, str) else repr(valeur)
    # Normalise l'unicode pour éviter les variantes homoglyphes exotiques.
    texte = unicodedata.normalize("NFKC", texte)
    texte = _CTRL.sub(" ", texte)
    texte = _ESPACES.sub(" ", texte).strip()
    tronque = False
    if len(texte) > limite:
        texte = texte[:limite].rstrip()
        tronque = True
    texte = html.escape(texte, quote=True)
    if not texte:
        return "[vide]"
    marque = "[leurre, neutralisé] "
    suffixe = " […]" if tronque else ""
    return f"{marque}{texte}{suffixe}"


def extrait(valeur: object, limite: int = 200) -> str:
    """Version courte pour les résumés de chaîne (boîte noire)."""
    return neutraliser(valeur, limite=limite)


def neutraliser_details(details: dict, champs: tuple[str, ...]) -> dict:
    """Copie `details` en neutralisant seulement les champs nommés (texte potentiellement piégé).

    On ne touche pas aux champs techniques (verite_terrain, chemins, booléens) : seuls les
    contenus rédigés par la surface piégée sont dangereux à réinjecter.
    """
    propre = dict(details)
    for champ in champs:
        if champ in propre and propre[champ] is not None:
            propre[champ] = neutraliser(propre[champ])
    return propre


# --- Document source : montré en entier, mais désarmé ------------------------------------
# Le mail ou le document piégé qu'a lu l'agent est affiché à l'analyste (avertissement de
# CONTRATS.md, avenant « copilote »). Il reste de la donnée inerte : liens en hxxp(s), domaines
# en [.], paramètres d'URL et clés masqués, HTML échappé. Les sauts de ligne sont gardés pour
# que le mail se lise comme un mail.
_CTRL_DOC = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f​-‏  ﻿]")
_REQUETE = re.compile(r"(h(?:tt|xx)ps?://[^\s?#)\"'<>]+)\?(?!\[paramètres masqués\])[^\s)\"'<>]*",
                      re.IGNORECASE)
_SCHEMA = re.compile(r"\bhttp(s?)://", re.IGNORECASE)
_TLD = r"(?:example|com|fr|net|org|io|ai|dev|app|eu|co|info|biz|xyz)"
_HOTE = re.compile(rf"(?<![\w.\[-])((?:[a-z0-9-]+\.)+{_TLD})\b", re.IGNORECASE)
_CLE = re.compile(r"\b(?:[A-Z0-9]+-CANARY-[A-Za-z0-9-]+|(?:sk|pk|rk)[-_](?:live|test)[-_][A-Za-z0-9_-]{6,}"
                  r"|[A-Za-z0-9+/]{32,}={0,2})")
_IDENT_DOC = re.compile(r"^[A-Za-z0-9_.:\-]{1,80}$")
LIMITE_DOCUMENT = 8000


def desarmer(texte: object, limite: int = LIMITE_DOCUMENT) -> str:
    """Texte lisible et inerte : clés masquées, liens cassés, HTML échappé une fois."""
    t = unicodedata.normalize("NFKC", texte if isinstance(texte, str) else str(texte))
    t = _CTRL_DOC.sub(" ", t.replace("\r\n", "\n"))
    t = _REQUETE.sub(r"\1?[paramètres masqués]", t)
    t = _CLE.sub("[clé masquée]", t)
    t = _SCHEMA.sub(lambda m: f"hxxp{m.group(1)}://", t)
    t = _HOTE.sub(lambda m: m.group(1).replace(".", "[.]"), t)
    if len(t) > limite:
        t = t[:limite].rstrip() + " […]"
    return html.escape(t, quote=False)


def desarmer_document(doc: object) -> dict | None:
    """Forme exposée de `details.document_source`. Les positions `piege[].debut/fin` portent sur
    `corps` tel qu'il est renvoyé (déjà échappé)."""
    if not isinstance(doc, dict):
        return None
    segments_in = doc.get("segments")
    if not isinstance(segments_in, list):
        segments_in = [{"texte": doc.get("corps") or "", "piege": False}]
    segments, pieges, corps = [], [], ""
    for seg in segments_in:
        if not isinstance(seg, dict) or len(corps) >= LIMITE_DOCUMENT:
            continue
        texte = desarmer(seg.get("texte") or "", LIMITE_DOCUMENT - len(corps))
        piege = seg.get("piege") is True
        if piege:
            pieges.append({"debut": len(corps), "fin": len(corps) + len(texte)})
        corps += texte
        segments.append({"texte": texte, "piege": piege})
    sortie = {
        "type": doc.get("type") if doc.get("type") in ("mail", "document", "appel", "memoire") else "document",
        "origine": doc.get("origine") if doc.get("origine") in ("externe", "interne") else "inconnue",
        "canari_id": doc.get("canari_id") if _IDENT_DOC.match(str(doc.get("canari_id") or "")) else None,
        "empreinte": doc.get("empreinte") if _IDENT_DOC.match(str(doc.get("empreinte") or "")) else None,
    }
    for champ in ("id", "titre", "expediteur", "destinataire", "date"):
        if doc.get(champ):
            sortie[champ] = desarmer(doc[champ], 300).replace("\n", " ")
    sortie.update({
        "corps": corps,
        "segments": segments,
        "piege": pieges,
        "texte_piege": " ".join(" ".join(s["texte"].split()) for s in segments if s["piege"]),
        "instruction_cachee": bool(pieges),
        "desarme": True,
    })
    return sortie


# --- Désarmeur de la passerelle interne : ce qui a été retiré avant lecture ---------------
# `details.desarmement` (voir CONTRATS.md, avenant « désarmeur »). Le texte retiré arrive déjà
# désarmé par la passerelle ; on ne garde que les champs connus, on borne les listes et on
# neutralise chaque texte comme un champ piégé. Rien n'en ressort actionnable.
_CODE = re.compile(r"^[a-z_]{1,40}$")


def _codes(valeur, limite: int = 12) -> list[str]:
    if not isinstance(valeur, list):
        return []
    return [v for v in valeur if isinstance(v, str) and _CODE.match(v)][:limite]


def _empreinte_longueur(valeur) -> dict:
    valeur = valeur if isinstance(valeur, dict) else {}
    empreinte = valeur.get("empreinte")
    longueur = valeur.get("longueur")
    return {"empreinte": empreinte if _IDENT_DOC.match(str(empreinte or "")) else None,
            "longueur": longueur if isinstance(longueur, int) and longueur >= 0 else None}


def desarmer_desarmement(valeur: object) -> dict | None:
    """Forme exposée de `details.desarmement`."""
    if not isinstance(valeur, dict):
        return None
    retraits = []
    for r in valeur.get("retraits") if isinstance(valeur.get("retraits"), list) else []:
        if not isinstance(r, dict) or len(retraits) >= 20:
            continue
        retraits.append({
            "technique": r.get("technique") if _CODE.match(str(r.get("technique") or "")) else "inconnue",
            "libelle": neutraliser(r.get("libelle") or "", 80),
            "consigne": r.get("consigne") is True,
            "formules": _codes(r.get("formules")),
            "langues": _codes(r.get("langues"), 8),
            "texte": neutraliser(r.get("texte") or "", 600),
            **_empreinte_longueur(r),
        })
    duree = valeur.get("duree_ms")
    return {
        "nature": valeur.get("nature") if _CODE.match(str(valeur.get("nature") or "")) else "document",
        "document": neutraliser(valeur.get("document") or "", 120),
        "origine": valeur.get("origine") if valeur.get("origine") in ("externe", "interne") else "inconnue",
        "canari_id": valeur.get("canari_id") if _IDENT_DOC.match(str(valeur.get("canari_id") or "")) else None,
        "consigne": valeur.get("consigne") is True,
        "mode": valeur.get("mode") if valeur.get("mode") in ("retirer", "encadrer") else "retirer",
        "techniques": _codes(valeur.get("techniques")),
        "formules": _codes(valeur.get("formules")),
        "langues": _codes(valeur.get("langues"), 8),
        "retraits": retraits,
        "nombre_retraits": len(retraits),
        "avant": _empreinte_longueur(valeur.get("avant")),
        "apres": _empreinte_longueur(valeur.get("apres")),
        "duree_ms": round(float(duree), 3) if isinstance(duree, (int, float)) and duree >= 0 else None,
        "actionnable": False,
    }
