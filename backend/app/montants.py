"""Lecture des montants et des volumes dans un texte, pour le relecteur IA.

Un montant mal lu fait accorder un virement dangereux : « 48,5 k€ » lu 48,5 €. Ce module lit les
formats courants et dit quand il doute, pour que les règles retiennent le geste au lieu de
l'accorder.

- chiffres : « 48 500 € », « 48.500 € », « 48,500 € », « 48 500,00 EUR », « 48,500.00 USD », « € 320 » ;
- multiplicateurs : « 48,5 k€ », « 12k EUR », « 1,2 M€ », « 3 millions d'euros », « 2 mds € » ;
- en lettres, jusqu'aux milliards : « douze mille euros », « quatre-vingt-dix mille euros »,
  « un million deux cent mille euros » ;
- devises : €, EUR, euro(s), $, USD, dollar(s), £, GBP, CHF. Seul l'euro se compare aux seuils.

Rien n'est exécuté : le texte est découpé et compté.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_DEVISES = [
    (r"€|eur(?:os?)?\b|euros?\b", "EUR"),
    (r"\$|usd\b|dollars?\b", "USD"),
    (r"£|gbp\b|livres? sterling\b", "GBP"),
    (r"chf\b|francs? suisses?\b", "CHF"),
]
_DEVISE = "|".join(f"(?:{m})" for m, _ in _DEVISES)
_MULT = {"k": 1e3, "ke": 1e3, "mille": 1e3, "milliers": 1e3, "m": 1e6, "me": 1e6, "million": 1e6,
         "millions": 1e6, "md": 1e9, "mds": 1e9, "mrd": 1e9, "milliard": 1e9, "milliards": 1e9}
_NOMBRE = r"(?<![\d.,'])(\d{1,3}(?:[ .,']\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)"
_MULTIPLICATEUR = r"(k|md?s?|mrd|mille|milliers?|millions?|milliards?)?"
# « 48,5 k€ », « 48 500,00 EUR », « 3 millions d'euros »
_APRES = re.compile(_NOMBRE + r"\s?" + _MULTIPLICATEUR + r"\s?(?:d['’]\s?|de\s)?(" + _DEVISE + r")", re.IGNORECASE)
# « € 320 », « EUR 1.2M », « $48,500 »
_AVANT = re.compile(r"(" + _DEVISE + r")\s?" + _NOMBRE + r"\s?" + r"(k|m|md|mds|millions?)?\b", re.IGNORECASE)
_INDICES = re.compile(r"€|\beur|euro|\$|usd|dollar|£|gbp|chf|k€|m€|\bmille\b|millions?|milliards?", re.IGNORECASE)

_UNITES = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7,
    "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}
_MOTS_NOMBRE = set(_UNITES) | {"cent", "cents", "mille", "million", "millions", "milliard", "milliards", "et"}


@dataclass(frozen=True)
class Montant:
    valeur: float
    devise: str
    brut: str


def _plat(texte: str) -> str:
    t = unicodedata.normalize("NFKC", texte or "")
    t = t.replace(" ", " ").replace(" ", " ")
    return t


def _sans_accents(texte: str) -> str:
    return unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode().lower()


def _devise(brut: str) -> str:
    for motif, code in _DEVISES:
        if re.fullmatch(motif, brut.strip(), re.IGNORECASE):
            return code
    return "EUR"


def nombre(brut: str, multiplicateur: bool = False) -> float | None:
    """« 48 500,00 » → 48500.0, « 48.500 » → 48500.0, « 48,5 » → 48.5, « 1,250.75 » → 1250.75.

    Un seul séparateur suivi de trois chiffres est un séparateur de milliers, sauf devant un
    multiplicateur (« 48,500 k€ » reste ambigu, on le lit 48,5 mille)."""
    t = re.sub(r"[ '’]", "", brut)
    points, virgules = t.count("."), t.count(",")
    if points and virgules:
        decimal = "." if t.rfind(".") > t.rfind(",") else ","
        t = t.replace("," if decimal == "." else ".", "").replace(decimal, ".")
    elif points or virgules:
        sep = "." if points else ","
        morceaux = t.split(sep)
        if len(morceaux) > 2 or (len(morceaux[-1]) == 3 and not multiplicateur):
            t = t.replace(sep, "")
        else:
            t = t.replace(sep, ".")
    try:
        return float(t)
    except ValueError:
        return None


def _en_lettres(mots: list[str]) -> float | None:
    """« quatre vingt dix mille » → 90000. Les mots sont déjà sans accents ni tirets."""
    total, courant, vu = 0.0, 0.0, False
    precedent = ""
    for m in mots:
        if m == "et":
            continue
        if m in ("vingt", "vingts") and precedent == "quatre":
            courant += 80 - 4
        elif m in _UNITES:
            courant += _UNITES[m]
        elif m in ("cent", "cents"):
            courant = (courant or 1) * 100
        elif m == "mille":
            total += (courant or 1) * 1e3
            courant = 0
        elif m in ("million", "millions"):
            total += (courant or 1) * 1e6
            courant = 0
        elif m in ("milliard", "milliards"):
            total += (courant or 1) * 1e9
            courant = 0
        else:
            return None
        vu = True
        precedent = m
    return total + courant if vu else None


def _montants_en_lettres(texte: str) -> list[Montant]:
    sortie = []
    mots = re.findall(r"[a-z]+|€|\$|£|'", _sans_accents(_plat(texte)).replace("-", " "))
    for i, m in enumerate(mots):
        devise = {"euro": "EUR", "euros": "EUR", "eur": "EUR", "€": "EUR", "dollars": "USD", "dollar": "USD",
                  "$": "USD", "£": "GBP", "chf": "CHF"}.get(m)
        if devise is None:
            continue
        j = i - 1
        while j >= 0 and mots[j] in ("d", "de", "'"):
            j -= 1
        suite = []
        while j >= 0 and mots[j] in _MOTS_NOMBRE:
            suite.insert(0, mots[j])
            j -= 1
        if suite and suite != ["et"]:
            v = _en_lettres(suite)
            if v is not None:
                sortie.append(Montant(v, devise, " ".join(suite + [m])))
    return sortie


def lire_montants(texte: str) -> list[Montant]:
    """Tous les montants lus, dans l'ordre du texte, chiffres et lettres."""
    t = _plat(texte)
    sortie: list[Montant] = []
    pris: list[tuple[int, int]] = []
    for m in _APRES.finditer(t):
        mult = (m.group(2) or "").lower()
        v = nombre(m.group(1), multiplicateur=bool(mult))
        if v is None:
            continue
        sortie.append(Montant(v * _MULT.get(mult, 1), _devise(m.group(3)), m.group(0)))
        pris.append(m.span())
    for m in _AVANT.finditer(t):
        if any(a <= m.start() < b for a, b in pris):
            continue
        mult = (m.group(3) or "").lower()
        v = nombre(m.group(2), multiplicateur=bool(mult))
        if v is not None:
            sortie.append(Montant(v * _MULT.get(mult, 1), _devise(m.group(1)), m.group(0)))
    sortie += _montants_en_lettres(t)
    return sortie


