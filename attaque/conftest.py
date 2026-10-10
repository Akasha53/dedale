"""Rend `banc` et `campagne` importables quand pytest tourne depuis attaque/."""
import sys
from pathlib import Path

racine = str(Path(__file__).parent)
if racine not in sys.path:
    sys.path.insert(0, racine)
