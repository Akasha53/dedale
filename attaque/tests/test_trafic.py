"""Chaque type de trafic produit les événements attendus, bien étiquetés.

Tourne en mode autonome avec un backend injoignable : les générateurs produisent
leurs événements dans le manifeste sans dépendre d'un service externe.
"""

from __future__ import annotations

import random

import pytest

from banc import evenement as ev
from banc.backend import Backend
from banc.client_ia import ClientIA
from banc.monde import Monde
from banc.surface import SurfaceLocale
from banc import trafic

CHAMPS = {"horodatage", "source", "surface", "type", "session_id", "leurre_id",
          "ip", "user_agent", "methode", "chemin", "outil", "details"}


def monde_hors_ligne() -> Monde:
    # port volontairement mort : emettre() renvoie un repli neutre, rien ne bloque
    return Monde("autonome", SurfaceLocale(), Backend("http://127.0.0.1:9", delai=0.2))


def evenements(monde: Monde, sid: str) -> list[dict]:
    return monde.manifeste[sid]


def test_schema_et_etiquetage_complets():
    monde = monde_hors_ligne()
    sid = trafic.agent_ia(monde, 1, random.Random("x"), client=ClientIA("simulateur"))
    for e in evenements(monde, sid):
        assert set(e) == CHAMPS, "un événement ne respecte pas le schéma du contrat"
        assert e["details"]["verite_terrain"] == ev.AGENT_IA
        assert e["session_id"] == sid


def test_humain_ne_touche_aucun_leurre():
    monde = monde_hors_ligne()
    sid = trafic.humain(monde, 1, random.Random("h"))
    evs = evenements(monde, sid)
    assert sid.startswith("banc-humain-")
    assert all(e["type"] == "requete" for e in evs)
    assert not [e for e in evs if e["type"] == "leurre_touche"]
    assert all(e["user_agent"] == trafic.NAVIGATEUR for e in evs)
    assert all(e["details"]["verite_terrain"] == ev.HUMAIN for e in evs)


def test_script_rapide_et_sans_leurre():
    monde = monde_hors_ligne()
    sid = trafic.script(monde, 1, random.Random("s"))
    evs = evenements(monde, sid)
    assert sid.startswith("banc-script-")
    assert len(evs) == len(trafic.MOTS_SCANNER)
    assert not [e for e in evs if e["type"] == "leurre_touche"]
    assert all(e["user_agent"] == trafic.SCRIPT_UA for e in evs)
    # délais courts et réguliers (hors première requête)
    delais = [e["details"]["delai_avant_s"] for e in evs[1:]]
    assert max(delais) < 0.2


def test_agent_ia_suit_les_leurres():
    monde = monde_hors_ligne()
    sid = trafic.agent_ia(monde, 1, random.Random("a"), client=ClientIA("simulateur"))
    evs = evenements(monde, sid)
    touches = [e for e in evs if e["type"] == "leurre_touche"]
    distincts = {e["leurre_id"] for e in touches}
    assert sid.startswith("banc-agentia-")
    assert touches, "l'agent IA doit toucher au moins un leurre"
    # route cachée, consigne cachée et faux outil MCP
    assert {"L-0001", "L-0002", "L-0003"} <= distincts
    assert any(e["type"] == "appel_outil" and e["outil"] == "exporter_clients"
               for e in evs)
    assert all(e["details"]["verite_terrain"] == ev.AGENT_IA for e in evs)


def test_agent_ia_ne_touche_pas_deux_fois_le_meme_leurre():
    monde = monde_hors_ligne()
    sid = trafic.agent_ia(monde, 1, random.Random("a2"), client=ClientIA("simulateur"))
    touches = [e["leurre_id"] for e in evenements(monde, sid)
               if e["type"] == "leurre_touche"]
    assert len(touches) == len(set(touches)), "pas de touche en double"


def test_agent_interne_touche_un_canari():
    monde = monde_hors_ligne()
    sid = trafic.agent_interne(monde, 1, random.Random("i"),
                               client=ClientIA("simulateur"))
    evs = evenements(monde, sid)
    assert sid.startswith("banc-interne-")
    assert any(e["type"] == "entree_agent" for e in evs)
    canaris = [e for e in evs if e["type"] == "leurre_touche"
               and (e["leurre_id"] or "").startswith("C-")]
    assert canaris, "le canari interne doit être touché"
    assert all(e["source"] == "interne" for e in canaris)
    assert any(e["type"] == "appel_outil" and e["outil"] == "exporter_clients"
               for e in evs)
    assert all(e["details"]["verite_terrain"] == ev.AGENT_INTERNE for e in evs)


def test_etiquette_refuse_une_session_mal_prefixee():
    with pytest.raises(ValueError):
        ev.evenement(source="externe", surface="site", type="requete",
                     session_id="banc-humain-0001", verite_terrain=ev.AGENT_IA)