def lire_montant(texte: str) -> tuple[float | None, str, str]:
    """(montant en euros, lecture, devise). `lecture` vaut :
    - `certain` : un seul montant en euros, sans ambiguïté ;
    - `incertain` : plusieurs montants différents, une autre devise, ou un indice d'argent (€,
      « mille », « k€ ») que la lecture n'a pas su convertir ;
    - `absent` : aucun montant ni indice d'argent."""
    montants = lire_montants(texte)
    valeurs = {round(m.valeur, 2) for m in montants}
    devises = {m.devise for m in montants}
    if not montants:
        return None, ("incertain" if _INDICES.search(_plat(texte)) else "absent"), "EUR"
    if devises != {"EUR"}:
        return None, "incertain", "/".join(sorted(devises))
    if len(valeurs) > 1:
        return max(valeurs), "incertain", "EUR"
    return valeurs.pop(), "certain", "EUR"


_UNITES_VOLUME = r"(?:fiches|clients|lignes|contacts|enregistrements|dossiers|comptes)"
_VOLUME = re.compile(_NOMBRE + r"\s?(k|mille|millions?)?\s?" + _UNITES_VOLUME, re.IGNORECASE)


def lire_volume(texte: str) -> int | None:
    """« 12 400 fiches » → 12400, « 12k fiches » → 12000, « douze mille fiches » → 12000."""
    t = _plat(texte)
    m = _VOLUME.search(t)
    if m:
        mult = (m.group(2) or "").lower()
        v = nombre(m.group(1), multiplicateur=bool(mult))
        if v is not None:
            return int(v * _MULT.get(mult, 1))
    mots = re.findall(r"[a-z]+", _sans_accents(t).replace("-", " "))
    for i, w in enumerate(mots):
        if re.fullmatch(_UNITES_VOLUME, w):
            suite, j = [], i - 1
            while j >= 0 and mots[j] in _MOTS_NOMBRE:
                suite.insert(0, mots[j])
                j -= 1
            if suite:
                v = _en_lettres(suite)
                if v is not None:
                    return int(v)
    return None
