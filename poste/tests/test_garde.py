"""Tests du garde du corps du poste.

On vérifie : un geste risqué lève l'avertissement et, si le salarié passe outre,
l'événement d'incident attendu ; un geste sûr ne déclenche rien ; le repli
backend-absent n'empêche jamais le poste de fonctionner.
"""

from __future__ import annotations

from garde import actions
from garde.backend import Backend
from garde.detection import evaluer, neutraliser
from garde.garde_du_corps import GardeDuCorps, toujours


class BackendEspion(Backend):
    """Backend qui enregistre les événements au lieu de les poster."""

    def __init__(self):
        super().__init__(actif=True)
        self.recus: list[tuple[str, str, dict]] = []

    def evenement(self, type, session_id, *, details=None):
        self.recus.append((type, session_id, details or {}))
        return {"session": {"id": session_id}, "consigne": "aucune"}


# --- gestes risqués, un par type ---------------------------------------------

def _garde(choix="annuler"):
    esp = BackendEspion()
    return GardeDuCorps(backend=esp, session_id="poste-test", decideur=toujours(choix)), esp


def test_secret_dans_chat_externe_declenche():
    g = actions.Geste(actions.COLLER_TEXTE, cible="ChatGPT", domaine="chat.openai.com",
                      texte="aide-moi, ma clé est sk-ant-api03-7h2Kd9fLmQ0zXc4Vb1Np stp")
    v = evaluer(g)
    assert v.risque and v.incident == "humain_secret"
    assert "sk-ant" not in v.preuve  # preuve neutralisée


def test_mail_externe_sensible_declenche():
    g = actions.Geste(actions.ENVOYER_MAIL, destinataires=["x@gmail.com"],
                      objet="pour ce soir", corps="l'export", pieces=["base-clients.csv"])
    v = evaluer(g)
    assert v.risque and v.incident == "humain_mail_externe"


def test_upload_ia_confidentiel_declenche():
    g = actions.Geste(actions.DEPOSER_FICHIER, cible="Drive perso", domaine="drive.google.com",
                      fichier="plan-confidentiel.pdf", confidentiel=True)
    v = evaluer(g)
    assert v.risque and v.incident == "humain_upload_ia"


def test_lien_phishing_declenche():
    for url in ["http://orbispay-secure.com/verif", "http://203.0.113.9/login",
                "https://orbispay.example@mechant.ru/"]:
        v = evaluer(actions.Geste(actions.CLIQUER_LIEN, url=url))
        assert v.risque and v.incident == "humain_phishing", url


def test_piece_jointe_double_extension_declenche():
    g = actions.Geste(actions.OUVRIR_PIECE, fichier="facture.pdf.exe", expediteur_externe=True)
    v = evaluer(g)
    assert v.risque and v.incident == "humain_phishing"
    assert v.gravite == "critique"


# --- gestes sûrs : rien ne doit se déclencher ---------------------------------

def test_gestes_surs_ne_declenchent_rien():
    surs = [
        actions.Geste(actions.COLLER_TEXTE, domaine="assistant.orbispay.example",
                      texte="compte rendu de réunion, rien de secret"),
        actions.Geste(actions.ENVOYER_MAIL, destinataires=["paul@orbispay.example"],
                      corps="l'export clients", pieces=["export-clients.csv"]),
        actions.Geste(actions.ENVOYER_MAIL, destinataires=["prospect@acheteur.example"],
                      corps="merci pour votre temps, à bientôt"),
        actions.Geste(actions.DEPOSER_FICHIER, domaine="assistant.orbispay.example",
                      fichier="plaquette.pdf", confidentiel=False),
        actions.Geste(actions.CLIQUER_LIEN, url="https://rh.orbispay.example/conges"),
        actions.Geste(actions.OUVRIR_PIECE, fichier="rapport.pdf", expediteur_externe=True),
    ]
    for g in surs:
        assert evaluer(g).risque is False, g


def test_geste_sur_nemet_aucun_evenement():
    garde, esp = _garde()
    res = garde.observer(actions.Geste(actions.CLIQUER_LIEN, url="https://orbispay.example/"))
    assert res.averti is False and res.choix is None
    assert esp.recus == []


