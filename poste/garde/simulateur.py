"""La journée d'un salarié d'Orbis Pay (Camille), gestes sûrs et gestes risqués.

Chaque geste passe par le garde du corps. Les gestes sûrs ne déclenchent rien ;
les gestes risqués lèvent une pop-up, et selon le choix joué, l'incident part ou
non. À la fin, une page HTML filmable est écrite dans poste/demo/popup.html.

Lancement : python -m garde.simulateur [--backend URL] [--choix mix|continuer|annuler]
            [--html CHEMIN] [--sans-reseau]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import actions
from .backend import Backend
from .garde_du_corps import GardeDuCorps
from .popup import page_html, rendu_terminal


def journee() -> list[actions.Geste]:
    """Les gestes de la journée. Sûrs et risqués mêlés, comme en vrai."""
    return [
        # --- gestes SÛRS : rien ne doit se déclencher ---
        actions.Geste(actions.COLLER_TEXTE, "Camille colle un compte rendu dans le chat interne",
                      cible="Chat interne", domaine="assistant.orbispay.example",
                      texte="Compte rendu de la réunion de ce matin : trois points à suivre."),
        actions.Geste(actions.ENVOYER_MAIL, "Camille envoie la base clients à un collègue interne",
                      destinataires=["paul@orbispay.example"], objet="Export clients du mois",
                      corps="Voici l'export clients demandé.", pieces=["export-clients.csv"]),
        actions.Geste(actions.ENVOYER_MAIL, "Camille répond à un prospect externe, sans données sensibles",
                      destinataires=["prospect@acheteur.example"], objet="Suite à notre échange",
                      corps="Merci pour votre temps, je reviens vers vous la semaine prochaine."),
        actions.Geste(actions.DEPOSER_FICHIER, "Camille dépose une plaquette publique sur l'assistant validé",
                      cible="Assistant Orbis", domaine="assistant.orbispay.example",
                      fichier="plaquette-commerciale.pdf", confidentiel=False),
        actions.Geste(actions.CLIQUER_LIEN, "Camille ouvre le portail RH interne",
                      url="https://rh.orbispay.example/conges"),

        # --- gestes RISQUÉS : un par type d'incident ---
        actions.Geste(actions.COLLER_TEXTE, "Camille colle une clé API dans ChatGPT pour « debugger »",
                      cible="ChatGPT", domaine="chat.openai.com",
                      texte="peux-tu analyser cette erreur ? ma clé est sk-ant-api03-7h2Kd9fLmQ0zXc4Vb1Np"),
        actions.Geste(actions.ENVOYER_MAIL, "Camille envoie l'export clients à son adresse Gmail perso",
                      destinataires=["camille.perso@gmail.com"], objet="pour bosser ce soir",
                      corps="je m'envoie le fichier clients pour avancer à la maison",
                      pieces=["base-clients-complete.csv"]),
        actions.Geste(actions.DEPOSER_FICHIER, "Camille dépose le plan stratégique sur un Drive perso",
                      cible="Google Drive perso", domaine="drive.google.com",
                      fichier="plan-strategique-2027-confidentiel.pdf", confidentiel=True),
        actions.Geste(actions.CLIQUER_LIEN, "Camille clique le lien « vérifiez votre compte » d'un mail",
                      url="http://orbispay-secure.com/verif?compte=camille"),
        actions.Geste(actions.OUVRIR_PIECE, "Camille ouvre une pièce jointe d'un expéditeur inconnu",
                      fichier="facture_impayee.pdf.exe", expediteur_externe=True),
    ]


def _decideur_mix():
    """Sur les gestes risqués, le salarié passe outre une fois sur deux."""
    compteur = {"n": 0}

    def _d(_g, _v):
        compteur["n"] += 1
        return "continuer" if compteur["n"] % 2 == 1 else "annuler"
    return _d


def lancer(backend: Backend, choix: str, chemin_html: str) -> dict:
    if choix == "mix":
        decideur = _decideur_mix()
    else:
        from .garde_du_corps import toujours
        decideur = toujours(choix)

    garde = GardeDuCorps(backend=backend, session_id="poste-camille-001", decideur=decideur)
    cartes = []
    stats = {"total": 0, "surs": 0, "avertis": 0, "incidents": 0, "evenements": 0}

    for geste in journee():
        stats["total"] += 1
        res = garde.observer(geste)
        if not res.averti:
            stats["surs"] += 1
            print(f"  ✓ sûr       — {geste.description}")
            continue
        stats["avertis"] += 1
        stats["evenements"] += len(res.evenements)
        if res.incident_emis:
            stats["incidents"] += 1
        print("\n" + rendu_terminal(res.verdict))
        marque = "→ passé outre, INCIDENT remonté" if res.choix == "continuer" else "→ annulé, incident évité"
        esc = "  [escaladé au SOC]" if res.escalade else ""
        print(f"  choix du salarié : {res.choix}  {marque}{esc}\n")
        cartes.append((res.verdict, res.choix))

    Path(chemin_html).parent.mkdir(parents=True, exist_ok=True)
    Path(chemin_html).write_text(page_html(cartes), encoding="utf-8")
    print(f"\nRésumé : {stats['total']} gestes · {stats['surs']} sûrs (0 pop-up) · "
          f"{stats['avertis']} avertissements · {stats['incidents']} incidents · "
          f"{stats['evenements']} événements émis.")
    print(f"Pop-up HTML filmable : {chemin_html}")
    return stats


def main(argv=None) -> int:
    racine = Path(__file__).resolve().parent.parent
    p = argparse.ArgumentParser(description="Garde du corps du poste — journée simulée")
    p.add_argument("--backend", default=os.environ.get("DEDALE_BACKEND", "http://127.0.0.1:8700"))
    p.add_argument("--choix", choices=["mix", "continuer", "annuler"], default="mix")
    p.add_argument("--html", default=str(racine / "demo" / "popup.html"))
    p.add_argument("--sans-reseau", action="store_true",
                   help="ne poste rien au backend (démo hors ligne)")
    args = p.parse_args(argv)

    backend = Backend(base=args.backend, actif=not args.sans_reseau)
    etat = "hors ligne" if args.sans_reseau else args.backend
    print(f"Garde du corps du poste — backend : {etat}\n")
    lancer(backend, args.choix, args.html)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
