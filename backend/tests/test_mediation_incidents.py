"""Médiation universelle de la passerelle interne : chaque règle nomme son incident.

Les règles C-8A61 (outil inconnu), C-5B27 (canal de sortie détourné) et C-3F90 (outil MCP
modifié) sont publiées comme des canaris. Premier canari touché de la session, elles donnent
`interne_outil_inconnu`, `interne_canal_detourne` ou `interne_outil_modifie`, et la session
est suspendue en attendant l'analyste.
"""

from __future__ import annotations

import pytest

from tests.conftest import BASE, evenement, horo

REGLES = [
    ("C-8A61", "outil_inconnu", "envoyer_mail", "interne_outil_inconnu"),
    ("C-5B27", "canal_detourne", "chercher_document", "interne_canal_detourne"),
    ("C-3F90", "outil_modifie", "convertir_montant", "interne_outil_modifie"),
]


@pytest.mark.parametrize("regle,nature,outil,type_attendu", REGLES)
def test_regle_de_mediation_nomme_l_incident(client, regle, nature, outil, type_attendu):
    client.post("/api/leurres", json=[
        {"id": regle, "source": "interne", "surface": "outil", "nature": nature,
         "emplacement": "passerelle de l'agent interne", "description": "Règle, pas un piège."},
        {"id": "C-2B91", "source": "interne", "surface": "document", "nature": "faux_secret",
         "emplacement": "coffre", "description": "Fausse clé d'API."},
    ])
    sid = f"S-{nature}"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil=outil,
        details={"verdict": "retenu", "retenu": True, "motif": nature, "parametres": {},
                 nature: {"outil": outil, "canaris": ["C-2B91"]}},
        horodatage=horo(BASE, 0)))
    for i, leurre in enumerate((regle, "C-2B91"), start=1):
        client.post("/api/evenements", json=evenement(
            session_id=sid, source="interne", surface="outil", type="leurre_touche",
            leurre_id=leurre, outil=outil, details={"type": nature, "detail": "retenu"},
            horodatage=horo(BASE, i * 0.1)))

    incidents = client.get("/api/incidents").json()["incidents"]
    inc = next(i for i in incidents if i["session_id"] == sid)
    assert inc["type"] == type_attendu
    assert client.get(f"/api/sessions/{sid}").json()["etat"] == "suspendue"


def _incident_mediation(client, regle, nature, outil):
    client.post("/api/leurres", json=[
        {"id": regle, "source": "interne", "surface": "outil", "nature": nature,
         "emplacement": "passerelle de l'agent interne", "description": "Règle, pas un piège."},
    ])
    sid = f"S-cert-{nature}"
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil=outil,
        details={"verdict": "retenu", "retenu": True, "motif": nature, "parametres": {},
                 nature: {"outil": outil, "regle": regle}},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="leurre_touche",
        leurre_id=regle, outil=outil, details={"type": nature, "detail": "retenu"},
        horodatage=horo(BASE, 0.1)))
    return next(i for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)["id"]


@pytest.mark.parametrize("regle,nature,outil,type_attendu", REGLES)
def test_retenue_par_regle_sans_pourcentage(client, regle, nature, outil, type_attendu):
    """Une règle fixe a retenu l'appel : la certitude nomme la règle, sans score ni raisons."""
    iid = _incident_mediation(client, regle, nature, outil)
    conf = client.get(f"/api/incidents/{iid}/synthese").json()["confiance"]
    assert conf["niveau"] == "regle" and conf["regle"] == regle
    assert conf["score"] is None and conf["raisons"] == []


@pytest.mark.parametrize("regle,nature,outil,type_attendu", REGLES[:1])
def test_pre_tri_reprend_la_certitude_de_la_synthese(client, regle, nature, outil, type_attendu):
    """Une seule source : le pré-tri porte la certitude de la synthèse, telle quelle."""
    iid = _incident_mediation(client, regle, nature, outil)
    conf = client.get(f"/api/incidents/{iid}/synthese").json()["confiance"]
    tri = client.get(f"/api/incidents/{iid}/tri").json()
    assert tri["certitude"] == {"score": conf["score"], "niveau": conf["niveau"], "regle": conf["regle"]}
