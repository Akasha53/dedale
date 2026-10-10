"""Le garde du corps : orchestration d'un geste, de la détection à l'événement.

1. observer le geste et le soumettre aux règles ;
2. si rien n'est risqué, laisser passer sans bruit (un geste sûr ne déclenche rien) ;
3. sinon, afficher l'avertissement et recueillir le choix du salarié ;
4. émettre l'événement `avertissement` (avec le choix) au backend ;
5. si le salarié passe outre (`continuer`), émettre l'événement d'incident.

Non bloquant : il prévient, laisse choisir. Escalade au SOC (details.escalade)
si la gravité est critique ou si les avertissements se répètent dans la session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import actions, config
from .backend import Backend
from .detection import Verdict, evaluer

# Un décideur reçoit (geste, verdict) et répond "continuer" ou "annuler".
Decideur = Callable[[actions.Geste, Verdict], str]


def toujours(choix: str) -> Decideur:
    """Décideur constant, pratique pour les tests et les démos scriptées."""
    def _d(_g: actions.Geste, _v: Verdict) -> str:
        return choix
    return _d


@dataclass
class Resultat:
    geste: actions.Geste
    verdict: Verdict
    averti: bool = False              # une pop-up a-t-elle été montrée ?
    choix: str | None = None          # "continuer" | "annuler" | None (geste sûr)
    escalade: bool = False
    incident_emis: bool = False
    evenements: list[dict] = field(default_factory=list)  # ce qui a été envoyé


class GardeDuCorps:
    def __init__(
        self,
        backend: Backend | None = None,
        session_id: str = "poste-salarie",
        decideur: Decideur | None = None,
    ):
        self.backend = backend or Backend()
        self.session_id = session_id
        self.decideur = decideur or toujours("annuler")
        self._avertissements = 0

    def _escalade(self, verdict: Verdict) -> bool:
        return verdict.gravite == "critique" or self._avertissements >= config.SEUIL_ESCALADE

    def _charge_commune(self, verdict: Verdict, escalade: bool) -> dict:
        # Données inertes : la preuve est déjà neutralisée par la détection.
        # `categorie` est la forme courte attendue par la console (secret,
        # mail_externe, upload_ia, phishing) ; on la dérive de l'incident.
        categorie = verdict.incident.removeprefix("humain_") if verdict.incident else None
        return {
            "categorie": categorie,
            "incident": verdict.incident,
            "regle": verdict.regle,
            "gravite": verdict.gravite,
            "titre": verdict.titre,
            "explication": verdict.explication,
            "preuve": verdict.preuve,
            "escalade": escalade,
            **verdict.details,
        }

    def observer(self, geste: actions.Geste, decideur: Decideur | None = None) -> Resultat:
        """Traite un geste de bout en bout. decideur surclasse celui du garde."""
        verdict = evaluer(geste)
        res = Resultat(geste=geste, verdict=verdict)

        if not verdict.risque:
            return res  # geste sûr : rien ne part, aucune pop-up

        self._avertissements += 1
        res.averti = True
        choix = (decideur or self.decideur)(geste, verdict)
        choix = "continuer" if choix == "continuer" else "annuler"
        res.choix = choix
        res.escalade = self._escalade(verdict)

        charge = self._charge_commune(verdict, res.escalade)
        charge["choix"] = choix
        rep = self.backend.evenement("avertissement", self.session_id, details=charge)
        res.evenements.append({"type": "avertissement", "details": charge, "reponse": rep})

        if choix == "continuer":
            # Le salarié passe outre : l'incident se produit.
            charge_inc = self._charge_commune(verdict, res.escalade)
            charge_inc["passe_outre"] = True
            rep2 = self.backend.evenement(verdict.incident, self.session_id, details=charge_inc)
            res.evenements.append({"type": verdict.incident, "details": charge_inc, "reponse": rep2})
            res.incident_emis = True

        return res
