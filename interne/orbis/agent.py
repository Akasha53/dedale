"""Agent interne d'Orbis Pay : boucle qui enchaîne cerveau -> outils, le tout à travers
la passerelle (journalisation + contrôle). L'agent ne touche jamais le backend ni les
outils directement : tout passe par la passerelle.
"""

from __future__ import annotations

from . import droits, mcp
from .boite_noire import BoiteNoire
from .canaris import inventaire_backend, jetons_secrets
from .cerveau import choisir_cerveau
from .outils import Outils
from .passerelle import AgentCoupe, AgentHorsScope, Passerelle


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
        tache: "droits.Tache | str | None" = None,
        surface_entree: str = "mail",
    ):
        self.session_id = session_id
        # Surface d'où vient la demande de l'agent (mail par défaut ; « chatbot » pour V3a).
        self.surface_entree = surface_entree
        self.cerveau = cerveau or choisir_cerveau(temperament=temperament)
        self.outils = outils or Outils()
        self.boite = boite or BoiteNoire()

        # Moindre privilège : un jeton limité à la tâche, le cas échéant.
        self.tache = droits.resoudre_tache(tache) if tache is not None else None
        jeton_tache = droits.emettre_jeton(self.tache) if self.tache is not None else None

        if passerelle is not None:
            self.passerelle = passerelle
            # Attache le jeton de tâche à une passerelle fournie sans le sien (sans écraser).
            if jeton_tache is not None and self.passerelle.jeton_tache is None:
                self.passerelle.jeton_tache = jeton_tache
                self.passerelle.scopes_accordes = list(droits.SCOPES_ACCORDES)
        else:
            self.passerelle = Passerelle(
                session_id,
                jetons_secrets(),
                self.boite,
                jeton_tache=jeton_tache,
                scopes_accordes=droits.SCOPES_ACCORDES if jeton_tache is not None else None,
            )

        self._table = {
            "lire_mail": self.outils.lire_mail,
            "chercher_document": self.outils.chercher_document,
            "resumer": self.outils.resumer,
            "envoyer_rapport": self.outils.envoyer_rapport,
            "executer_paiement": self.outils.executer_paiement,
            "lire_coffre": self.outils.lire_coffre,
            "exporter_contacts": self.outils.exporter_contacts,
            # V1 (appels) et V4 (mémoire long terme).
            "chercher_appel": self.outils.chercher_appel,
            "lire_memoire": self.outils.lire_memoire,
            "memoriser": self.outils.memoriser,
        }
        # Outils MCP (implémentations bénignes + descripteurs portant la description).
        self._mcp = {o.nom: o for o in mcp.CATALOGUE}
        for nom, fonction in mcp.IMPLEM.items():
            self._table[nom] = fonction

    def executer(self, demande: str, max_pas: int = 8) -> dict:
        self.passerelle.entree_agent(demande, surface=self.surface_entree)
        historique: list[dict] = []
        reponse: str | None = None
        coupe = False
        hors_scope = False

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

            descripteur = self._mcp.get(nom)
            # L'intention annoncée n'est transmise que si le cerveau en donne une.
            options = {"intention": action["intention"]} if action.get("intention") else {}
            try:
                resultat = self.passerelle.appel_outil(nom, params, fonction, descripteur=descripteur,
                                                       **options)
            except AgentCoupe:
                coupe = True
                break
            except AgentHorsScope:
                # Action hors du jeton de tâche : bloquée, jeton révoqué, agent arrêté.
                hors_scope = True
                break
            historique.append({"outil": nom, "resultat": resultat})
        else:
            # max_pas atteint sans réponse finale.
            pass

        return {
            "reponse": reponse,
            "coupe": coupe,
            "hors_scope": hors_scope,
            "jeton_revoque": self.passerelle.jeton_revoque,
            "canaris_touches": list(self.passerelle.canaris_touches),
            "incident": self.passerelle.incident,
            "etat": self.passerelle.etat,
            "scopes_utilises": list(self.passerelle.scopes_utilises),
            "tentatives_hors_scope": list(self.passerelle.tentatives_hors_scope),
            "historique": historique,
            "rapports_envoyes": self.outils.rapports_envoyes,
            "journal": self.passerelle.journal,
            # Mode protégé (scénario jury) : vides ou None hors de ce mode.
            "appels_liberes": list(getattr(self.passerelle, "appels_liberes", [])),
            "appels_refuses": list(getattr(self.passerelle, "appels_refuses", [])),
            "boite_noire": (list(self.passerelle.enregistreur.maillons)
                            if getattr(self.passerelle, "enregistreur", None) else None),
            "chronos": (list(self.passerelle.enregistreur.chronos)
                        if getattr(self.passerelle, "enregistreur", None) else None),
        }
