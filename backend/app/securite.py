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