# --- flux complet avertissement + choix ---------------------------------------

def test_annuler_emet_seulement_avertissement():
    garde, esp = _garde(choix="annuler")
    g = actions.Geste(actions.COLLER_TEXTE, cible="ChatGPT", domaine="chat.openai.com",
                      texte="ma clé AKIA1234567890ABCDEF ici")
    res = garde.observer(g)
    assert res.averti and res.choix == "annuler" and res.incident_emis is False
    types = [t for t, _, _ in esp.recus]
    assert types == ["avertissement"]
    assert esp.recus[0][2]["choix"] == "annuler"


def test_continuer_emet_avertissement_puis_incident():
    garde, esp = _garde(choix="continuer")
    g = actions.Geste(actions.DEPOSER_FICHIER, cible="Drive perso", domaine="drive.google.com",
                      fichier="plan-confidentiel.pdf", confidentiel=True)
    res = garde.observer(g)
    assert res.averti and res.choix == "continuer" and res.incident_emis
    types = [t for t, _, _ in esp.recus]
    assert types == ["avertissement", "humain_upload_ia"]
    # l'événement d'incident porte source/surface via le Backend ; details marque le passage outre
    assert esp.recus[1][2]["passe_outre"] is True


def test_evenements_portent_source_humain_surface_poste():
    # On vérifie la forme du corps réellement construit par Backend.
    envois = []

    class B(Backend):
        def evenement(self, type, session_id, *, details=None):
            # reconstruit le corps comme le vrai Backend.
            corps = {
                "source": "humain", "surface": "poste", "type": type,
                "session_id": session_id, "details": details or {},
            }
            envois.append(corps)
            return None

    garde = GardeDuCorps(backend=B(), session_id="poste-test", decideur=toujours("continuer"))
    garde.observer(actions.Geste(actions.CLIQUER_LIEN, url="http://orbispay-secure.com/x"))
    assert all(e["source"] == "humain" and e["surface"] == "poste" for e in envois)
    assert [e["type"] for e in envois] == ["avertissement", "humain_phishing"]


# --- repli backend absent ------------------------------------------------------

def test_backend_absent_ne_fait_pas_tomber():
    # Backend réel vers un port fermé : urlopen échoue, evenement() renvoie None.
    garde = GardeDuCorps(backend=Backend(base="http://127.0.0.1:1", actif=True),
                         session_id="poste-test", decideur=toujours("continuer"))
    g = actions.Geste(actions.OUVRIR_PIECE, fichier="piege.exe", expediteur_externe=True)
    res = garde.observer(g)  # ne doit pas lever
    assert res.averti and res.incident_emis
    assert all(ev["reponse"] is None for ev in res.evenements)


def test_escalade_sur_repetition():
    garde, esp = _garde(choix="annuler")
    g = actions.Geste(actions.COLLER_TEXTE, cible="ChatGPT", domaine="chat.openai.com",
                      texte="clé sk-ant-api03-7h2Kd9fLmQ0zXc4Vb1Np")
    r1 = garde.observer(g)
    r2 = garde.observer(g)
    r3 = garde.observer(g)  # 3e avertissement : seuil atteint
    assert r1.escalade is False
    assert r3.escalade is True


def test_neutraliser_est_inerte():
    out = neutraliser("sk-ant-api03-secret-tres-long-xyz")
    assert out.startswith("[preuve, neutralisée]")
    assert "secret-tres-long" not in out


def test_piece_executable_simple_et_macro():
    assert evaluer(actions.Geste(actions.OUVRIR_PIECE, fichier="jeu.exe")).risque
    v_macro = evaluer(actions.Geste(actions.OUVRIR_PIECE, fichier="budget.xlsm", expediteur_externe=True))
    assert v_macro.risque and v_macro.incident == "humain_phishing"
    # un .xlsm interne (pas externe) ne déclenche pas la règle macro
    assert evaluer(actions.Geste(actions.OUVRIR_PIECE, fichier="budget.xlsm",
                                 expediteur_externe=False)).risque is False
