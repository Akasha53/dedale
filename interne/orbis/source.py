"""Document source d'un incident : le mail ou le document piégé, montré en entier mais désarmé.

L'analyste doit pouvoir lire ce que l'agent a lu : expéditeur, objet, corps. La partie piégée
est repérée (segments `piege: true`) pour être surlignée, et rendue inerte avant de quitter la
passerelle :

- les liens perdent leur schéma actif (`https://` devient `hxxps://`) et leurs paramètres ;
- les domaines et adresses prennent `[.]` à la place du point ;
- toute clé, même fictive, est remplacée par « [clé masquée] ».

Le texte n'est jamais lu comme une instruction : on le découpe et on le recopie, rien de plus.
"""

from __future__ import annotations

import re

from . import detection
from .enregistreur import empreinte

# Parties piégées reconnaissables à leur forme : commentaire HTML, note entre crochets.
_BLOCS_PIEGES = [
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"\[NOTE.*?FIN NOTE\]", re.DOTALL | re.IGNORECASE),
]
_PARAGRAPHES = re.compile(r"\n\s*\n")

_REQUETE = re.compile(r"(https?://[^\s?#)\"'<>]+)\?[^\s)\"'<>]*", re.IGNORECASE)
_SCHEMA = re.compile(r"\bhttp(s?)://", re.IGNORECASE)
_TLD = r"(?:example|com|fr|net|org|io|ai|dev|app|eu|co|info|biz|xyz)"
_HOTE = re.compile(rf"(?<![\w.-])((?:[a-z0-9-]+\.)+{_TLD})\b", re.IGNORECASE)
_CLE = re.compile(r"\b(?:[A-Z0-9]+-CANARY-[A-Za-z0-9-]+|(?:sk|pk|rk)[-_](?:live|test)[-_][A-Za-z0-9_-]{6,}"
                  r"|[A-Za-z0-9+/]{32,}={0,2})")

TYPES = {"lire_mail": "mail", "chercher_document": "document", "chercher_appel": "appel",
         "lire_memoire": "memoire"}


def desarmer(texte: str, jetons: dict[str, str] | None = None) -> str:
    """Rend un texte inerte : clés masquées, paramètres d'URL retirés, liens et domaines cassés."""
    t = _REQUETE.sub(r"\1?[paramètres masqués]", texte or "")
    for jeton in (jetons or {}).values():
        if jeton:
            t = t.replace(jeton, "[clé masquée]")
    t = _CLE.sub("[clé masquée]", t)
    t = _SCHEMA.sub(lambda m: f"hxxp{m.group(1)}://", t)
    return _HOTE.sub(lambda m: m.group(1).replace(".", "[.]"), t)


def _spans_pieges(texte: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for motif in _BLOCS_PIEGES:
        spans += [m.span() for m in motif.finditer(texte)]
    if not spans:
        # Sans forme reconnaissable : les paragraphes qui portent un marqueur ou un lien externe.
        debut = 0
        for m in list(_PARAGRAPHES.finditer(texte)) + [None]:
            fin = m.start() if m else len(texte)
            if detection.consigne_cachee_dans(texte[debut:fin]):
                spans.append((debut, fin))
            debut = m.end() if m else fin
    spans.sort()
    fusion: list[tuple[int, int]] = []
    for a, b in spans:
        if fusion and a <= fusion[-1][1]:
            fusion[-1] = (fusion[-1][0], max(b, fusion[-1][1]))
        else:
            fusion.append((a, b))
    return fusion


def segments(texte: str, jetons: dict[str, str] | None = None) -> list[dict]:
    """Découpe le corps en segments ordinaires et piégés, chacun désarmé."""
    sortie: list[dict] = []
    curseur = 0
    for a, b in _spans_pieges(texte):
        if a > curseur:
            sortie.append({"texte": desarmer(texte[curseur:a], jetons), "piege": False})
        sortie.append({"texte": desarmer(texte[a:b], jetons), "piege": True})
        curseur = b
    if curseur < len(texte):
        sortie.append({"texte": desarmer(texte[curseur:], jetons), "piege": False})
    return sortie


def _titre_markdown(texte: str, defaut: str) -> str:
    for ligne in texte.splitlines():
        if ligne.startswith("# "):
            return ligne[2:].strip()
    return defaut


def document_source(outil: str, element, jetons: dict[str, str] | None = None, *,
                    canari_id: str | None = None, origine: str = "externe") -> dict:
    """Le document lu par l'agent, au format `details.document_source` (voir CONTRATS.md)."""
    el = element if isinstance(element, dict) else {"texte": str(element)}
    type_ = TYPES.get(outil, "document")
    if type_ == "mail":
        corps = str(el.get("corps") or "")
        champs = {"id": el.get("id"), "titre": el.get("sujet"), "expediteur": el.get("de"),
                  "destinataire": el.get("a"), "date": el.get("date")}
    elif type_ == "appel":
        corps = str(el.get("transcription") or "")
        champs = {"id": el.get("id"), "titre": _titre_markdown(corps, str(el.get("id") or "appel"))}
    elif type_ == "memoire":
        corps = str(el.get("texte") or el)
        champs = {"id": el.get("id"), "titre": "Entrée de la mémoire de l’agent"}
    else:
        corps = str(el.get("contenu") or el.get("texte") or "")
        nom = str(el.get("nom") or el.get("chemin") or "document")
        champs = {"id": nom, "titre": _titre_markdown(corps, nom)}
    doc = {"type": type_, **{k: desarmer(str(v), jetons) for k, v in champs.items() if v}}
    doc.update({
        "origine": origine,
        "canari_id": canari_id,
        "empreinte": empreinte(corps),
        "segments": segments(corps, jetons),
    })
    return doc
