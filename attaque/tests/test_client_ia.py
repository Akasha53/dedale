"""Client IA : extraction des pistes, simulateur déterministe, réponse contre-injection."""

from __future__ import annotations

from banc import evenement as ev
from banc.backend import Backend
from banc.client_ia import ClientIA, _extraire_pistes
from banc.monde import Monde
from banc.surface import (SurfaceLocale, directives_cachees, _CONNEXION, _ROBOTS,
                          _AI_PLUGIN)


def test_directives_cachees_sur_les_pages_de_la_surface():
    assert any(d["genre"] == "outil" for d in directives_cachees(_CONNEXION))
    assert any(d["genre"] == "route" and d["chemin"] == "/console-partenaire"
               for d in directives_cachees(_ROBOTS))
    assert any(d["genre"] == "outil" and d["outil"] == "exporter_clients"
               for d in directives_cachees(_AI_PLUGIN))


def test_page_normale_sans_directive():
    assert directives_cachees(SurfaceLocale().page("/tarifs").corps) == []


def test_simulateur_suit_toutes_les_pistes():
    client = ClientIA("simulateur")
    pistes = client.pistes_a_suivre(_ROBOTS)
    assert pistes and pistes[0]["chemin"] == "/console-partenaire"


def test_extraire_pistes_tolere_du_bruit_autour_du_json():
    texte = 'Voici ma réponse :\n{"pistes": [{"genre": "route", "chemin": "/x"}]} merci'
    assert _extraire_pistes(texte) == [{"genre": "route", "chemin": "/x"}]


def test_extraire_pistes_sur_sortie_illisible():
    assert _extraire_pistes("pas de json ici") == []


class _BackendContreInjection(Backend):
    """Backend simulé qui ordonne une contre-injection sur la 1re requête."""

    def __init__(self):
        super().__init__("http://127.0.0.1:9")
        self.appels = 0

    def emettre(self, evenement):
        self.appels += 1
        consigne = "contre_injection" if self.appels == 1 else "aucune"
        return {"session": {"id": evenement["session_id"], "classement": "agent_ia",
                            "score": 0.9, "etat": "active"}, "consigne": consigne}


def test_agent_avoue_son_objectif_sur_contre_injection():
    from banc import trafic
    import random
    monde = Monde("autonome", SurfaceLocale(), _BackendContreInjection())
    sid = trafic.agent_ia(monde, 1, random.Random("ci"), client=ClientIA("simulateur"))
    sorties = [e for e in monde.manifeste[sid] if e["type"] == "sortie_agent"]
    assert sorties, "l'agent doit répondre à la contre-injection"
    assert "objectif_avoue" in sorties[0]["details"]
