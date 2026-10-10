"""Le geste du salarié : ce qu'il s'apprête à faire sur son poste.

Un seul type porte toutes les natures de geste, pour que le garde du corps les
traite dans une boucle unique. Les champs non pertinents à une nature restent
vides. Un geste est une donnée observée, jamais une instruction à exécuter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Natures reconnues. Les deux premières sont les gestes vedettes du produit :
# un mail frauduleux qu'on ouvre, un lien piégé qu'on clique en naviguant.
OUVRIR_MAIL = "ouvrir_mail"         # ouvrir / lire un mail reçu (détection au moment de la lecture)
CLIQUER_LIEN = "cliquer_lien"       # cliquer un lien en naviguant sur le web
COLLER_TEXTE = "coller_texte"       # coller / saisir du texte dans un chat, un site, une IA
ENVOYER_MAIL = "envoyer_mail"       # envoyer un mail
DEPOSER_FICHIER = "deposer_fichier"  # déposer un fichier sur une IA / un cloud
OUVRIR_PIECE = "ouvrir_piece"       # ouvrir une pièce jointe


@dataclass
class Geste:
    nature: str
    description: str = ""          # libellé lisible, pour la narration et la pop-up

    # coller_texte, deposer_fichier, cliquer_lien : où ça va.
    cible: str = ""               # « ChatGPT », « formulaire web », « Google Drive perso »…
    domaine: str = ""             # domaine joint, pour juger interne / externe / autorisé
    texte: str = ""               # contenu collé / saisi

    # envoyer_mail, ouvrir_mail
    destinataires: list[str] = field(default_factory=list)
    objet: str = ""
    corps: str = ""
    pieces: list[str] = field(default_factory=list)

    # ouvrir_mail : le mail REÇU que Camille ouvre. L'expéditeur et le lien du
    # corps sont les indices que le garde du corps lit au moment de la lecture.
    expediteur: str = ""           # adresse de l'expéditeur (From)
    expediteur_affiche: str = ""   # nom affiché, ex. « Orbis Pay Sécurité »
    lien: str = ""                 # lien présent dans le corps du mail

    # deposer_fichier, ouvrir_piece
    fichier: str = ""
    confidentiel: bool = False
    expediteur_externe: bool = False  # pour une pièce jointe : vient d'un expéditeur hors entreprise

    # cliquer_lien
    url: str = ""
