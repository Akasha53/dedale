"""Service : relève, verdicts, mail désarmé, flux en direct et signalement au backend."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import envoyer_demo
import service as svc
from boite import BoiteIndisponible

JEU = envoyer_demo.construire_jeu()


class BoiteFausse:
    """Boîte Mailpit en mémoire : mêmes méthodes que boite.Boite, sans réseau."""

    base = "http://boite-fausse"

    def __init__(self):
        self.mails: dict[str, bytes] = {}
        self.absente = False

    def ajouter(self, cas: envoyer_demo.Cas) -> str:
        identifiant = f"ID{len(self.mails):04d}{cas.code}"
        self.mails[identifiant] = cas.message.as_bytes()
        return identifiant

    def lister(self, limite=200):
        if self.absente:
            raise BoiteIndisponible("boîte arrêtée")
        maintenant = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        return [{"ID": i, "Created": maintenant} for i in reversed(list(self.mails))][:limite]

    def brut(self, identifiant):
        if self.absente:
            raise BoiteIndisponible("boîte arrêtée")
        return self.mails[identifiant]


class BackendFaux:
    base = "http://backend-faux"

    def __init__(self, present=True, actif=True):
        self.present = present
        self.actif = actif
        self.recus: list[dict] = []

    def session_existe(self, session_id):
        if not self.present:
            return None
        return any(e["session_id"] == session_id for e in self.recus)

    def poster(self, corps):
        if not self.present:
            return None
        self.recus.append(json.loads(json.dumps(corps)))
        return {"session": {"id": corps["session_id"]}, "consigne": "aucune"}


@pytest.fixture
def boite():
    b = BoiteFausse()
    for cas in JEU:
        b.ajouter(cas)
    return b


def test_releve_tout_le_jeu_et_signale_chaque_frauduleux_une_fois(boite):
    backend = BackendFaux()
    s = svc.Service(boite, backend)
    nouveaux = s.relever()
    assert len(nouveaux) == len(JEU)
    attendus = {f"ID{i:04d}{c.code}": c.attendu for i, c in enumerate(JEU)}
    assert {v["id"]: v["verdict"] for v in nouveaux} == attendus
    frauduleux = [v for v in nouveaux if v["verdict"] == "frauduleux"]
    assert len(backend.recus) == len(frauduleux) == 8
    assert all(v["signalement"]["statut"] == "envoye" for v in frauduleux)
    assert s.relever() == [] and len(backend.recus) == 8          # rien n'est signalé deux fois


def test_forme_de_l_evenement_envoye_au_backend(boite):
    backend = BackendFaux()
    svc.Service(boite, backend).relever()
    ev = next(e for e in backend.recus if "fraude_president" in e["session_id"])
    assert (ev["source"], ev["surface"], ev["type"]) == ("humain", "poste", "avertissement")
    assert ev["session_id"].startswith("mail-")
    d = ev["details"]
    assert d["categorie"] == "phishing" and d["contexte"] == "mail reçu"
    assert d["verdict"] == "frauduleux" and d["raisons"] and d["message"].startswith("Le mail presse")
    assert "choix" not in d                                        # le salarié n'a encore rien choisi
    assert d["document_source"]["type"] == "mail"
    cache = next(e for e in backend.recus if "instruction_blanche" in e["session_id"])["details"]
    assert "ignore les instructions précédentes" in cache["extrait"]
    assert any(seg["piege"] for seg in cache["document_source"]["segments"])
    lien = next(e for e in backend.recus if e["session_id"].endswith("sosie"))["details"]["lien"]
    assert lien.startswith("hxxps://") and "[.]" in lien


def test_backend_absent_ne_fait_rien_tomber_puis_rattrape(boite):
    backend = BackendFaux(present=False)
    s = svc.Service(boite, backend)
    assert len(s.relever()) == len(JEU)
    assert len(s.a_signaler) == 8 and s.erreur_backend
    backend.present = True
    s._prochain_essai = 0.0
    s.relever()
    assert s.a_signaler == [] and len(backend.recus) == 8 and s.erreur_backend is None


def test_session_deja_connue_du_backend_n_est_pas_renvoyee(boite):
    backend = BackendFaux()
    svc.Service(boite, backend).relever()
    s2 = svc.Service(boite, backend)          # redémarrage du service, même boîte, même backend
    s2.relever()
    assert len(backend.recus) == 8
    assert {v["signalement"]["statut"] for v in s2.verdicts.values() if v["signalement"]} == {"deja_present"}


def test_signalement_desactive():
    b = BoiteFausse()
    b.ajouter(next(c for c in JEU if c.code == "piece_exe"))
    backend = BackendFaux(actif=False)
    v = svc.Service(b, backend).relever()[0]
    assert v["signalement"]["statut"] == "desactive" and backend.recus == []


def test_boite_absente(boite):
    boite.absente = True
    s = svc.Service(boite, BackendFaux())
    assert s.relever() == []
    with TestClient(svc.creer_app(s, releve_auto=False)) as client:
        sante = client.get("/sante").json()
        assert sante["boite"]["joignable"] is False and "arrêtée" in sante["boite"]["erreur"]
        assert client.get("/mails/ID0000rh_entretiens").status_code == 503


@pytest.fixture
def client(boite):
    s = svc.Service(boite, BackendFaux())
    with TestClient(svc.creer_app(s, releve_auto=False)) as c:
        c.post("/relever")
        yield c


def test_routes_verdicts_et_mails(client):
    d = client.get("/verdicts").json()
    assert d["total"] == len(JEU) and d["repartition"] == {"sur": 3, "suspect": 1, "frauduleux": 8}
    assert d["verdicts"][0]["id"].endswith("caracteres_invisibles")          # le plus récent d'abord
    v = d["verdicts"][0]
    for champ in ("id", "recu_a", "de", "objet", "verdict", "frauduleux", "score", "gravite", "titre_alerte",
                  "conseil", "raison_principale", "raisons", "signaux", "pieces_jointes", "signalement"):
        assert champ in v
    seuls = client.get("/verdicts", params={"verdict": "suspect"}).json()["verdicts"]
    assert [x["id"] for x in seuls] == ["ID0003relance_paiement"]
    assert client.get("/verdicts", params={"verdict": "autre"}).status_code == 422
    assert len(client.get("/mails").json()["mails"]) == len(JEU)


def test_mail_complet_desarme(client):
    d = client.get("/mails/ID0004sosie").json()
    assert d["verdict"]["verdict"] == "frauduleux"
    assert d["liens"][0]["destination"] == "hxxps://orbispay-verification[.]example/connexion"
    assert "https://" not in json.dumps(d["liens"]) and "https://" not in d["texte"]
    assert client.get("/mails/inconnu").status_code == 404
    assert client.get("/mails/..%2F..%2Fapi").status_code == 404


def test_flux_sse_rejoue_et_pousse(client):
    with client.stream("GET", "/flux", params={"derniers": 1, "max": 1}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        texte = "".join(r.iter_text())
    assert "event: verdict" in texte
    donnees = json.loads(texte.split("data: ", 1)[1].split("\n", 1)[0])
    assert donnees["id"].endswith("caracteres_invisibles")


def test_websocket_pousse_chaque_nouveau_verdict(client, boite):
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "bonjour"
        identifiant = boite.ajouter(next(c for c in JEU if c.code == "piece_macro"))
        client.post("/relever")
        message = ws.receive_json()
        assert message["type"] == "verdict"
        assert message["donnees"]["id"] == identifiant and message["donnees"]["verdict"] == "frauduleux"
