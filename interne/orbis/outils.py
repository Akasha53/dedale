"""Outils de l'agent interne : lire_mail, chercher_document, resumer, envoyer_rapport.

Implémentations « nues ». La passerelle les enveloppe (journalisation + contrôle).
Toutes les données sont synthétiques et locales.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config


class Outils:
    def __init__(
        self,
        fichier_mails: Path | None = None,
        dossier_documents: Path | None = None,
    ):
        self.fichier_mails = fichier_mails or config.FICHIER_MAILS
        self.dossier_documents = dossier_documents or config.DOSSIER_DOCUMENTS
        # Boîte d'envoi locale : les rapports « envoyés » atterrissent ici (rien ne sort
        # de la machine, tout est fictif).
        self.rapports_envoyes: list[dict] = []
        # Journal local des outils « privilégiés » (virements, export contacts). Fictif.
        self.paiements: list[dict] = []
        self.exports_contacts: list[dict] = []

    # --- lecture de la boîte mail -------------------------------------------------
    def lire_mail(self, depuis: str | None = None) -> list[dict]:
        """Renvoie les mails de la boîte (optionnellement filtrés par date >= depuis)."""
        mails = json.loads(Path(self.fichier_mails).read_text(encoding="utf-8"))
        if depuis:
            mails = [m for m in mails if m.get("date", "") >= depuis]
        return mails

    # --- recherche de documents internes ------------------------------------------
    def chercher_document(self, requete: str) -> list[dict]:
        """Cherche un document dont le nom ou le contenu contient la requête."""
        requete_bas = (requete or "").lower()
        resultats: list[dict] = []
        for chemin in sorted(Path(self.dossier_documents).glob("*.md")):
            texte = chemin.read_text(encoding="utf-8")
            if not requete_bas or requete_bas in chemin.stem.lower() or requete_bas in texte.lower():
                resultats.append({"nom": chemin.stem, "chemin": chemin.name, "contenu": texte})
        return resultats

    # --- résumé -------------------------------------------------------------------
    def resumer(self, textes: list[str] | str) -> str:
        """Résumé simple et local (pas d'appel LLM : déterministe pour la démo/tests)."""
        if isinstance(textes, str):
            textes = [textes]
        lignes = []
        for t in textes:
            t = " ".join((t or "").split())
            lignes.append(t[:200] + ("…" if len(t) > 200 else ""))
        return "\n".join(f"- {l}" for l in lignes if l)

    # --- envoi de rapport ---------------------------------------------------------
    def envoyer_rapport(self, destinataire: str, contenu: str) -> dict:
        """« Envoie » un rapport (écrit dans la boîte d'envoi locale). Fictif."""
        rapport = {"destinataire": destinataire, "contenu": contenu}
        self.rapports_envoyes.append(rapport)
        return {"statut": "envoye", "destinataire": destinataire, "taille": len(contenu)}

    # --- outils « privilégiés » (droits larges) -----------------------------------
    def executer_paiement(self, montant: float, beneficiaire: str) -> dict:
        """« Exécute » un virement (scope paiement:executer). Simulé, local, fictif."""
        op = {"montant": montant, "beneficiaire": beneficiaire, "statut": "simule"}
        self.paiements.append(op)
        return dict(op)

    def exporter_contacts(self) -> dict:
        """« Exporte » la base contacts (scope contact:exporter). Synthétique, local."""
        contacts = [
            {"nom": "Camille Rossi", "mail": "camille.rossi@orbispay.example"},
            {"nom": "Jean Moreau", "mail": "jean.moreau@orbispay.example"},
        ]
        self.exports_contacts.append({"n": len(contacts)})
        return {"statut": "exporte", "contacts": contacts, "taille": len(contacts)}
