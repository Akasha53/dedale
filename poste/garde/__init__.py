"""poste/ — le garde du corps du poste du salarié (Dédale, avenant « humain »).

Un agent local observe une action risquée AVANT qu'elle n'aboutisse, décide si
elle est dangereuse selon des règles claires, avertit le salarié et le laisse
choisir (continuer / annuler). Chaque avertissement et chaque choix part au
backend (source `humain`, surface `poste`). Rien d'autre ne quitte le poste.
"""

from .actions import Geste
from .detection import Verdict, evaluer
from .garde_du_corps import GardeDuCorps, Resultat

__all__ = ["Geste", "Verdict", "evaluer", "GardeDuCorps", "Resultat"]
