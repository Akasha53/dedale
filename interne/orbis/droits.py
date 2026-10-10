"""Moindre privilège pour l'agent interne : droits accordés vs droits nécessaires.

L'agent d'Orbis Pay dispose d'un ensemble de droits (scopes) LARGE — c'est l'argument
du pitch : « il a accès à toute la vie de l'entreprise ». Pour une tâche donnée, seul un
sous-ensemble est réellement nécessaire. On matérialise un JETON limité à la tâche : il ne
porte que les scopes utiles. Toute action hors de ce jeton est une violation du moindre
privilège (OWASP Agentic ASI03), bloquée et signalée.

Ce module ne fait qu'émettre/révoquer un jeton et décrire des droits ; il n'exécute rien.
Le blocage effectif vit dans la passerelle, qui réutilise la révocation de jeton existante.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

# Libellés lisibles par l'analyste (repris tels quels dans la console).
LIBELLES = {
    "mail:lire": "Lire la boîte mail",
    "mail:envoyer": "Envoyer des mails",
    "document:lire": "Lire les documents internes",
    "coffre:lire": "Lire le coffre de clés d'API",
    "rapport:envoyer": "Envoyer un rapport interne",
    "paiement:executer": "Exécuter un virement",
    "contact:exporter": "Exporter la base contacts",
    "outil:mcp": "Appeler les outils MCP",
    "resume:local": "Résumer en local",
    "appel:lire": "Lire les transcriptions d'appels",
    "memoire:lire": "Lire la mémoire long terme",
    "memoire:ecrire": "Écrire dans la mémoire long terme",
}

# Droits ACCORDÉS au compte de l'agent (larges, hérités du périmètre Orbis Pay).
SCOPES_ACCORDES = [
    "mail:lire",
    "mail:envoyer",
    "document:lire",
    "coffre:lire",
    "rapport:envoyer",
    "paiement:executer",
    "contact:exporter",
    "outil:mcp",
    "resume:local",
    "appel:lire",
    "memoire:lire",
    "memoire:ecrire",
]

# Scope requis par chaque outil (natifs + MCP). Un outil absent n'exige aucun droit.
SCOPE_PAR_OUTIL = {
    "lire_mail": "mail:lire",
    "chercher_document": "document:lire",
    "resumer": "resume:local",
    "envoyer_rapport": "rapport:envoyer",
    "executer_paiement": "paiement:executer",
    "exporter_contacts": "contact:exporter",
    # Outils MCP :
    "convertir_montant": "outil:mcp",
    "verifier_conformite": "outil:mcp",
    # Appels (V1), mémoire long terme (V4) :
    "chercher_appel": "appel:lire",
    "lire_memoire": "memoire:lire",
    "memoriser": "memoire:ecrire",
    # Scénario jury : lecture d'une entrée du coffre de clés.
    "lire_coffre": "coffre:lire",
}


def scope_outil(nom: str) -> str | None:
    return SCOPE_PAR_OUTIL.get(nom)


def libelle(code: str) -> str:
    return LIBELLES.get(code, code)


def avec_libelles(codes) -> list[dict]:
    """Rend une liste de scopes au format console [{code, libelle}, …]."""
    return [{"code": c, "libelle": libelle(c)} for c in codes]


@dataclass(frozen=True)
class Tache:
    id: str
    libelle: str
    scopes_necessaires: tuple[str, ...]


TACHES: dict[str, Tache] = {
    "resume_mails": Tache(
        "resume_mails",
        "Résumer les mails de la semaine",
        ("mail:lire", "resume:local", "rapport:envoyer"),
    ),
    "conversion_facture": Tache(
        "conversion_facture",
        "Convertir le montant d'une facture",
        ("mail:lire", "outil:mcp", "rapport:envoyer"),
    ),
    "verif_conformite": Tache(
        "verif_conformite",
        "Vérification de conformité du compte",
        ("mail:lire", "outil:mcp", "document:lire", "rapport:envoyer"),
    ),
    "triage_appels": Tache(
        "triage_appels",
        "Trier et résumer les transcriptions d'appels",
        ("appel:lire", "resume:local", "rapport:envoyer"),
    ),
    "revue_hebdo": Tache(
        "revue_hebdo",
        "Revue hebdomadaire (mémoire + rapport)",
        ("memoire:lire", "mail:lire", "resume:local", "rapport:envoyer"),
    ),
    "rapport_paiements": Tache(
        "rapport_paiements",
        "Préparer le rapport mensuel des paiements fournisseurs",
        ("document:lire", "resume:local", "rapport:envoyer"),
    ),
    "apprentissage_prefs": Tache(
        "apprentissage_prefs",
        "Enregistrer les préférences d'un échange",
        ("appel:lire", "memoire:ecrire"),
    ),
}


_seq = itertools.count(1)


@dataclass
class Jeton:
    """Jeton limité à une tâche : il ne porte que les scopes utiles."""

    id: str
    tache: str
    scopes: tuple[str, ...]
    revoque: bool = False

    def porte(self, scope: str) -> bool:
        return (not self.revoque) and scope in self.scopes

    def revoquer(self) -> None:
        self.revoque = True


def resoudre_tache(tache: "Tache | str") -> Tache:
    return tache if isinstance(tache, Tache) else TACHES[tache]


def emettre_jeton(tache: "Tache | str") -> Jeton:
    t = resoudre_tache(tache)
    return Jeton(id=f"JT-{next(_seq):04d}", tache=t.id, scopes=tuple(t.scopes_necessaires))


def surplus(accordes, necessaires) -> list[str]:
    """Scopes détenus mais inutiles à la tâche : le cœur de l'argument moindre privilège."""
    nec = set(necessaires)
    return [c for c in accordes if c not in nec]
