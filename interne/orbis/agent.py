"""Agent interne d'Orbis Pay : boucle qui enchaîne cerveau -> outils, le tout à travers
la passerelle (journalisation + contrôle). L'agent ne touche jamais le backend ni les
outils directement : tout passe par la passerelle.
"""

from __future__ import annotations

from .boite_noire import BoiteNoire
from .canaris import inventaire_backend, jetons_secrets
from .cerveau import choisir_cerveau
from .outils import Outils
from .passerelle import AgentCoupe, Passerelle


def enregistrer_canaris(boite: BoiteNoire | None = None) -> bool:
    """POST /api/leurres au démarrage. À appeler une fois au lancement du module."""
    boite = boite or BoiteNoire()
    return boite.enregistrer_leurres(inventaire_backend())


class AgentInterne:
    def __init__(
        self,
        session_id: str,
        cerveau=None,
        *,
        outils: Outils | None = None,
        boite: BoiteNoire | None = None,
        passerelle: Passerelle | None = None,
        temperament: str = "prudent",
    ):
        self.session_id = session_id
        self.cerveau = cerveau or choisir_cerveau(temperament=temperament)
        self.outils = outils or Outils()
        self.boite = boite or BoiteNoire()
        self.passerelle = passerelle or Passerelle(session_id, jetons_secrets(), self.boite)
        self._table = {
            "lire_mail": self.outils.lire_mail,
            "chercher_document": self.outils.chercher_document,
            "resumer": self.outils.resumer,
            "envoyer_rapport": self.outils.envoyer_rapport,
        }

    def executer(self, demande: str, max_pas: int = 8) -> dict:
        self.passerelle.entree_agent(demande)
        historique: list[dict] = []
        reponse: str | None = None
        coupe = False

        for _ in range(max_pas):
            action = self.cerveau.prochaine_action(demande, historique)

            if "reponse_finale" in action:
                try:
                    reponse = self.passerelle.sortie_agent(action["reponse_finale"])
                except AgentCoupe:
                    coupe = True
                break

            nom = action.get("outil")
            params = action.get("parametres") or {}
            fonction = self._table.get(nom)
            if fonction is None:
                historique.append({"outil": nom, "resultat": {"erreur": "outil inconnu"}})
                continue

            try:
                resultat = self.passerelle.appel_outil(nom, params, fonction)
            except AgentCoupe:
                coupe = True
                break
            historique.append({"outil": nom, "resultat": resultat})
        else:
            # max_pas atteint sans réponse finale.
            pass

        return {
            "reponse": reponse,
            "coupe": coupe,
            "jeton_revoque": self.passerelle.jeton_revoque,
            "canaris_touches": list(self.passerelle.canaris_touches),
            "incident": self.passerelle.incident,
            "etat": self.passerelle.etat,
            "historique": historique,
            "rapports_envoyes": self.outils.rapports_envoyes,
            "journal": self.passerelle.journal,
        }
