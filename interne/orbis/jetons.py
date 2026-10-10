"""Jetons d'accès au backend Dédale, lus hors du dépôt dans `~/.config/dedale/`.

Le backend tire trois jetons au premier démarrage (analyste, passerelle, poste). La passerelle
et la boîte noire présentent le jeton `passerelle` : elles écrivent des événements et lisent
l'état d'une session, sans jamais décider. Les démos qui jouent l'analyste par l'API
présentent le jeton `analyste`. `DEDALE_JETONS` désigne un autre dossier (tests, banc isolé).

Un jeton absent donne un appel sans en-tête : le backend répond 401 et le module continue
sans consigne, comme lorsque le backend est muet.
"""

from __future__ import annotations

import os
from pathlib import Path


def dossier() -> Path:
    brut = os.environ.get("DEDALE_JETONS", "").strip()
    return Path(brut).expanduser() if brut else Path.home() / ".config" / "dedale"


def entete(role: str) -> dict[str, str]:
    """`{"Authorization": "Bearer …"}` pour ce rôle, ou {} si le jeton n'est pas lisible.
    Relu à chaque appel : un jeton créé après le lancement du module est pris aussitôt."""
    try:
        jeton = (dossier() / f"jeton-{role}").read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return {}
    return {"Authorization": f"Bearer {jeton}"} if jeton else {}
