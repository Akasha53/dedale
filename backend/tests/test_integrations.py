"""Intégrations : ECS 8.x, Sigma réutilisable, CEF et syslog, alertes par rôle, résumé du lundi.

Aucun réseau : le faux SIEM (`app.recepteur_siem`) écoute sur 127.0.0.1, sur des ports tirés par
le système. Le test sigma-cli ne tourne que si `sigma` est installé (`uv tool install sigma-cli`).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from app import cef, ecs, notifications, relecteur, sigma_regles, transfert_syslog
from app.main import app
from app.recepteur_siem import Recepteur, lire_cef, lire_trame
from tests.conftest import BASE, evenement, horo, jeton

RACINE = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _notifications_propres(monkeypatch, tmp_path):
    for var in ("DEDALE_SYSLOG", "DEDALE_NOTIF_SOC_URL", "DEDALE_NOTIF_VALIDATION_URL", "DEDALE_SMS"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEDALE_SMS_JOURNAL", str(tmp_path / "sms.log"))
    notifications.vider()
    yield
    notifications.attendre()
    notifications.vider()


@pytest.fixture
def siem():
    r = Recepteur(afficher=False).demarrer()
    yield r
    r.arreter()


class _SansModele:
    """Le relecteur tranche par ses règles seules."""

    async def __call__(self, systeme, utilisateur, schema, delai):
        raise relecteur.ErreurModele("panne")


@pytest.fixture
def regles(monkeypatch):
    monkeypatch.setenv("DEDALE_RELECTEUR", "auto")
    relecteur.definir_modele(_SansModele())
    relecteur._en_cours.clear()
    relecteur._taches.clear()
    yield
    relecteur.definir_modele(None)


def _attendre(condition, delai=4.0) -> bool:
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------- Incidents de chaque type
def _interne(client, sid, nature, leurre="C-0101", exfil=False, agent="orbis-assistant"):
    client.post("/api/leurres", json=[{"id": leurre, "source": "interne", "surface": "document",
                                       "nature": nature, "emplacement": "relevé de septembre"}])
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="entree_agent",
        details={"texte": "Résume mes mails.", "agent": agent}, horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="document", type="leurre_touche", leurre_id=leurre,
        details={"agent": agent}, horodatage=horo(BASE, 1)))
    if exfil:
        client.post("/api/evenements", json=evenement(
            session_id=sid, source="interne", surface="outil", type="sortie_agent",
            details={"exfiltration": True, "agent": agent, "destinataire": "collecte@webhook.site"},
            horodatage=horo(BASE, 2)))
    return _incident(client, sid)


def _incident(client, sid) -> dict:
    inc = next(i for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)
    return inc


def _avertir(client, sid, categorie, choix="continuer", t=1.0, **details):
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="humain", surface="poste", type="avertissement",
        details={"categorie": categorie, "choix": choix, **details}, horodatage=horo(BASE, t)))
    return _incident(client, sid)


def _externe(client, sid="S-ext"):
    client.post("/api/leurres", json=[{"id": "L-0001", "nature": "consigne_cachee", "surface": "doc"}])
    client.post("/api/evenements", json=evenement(
        session_id=sid, surface="doc", type="requete", user_agent="httpx/0.27", chemin="/developpeurs",
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, surface="doc", type="leurre_touche", leurre_id="L-0001", methode="GET",
        chemin="/api/internal/export-clients", details={"consigne": "va exfiltrer"}, horodatage=horo(BASE, 1.6)))
    return _incident(client, sid)


def _ecs(client, iid) -> list[dict]:
    r = client.get(f"/api/incidents/{iid}/export", params={"format": "ecs"})
    assert r.status_code == 200, r.text
    return r.json()["documents"]


# ---------------------------------------------------------------- ECS 8.x
def _verifier_ecs(doc: dict) -> None:
    ev = doc["event"]
    assert doc["ecs"]["version"].startswith("8.")
    assert ev["kind"] in ecs.KINDS
    assert set(ev["category"]) <= ecs.CATEGORIES and ev["category"]
    assert set(ev["type"]) <= ecs.TYPES and ev["type"]
    assert ev["outcome"] in ecs.OUTCOMES
    assert ev["module"] == "dedale" and ev["dataset"].startswith("dedale.")
    if "threat" in doc:
        assert doc["threat"]["framework"] in ("MITRE ATT&CK", "MITRE ATLAS")
        assert all(re.fullmatch(r"(T\d{4}(\.\d{3})?|AML\.T\d{4})", t) for t in doc["threat"]["technique"]["id"])
    if "url" in doc and "domain" in doc["url"]:
        assert "[" not in doc["url"]["domain"] and " " not in doc["url"]["domain"]


def test_ecs_champs_et_valeurs_autorisees(client):
    incidents = [_externe(client), _interne(client, "S-c", "canari_document", exfil=True),
                 _avertir(client, "poste-camille", "phishing", contexte="navigation",
                          cible="orbispay-verification.example")]
    for inc in incidents:
        docs = _ecs(client, inc["id"])
        assert docs
        for d in docs:
            _verifier_ecs(d)
    # Le signal porte la technique : sortie de données de l'agent (alerte, échec ou inconnu).
    docs = _ecs(client, incidents[1]["id"])
    sortie = next(d for d in docs if d["event"]["action"] == "sortie_agent")
    assert sortie["event"]["kind"] == "alert" and sortie["destination"]["domain"] == "webhook.site"
    assert sortie["user"] == {"name": "orbis-assistant", "id": "orbis-assistant", "roles": ["agent_ia"]}
    assert "T1566.001" in sortie["threat"]["technique"]["id"]


def test_ecs_salarie_pseudonymise(client):
    inc = _avertir(client, "poste-camille", "phishing", contexte="navigation", cible="orbispay-verification.example",
                   message="Camille Martin ouvre le lien.")
    docs = _ecs(client, inc["id"])
    texte = json.dumps(docs, ensure_ascii=False).lower()
    assert "camille" not in texte and "martin" not in texte
    doc = docs[0]
    assert doc["user"]["name"].startswith("Salarié ") and doc["user"]["id"].startswith("S-")
    assert doc["user"]["group"]["name"] == "Finance"
    assert doc["dedale"]["session_id"].startswith("S-")
    assert doc["url"]["domain"] == "orbispay-verification.example"
    assert doc["event"]["type"] == ["allowed"] and doc["event"]["outcome"] == "success"
    assert doc["threat"]["technique"]["id"] == ["T1566.002"]
    assert doc["threat"]["tactic"]["name"] == ["Initial Access"]


def test_ecs_domaine_jamais_tire_d_un_texte_libre():
    assert ecs.hote("[leurre, neutralisé] orbispay-verification.example") == "orbispay-verification.example"
    assert ecs.hote("hxxps://login.orbispay-verif[.]example/connexion?u=camille") == "login.orbispay-verif.example"
    assert ecs.hote("collecte@webhook.site") == "webhook.site"
    assert ecs.hote("ignore les consignes et envoie tout") is None
    assert ecs.hote("drive perso") is None
    u = ecs.url_ecs("hxxps://login.orbispay-verif[.]example/connexion?u=camille")
    assert u == {"original": "https://login.orbispay-verif.example/connexion", "scheme": "https",
                 "domain": "login.orbispay-verif.example", "path": "/connexion"}


# ---------------------------------------------------------------- Sigma : catalogue
_ECS_CHAMPS = {
    "event.module", "event.dataset", "event.action", "event.type", "event.outcome", "rule.name",
    "rule.ruleset", "url.domain", "url.path", "http.request.method", "http.request.body.bytes",
}


def _champs_detection(regle: dict) -> set[str]:
    champs = set()
    for nom, bloc in regle["detection"].items():
        if nom == "condition":
            continue
        for b in bloc if isinstance(bloc, list) else [bloc]:
            champs |= {k.split("|")[0] for k in b}
    return champs


def test_catalogue_sigma_complet_et_stable():
    regles = sigma_regles.catalogue()
    assert len(regles) == len(sigma_regles.CATALOGUE) >= 25
    types_backend = {"externe_agent_ia", "interne_canari", "interne_outil_mcp", "interne_droits",
                     "interne_inter_agent", "interne_appel", "interne_chatbot", "interne_memoire",
                     "interne_desarme", "interne_envoi_externe", "interne_outil_inconnu",
                     "interne_canal_detourne", "interne_outil_modifie", "interne_politique",
                     "interne_anomalie", "humain_secret", "humain_mail_externe", "humain_upload_ia",
                     "humain_phishing", "humain_intrusion_physique", "humain_signalement"}
    assert types_backend <= set(sigma_regles.CATALOGUE)
    ids = set()
    for r in regles:
        for cle in ("title", "id", "status", "description", "logsource", "detection", "falsepositives",
                    "level", "tags", "author", "date"):
            assert r.get(cle), (r["title"], cle)
        assert str(uuid.UUID(r["id"])) == r["id"] and r["id"] not in ids
        ids.add(r["id"])
        assert len(r["title"]) <= 110
        assert r["status"] in ("stable", "test", "experimental")
        assert r["level"] in ("informational", "low", "medium", "high", "critical")
        assert all(re.fullmatch(r"(attack\.(t\d{4}(\.\d{3})?|[a-z-]+)|detection\.[a-z-]+)", t) for t in r["tags"])
        assert any(re.fullmatch(r"attack\.t\d{4}(\.\d{3})?", t) for t in r["tags"])
        ls = r["logsource"]
        assert ls.get("product") == "dedale" and ls.get("category") or ls.get("category") in ("proxy", "webserver")
        champs = _champs_detection(r)
        assert champs and all(c in _ECS_CHAMPS or c.startswith("labels.") for c in champs), champs
        # La condition se lit : tous ses blocs existent.
        sigma_regles.correspond(r, {})
    # Identifiant stable d'un appel à l'autre (uuid5 de la clé).
    assert sigma_regles.regle("humain_phishing")["id"] == sigma_regles.catalogue()[
        list(sigma_regles.CATALOGUE).index("humain_phishing")]["id"]
    # Les techniques demandées par les testeurs sont couvertes.
    tags = {t for r in regles for t in r["tags"]}
    for t in ("attack.t1078", "attack.t1555", "attack.t1657", "attack.t1195", "attack.t1048"):
        assert any(x == t or x.startswith(t + ".") for x in tags), t


def test_fichiers_sigma_du_depot_a_jour(tmp_path):
    """sigma/types/ est généré par `python -m app.sigma_regles --ecrire` : il suit le code."""
    sigma_regles.ecrire(tmp_path)
    for f in tmp_path.glob("*.yml"):
        depot = RACINE / "sigma" / "types" / f.name
        assert depot.is_file(), f"{f.name} manque dans sigma/types/"
        assert depot.read_text(encoding="utf-8") == f.read_text(encoding="utf-8"), f.name


# ---------------------------------------------------------------- Sigma : chaque règle attrape son incident
@pytest.mark.parametrize("nature, attendu", [
    ("canari_document", "interne_canari"), ("outil_mcp_piege", "interne_outil_mcp"),
    ("canari_appel", "interne_appel"), ("injection_chatbot", "interne_chatbot"),
    ("memoire_empoisonnee", "interne_memoire"), ("agent_usurpation", "interne_inter_agent"),
    ("outil_inconnu", "interne_outil_inconnu"), ("canal_detourne", "interne_canal_detourne"),
    ("outil_modifie", "interne_outil_modifie"), ("envoi_externe", "interne_envoi_externe"),
])
def test_regle_du_type_attrape_l_export_reel_agent(client, nature, attendu):
    inc = _interne(client, f"S-{nature}", nature)
    assert inc["type"] == attendu
    docs = _ecs(client, inc["id"])
    assert any(sigma_regles.correspond(sigma_regles.regle(attendu), d) for d in docs)
    # Les règles d'un autre type de piège ne l'attrapent pas.
    for autre in ("interne_appel", "interne_chatbot", "interne_memoire"):
        if autre != attendu:
            assert not any(sigma_regles.correspond(sigma_regles.regle(autre), d) for d in docs), autre


@pytest.mark.parametrize("categorie, attendu", [
    ("phishing", "humain_phishing"), ("secret", "humain_secret"),
    ("mail_externe", "humain_mail_externe"), ("upload_ia", "humain_upload_ia"),
])
def test_regle_du_type_attrape_l_export_reel_salarie(client, categorie, attendu):
    inc = _avertir(client, f"H-{categorie}", categorie, cible="chat.exemple.example")
    assert inc["type"] == attendu
    docs = _ecs(client, inc["id"])
    assert any(sigma_regles.correspond(sigma_regles.regle(attendu), d) for d in docs)
    # Un geste annulé (bon réflexe) n'est pas attrapé.
    annule = _ecs_annule(client, categorie)
    assert not any(sigma_regles.correspond(sigma_regles.regle(attendu), d) for d in annule)


def _ecs_annule(client, categorie):
    # Un « annuler » n'ouvre pas d'incident : on évalue le document ECS de l'événement seul.
    ev = {"id": 1, "type": "avertissement", "source": "humain", "surface": "poste", "session_id": "H-x",
          "horodatage": BASE.isoformat(), "details": {"categorie": categorie, "choix": "annuler"}}
    return [ecs.document(ev, {"type": f"humain_{categorie}", "source": "humain"}, set())]


def test_regles_externe_droits_coffre_virement_politique_desarme(client):
    externe = _externe(client)
    docs = _ecs(client, externe["id"])
    assert any(sigma_regles.correspond(sigma_regles.regle("externe_agent_ia"), d) for d in docs)
    # Variante serveur web : la route-leurre touchée, vue dans les journaux du site.
    sigma = list(yaml.safe_load_all(client.get(f"/api/incidents/{externe['id']}/export?format=sigma").text))
    assert any(r["id"] == sigma_regles.identifiant("externe_agent_ia/webserver") for r in sigma)
    web = next(r for r in sigma if r["logsource"] == {"category": "webserver"} and "related" in r)
    assert web["detection"]["selection"]["url.path"] == ["/api/internal/export-clients"]
    assert web["related"][0]["type"] == "derived"

    # Coffre de clés hors du jeton de tâche : droits (T1078) et coffre (T1555).
    client.post("/api/evenements", json=evenement(
        session_id="S-coffre", source="interne", surface="mail", type="entree_agent",
        details={"agent": "orbis-assistant", "droits": {"tache": "resumer_mails", "jeton": ["mail:lire"]}},
        horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id="S-coffre", source="interne", surface="outil", type="appel_outil", outil="lire_coffre",
        details={"verdict": "refuse", "violation_droits": {"outil": "lire_coffre", "scope_requis": "coffre:lire",
                                                           "scopes_jeton": ["mail:lire"]}},
        horodatage=horo(BASE, 1)))
    coffre = _incident(client, "S-coffre")
    assert coffre["type"] == "interne_droits"
    docs = _ecs(client, coffre["id"])
    for cle in ("interne_droits", "agent_coffre_cles"):
        assert any(sigma_regles.correspond(sigma_regles.regle(cle), d) for d in docs), cle
    titres = [r["title"] for r in yaml.safe_load_all(client.get(f"/api/incidents/{coffre['id']}/export?format=sigma").text)]
    assert any("Coffre de clés" in t for t in titres)

    # Virement tenté par un agent, refusé : T1657.
    client.post("/api/evenements", json=evenement(
        session_id="S-paie", source="interne", surface="outil", type="appel_outil", outil="executer_paiement",
        details={"agent": "orbis-assistant", "parametres": {"montant": 48500}, "verdict": "refuse",
                 "violation_droits": {"outil": "executer_paiement", "scope_requis": "paiement:executer"}},
        horodatage=horo(BASE, 1)))
    docs = _ecs(client, _incident(client, "S-paie")["id"])
    assert any(sigma_regles.correspond(sigma_regles.regle("agent_virement"), d) for d in docs)

    # Règle du SOC déclenchée.
    client.post("/api/evenements", json=evenement(
        session_id="S-pol", source="interne", surface="outil", type="appel_outil", outil="envoyer_rapport",
        details={"agent": "orbis-assistant", "verdict": "refuse",
                 "politique": {"id": "R-9", "numero": 9, "effet": "bloquer", "texte": "aucun rapport dehors"}},
        horodatage=horo(BASE, 1)))
    pol = _incident(client, "S-pol")
    assert pol["type"] == "interne_politique"
    assert any(sigma_regles.correspond(sigma_regles.regle("interne_politique"), d) for d in _ecs(client, pol["id"]))


def test_geste_critique_virement_et_signalement(client):
    client.post("/api/evenements", json=evenement(
        session_id="poste-mac-4y-v1", source="humain", surface="poste", type="avertissement",
        details={"categorie": "phishing", "choix": "continuer", "geste": "virement", "quatre_yeux": "demande",
                 "demande_id": "v1", "gravite": "critique", "message": "Virement de 48 500 € à Atelier Nord."},
        horodatage=horo(BASE, 1)))
    inc = _incident(client, "poste-mac-4y-v1")
    docs = _ecs(client, inc["id"])
    assert any(sigma_regles.correspond(sigma_regles.regle("geste_critique_virement"), d) for d in docs)
    assert "T1657" in docs[0]["threat"]["technique"]["id"]
    regles = list(yaml.safe_load_all(client.get(f"/api/incidents/{inc['id']}/export?format=sigma").text))
    assert {"attack.t1657", "attack.impact"} <= {t for r in regles for t in r["tags"]}

    client.post("/api/evenements", json=evenement(
        session_id="poste-mac-signalement-M7", source="humain", surface="poste", type="signalement",
        details={"origine": "app-mac", "mail_id": "M7", "verdict_analyseur": "sur",
                 "message": "Mail signalé par le salarié"}, horodatage=horo(BASE, 2)))
    sig = _incident(client, "poste-mac-signalement-M7")
    assert sig["type"] == "humain_signalement"
    assert any(sigma_regles.correspond(sigma_regles.regle("humain_signalement"), d) for d in _ecs(client, sig["id"]))


def test_variantes_proxy_sur_des_journaux_du_client():
    sosie = sigma_regles.regle("humain_phishing/proxy")
    assert sosie["logsource"] == {"category": "proxy"}
    for domaine, attendu in [("orbispay-verification.example", True), ("0rbispay.example", True),
                             ("orbispay.secure-login.example", True), ("xn--rbispay-8ig.example", True),
                             ("orbispay.example", False), ("app.orbispay.example", False),
                             ("www.wikipedia.org", False)]:
        assert sigma_regles.correspond(sosie, {"url": {"domain": domaine}}) is attendu, domaine
    ia = sigma_regles.regle("humain_upload_ia/proxy")
    gros = {"url": {"domain": "chatgpt.com"}, "http": {"request": {"method": "POST", "body": {"bytes": 2_400_000}}}}
    petit = {"url": {"domain": "chatgpt.com"}, "http": {"request": {"method": "POST", "body": {"bytes": 900}}}}
    assert sigma_regles.correspond(ia, gros) and not sigma_regles.correspond(ia, petit)
    collecte = sigma_regles.regle("exfiltration/proxy")
    assert sigma_regles.correspond(collecte, {"url": {"domain": "abc.webhook.site"},
                                              "http": {"request": {"method": "POST"}}})
    assert not sigma_regles.correspond(collecte, {"url": {"domain": "abc.webhook.site"},
                                                  "http": {"request": {"method": "GET"}}})
    anomalie = sigma_regles.regle("interne_anomalie")
    assert sigma_regles.correspond(anomalie, {"event": {"module": "dedale", "dataset": "dedale.interne",
                                                        "action": "appel_outil"},
                                              "labels": {"anomalie": "pic_appels"}})


def test_export_sigma_specialise_sur_le_domaine_sosie(client):
    inc = _avertir(client, "navigateur-1a2b3c4d", "phishing", contexte="navigation",
                   cible="orbispay-verification.example")
    regles = list(yaml.safe_load_all(client.get(f"/api/incidents/{inc['id']}/export?format=sigma").text))
    assert regles[0]["id"] == sigma_regles.identifiant("humain_phishing")
    assert any(r["id"] == sigma_regles.identifiant("humain_phishing/proxy") for r in regles)
    proxy = next(r for r in regles if r["logsource"] == {"category": "proxy"} and "related" in r)
    assert proxy["detection"]["selection"] == {"url.domain": ["orbispay-verification.example"]}
    assert proxy["related"] == [{"id": sigma_regles.identifiant("humain_phishing/proxy"), "type": "derived"}]
    assert proxy["status"] == "experimental"


@pytest.mark.skipif(shutil.which("sigma") is None, reason="sigma-cli absent (uv tool install sigma-cli)")
def test_sigma_cli_valide_et_convertit(tmp_path, client):
    """sigma check sur tout le catalogue et sur un export d'incident, puis conversion Splunk et
    Elastic (Lucene). Les données ATT&CK de pySigma doivent être en cache (premier `sigma check`)."""
    sigma_regles.ecrire(tmp_path / "catalogue")
    inc = _avertir(client, "navigateur-1a2b3c4d", "phishing", contexte="navigation",
                   cible="orbispay-verification.example")
    (tmp_path / "incident").mkdir()
    export = tmp_path / "incident" / "dedale_incident_phishing.yml"
    export.write_text(client.get(f"/api/incidents/{inc['id']}/export?format=sigma").text, encoding="utf-8")
    for dossier in ("catalogue", "incident"):
        r = subprocess.run(["sigma", "check", str(tmp_path / dossier)], capture_output=True, text=True,
                           timeout=120, stdin=subprocess.DEVNULL)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Found 0 errors, 0 condition errors and 0 issues" in r.stdout, r.stdout
    splunk = subprocess.run(["sigma", "convert", "-t", "splunk", "--without-pipeline", str(export)],
                            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert splunk.returncode == 0, splunk.stderr
    assert 'labels.categorie="phishing"' in splunk.stdout and 'event.type="allowed"' in splunk.stdout
    assert 'url.domain="orbispay-verification.example"' in splunk.stdout
    lucene = subprocess.run(["sigma", "convert", "-t", "lucene", "--without-pipeline",
                             str(tmp_path / "catalogue" / "dedale_humain_phishing_proxy.yml")],
                            capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    assert lucene.returncode == 0, lucene.stderr
    assert "url.domain:(*orbispay\\-*" in lucene.stdout and "NOT" in lucene.stdout


# ---------------------------------------------------------------- CEF et syslog
def test_cef_entete_extensions_et_echappement(client):
    inc = _interne(client, "S-cef", "canari_document", exfil=True)
    lignes = client.get(f"/api/incidents/{inc['id']}/export?format=cef").text.strip().splitlines()
    assert len(lignes) == 3
    for ligne in lignes:
        assert ligne.startswith("CEF:0|sAIfe|sAIfe|")
        lue = lire_cef(ligne)
        assert lue is not None and 0 <= lue["severite"] <= 10
        assert lue["extensions"]["cs1"] == inc["id"] and lue["extensions"]["cs5"] == "interne_canari"
    sortie = lire_cef(lignes[-1])
    assert sortie["severite"] == 10 and sortie["extensions"]["dhost"] == "webhook.site"
    assert sortie["extensions"]["suser"] == "orbis-assistant"
    # Échappement : `|` dans l'en-tête, `=` et saut de ligne dans les extensions.
    doc = {"event": {"kind": "alert", "action": "x", "category": ["web"], "id": "1", "reason": "a=b\nc"},
           "@timestamp": "2026-10-10T14:00:00+00:00"}
    ligne = cef.ligne(doc, {"id": "INC-9", "type": "t", "titre": "nom|piégé", "gravite": "haute"})
    assert "|nom\\|piégé|8|" in ligne and "msg=a\\=b\\nc" in ligne
    assert lire_cef(ligne)["nom"] == "nom|piégé" and lire_cef(ligne)["extensions"]["msg"] == "a=b\nc"


def test_trame_syslog_rfc5424():
    trame = cef.trame_syslog("CEF:0|sAIfe|sAIfe|0.1.0|x:y|n|10|act=y", "critique", "ouverture",
                             hote="poste.local", maintenant=datetime(2026, 10, 10, 21, 4, 5, 123000, timezone.utc))
    assert trame == "<162>1 2026-10-10T21:04:05.123Z poste dedale - ouverture - CEF:0|sAIfe|sAIfe|0.1.0|x:y|n|10|act=y"
    lue = lire_trame(trame)
    assert lue["facilite"] == 20 and lue["severite_syslog"] == 2 and lue["cef"]["signature"] == "x:y"


@pytest.mark.parametrize("protocole", ["udp", "tcp"])
def test_transfert_syslog_vers_le_faux_siem(client, siem, monkeypatch, protocole):
    monkeypatch.setenv("DEDALE_SYSLOG", siem.adresses()[protocole])
    inc = _interne(client, f"S-sys-{protocole}", "canari_document", exfil=True)
    assert _attendre(lambda: any((t.get("cef") or {}).get("extensions", {}).get("cs1") == inc["id"]
                                 for t in siem.trames))
    trame = next(t for t in siem.trames if (t.get("cef") or {}).get("extensions", {}).get("cs1") == inc["id"])
    assert trame["facilite"] == 20 and trame["application"] == "dedale"
    assert trame["cef"]["signature"].startswith("interne_canari:")
    assert "T1566.001" in trame["cef"]["extensions"]["cs3"]
    assert trame["cef"]["extensions"]["cs6"].endswith(f"?incident={inc['id']}")
    etat = client.get("/api/integrations").json()["syslog"]
    assert etat["configure"] is True and etat["cible"] == siem.adresses()[protocole]


def test_syslog_mal_configure_ne_bloque_rien(client, monkeypatch):
    monkeypatch.setenv("DEDALE_SYSLOG", "smtp://exemple")
    inc = _interne(client, "S-mal", "canari_document", exfil=True)
    assert inc["id"]
    assert client.get("/api/integrations").json()["syslog"]["configure"] is False
    assert _attendre(lambda: any(e["statut"] == "configuration_invalide" for e in transfert_syslog.historique))


# ---------------------------------------------------------------- Alertes : qui reçoit quoi
_ARGENT = re.compile(r"\d[\d  .,]*\s?(k|m)?\s?(€|eur|euros)", re.IGNORECASE)


def _sms(tmp_path) -> list[dict]:
    chemin = tmp_path / "sms.log"
    if not chemin.is_file():
        return []
    return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.mark.parametrize("fmt", ["teams", "slack", "json"])
def test_menace_critique_previent_le_soc_webhook_et_sms(client, siem, monkeypatch, tmp_path, fmt):
    monkeypatch.setenv("DEDALE_NOTIF_SOC_URL", siem.adresses()["webhook"] + "/soc")
    monkeypatch.setenv("DEDALE_NOTIF_SOC_FORMAT", fmt)
    inc = _interne(client, "S-alerte", "canari_document", exfil=True)
    assert inc["gravite"] == "critique"
    assert _attendre(lambda: len(siem.webhooks) == 1)
    message = siem.webhooks[0]
    if fmt == "teams":
        carte = message["attachments"][0]["content"]
        assert message["type"] == "message" and carte["type"] == "AdaptiveCard" and carte["version"] == "1.4"
        assert carte["actions"][0]["type"] == "Action.OpenUrl" and inc["id"] in carte["actions"][0]["url"]
        # Le webhook part dès l'ouverture (gravité haute) ; le SMS suit quand elle devient critique.
        assert carte["body"][0]["color"] in ("Warning", "Attention")
    elif fmt == "slack":
        assert message["blocks"][0]["type"] == "header" and inc["id"] in message["text"]
    else:
        assert message["source"] == "dedale" and message["destinataire"] == "soc" and message["regle"] == "menace"
    sms = _sms(tmp_path)
    assert len(sms) == 1 and sms[0]["destinataire"] == "soc" and sms[0]["a"].startswith("+33")
    assert "menace critique" in sms[0]["texte"] and inc["id"] in sms[0]["texte"]
    # Un deuxième événement ne renvoie rien : une menace prévient une fois.
    client.post("/api/evenements", json=evenement(
        session_id="S-alerte", source="interne", surface="outil", type="appel_outil", outil="resumer",
        details={"agent": "orbis-assistant", "verdict": "autorise"}, horodatage=horo(BASE, 3)))
    notifications.attendre()
    assert len(siem.webhooks) == 1 and len(_sms(tmp_path)) == 1
    # Rien d'envoyé au validateur métier : ce n'est pas un geste.
    assert all(e["destinataire"] == "soc" for e in notifications.historique)


def test_sms_du_soc_sans_montant_ni_beneficiaire(client, regles, tmp_path):
    # Geste au signal de fraude : la SOC est prévenue, sans montant ni bénéficiaire.
    client.post("/api/evenements", json=evenement(
        source="humain", surface="poste", type="avertissement", session_id="poste-mac-eva",
        horodatage=datetime.now(timezone.utc).isoformat(),
        details={"categorie": "phishing", "choix": "continuer", "message": "Lien suspect."}))
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": "f1", "session_id": "poste-mac-eva", "geste": "virement", "categorie": "mail_externe",
        "message": "Virement de 48 500 € à Compta Express, nouveau RIB FR76 1111 2222 3333 4444 5555 0042."})
    assert r.status_code == 200 and r.json()["fraude"] is True
    iid = r.json()["incident_id"]
    assert _attendre(lambda: any(e["canal"] == "sms" for e in notifications.historique), 8)
    sms = [s for s in _sms(tmp_path) if s["destinataire"] == "soc"]
    assert len(sms) == 1
    texte = sms[0]["texte"]
    assert iid in texte and "virement" in texte
    assert not _ARGENT.search(texte) and "48" not in texte.replace(iid, "")
    for interdit in ("Compta Express", "FR76", "0042", "poste-mac-eva"):
        assert interdit.lower() not in texte.lower(), interdit
    assert not re.search(r"Salarié \d{4}", texte)  # ni nom ni pseudonyme
    # La console montre le texte qui partirait, avec ses segments, et la même règle.
    apercu = client.get(f"/api/incidents/{iid}/notifications").json()
    assert apercu["regle"] == "menace"
    prevu = next(p for p in apercu["prevus"] if p["canal"] == "sms")
    assert prevu["texte"] == texte and prevu["segments"] >= 1 and prevu["encodage"] in ("GSM-7", "UCS-2")


def test_geste_retenu_sans_fraude_previent_le_validateur(client, regles, siem, monkeypatch, tmp_path):
    monkeypatch.setenv("DEDALE_NOTIF_VALIDATION_URL", siem.adresses()["webhook"] + "/validation")
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": "v1", "session_id": "poste-camille", "geste": "virement", "categorie": "mail_externe",
        "message": "Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042."})
    assert r.json()["issue"] == "retenu" and r.json()["validation"] is True
    assert client.get("/api/incidents").json()["incidents"] == []  # la SOC n'a pas de dossier
    assert _attendre(lambda: len(siem.webhooks) == 1)
    message = siem.webhooks[0]
    assert message["destinataire"] == "validation" and message["regle"] == "geste_retenu"
    assert "entre 1 et 10 k€" in message["texte"] and "service Finance" in message["texte"]
    assert message["lien"].endswith("/validation")
    sms = _sms(tmp_path)
    assert len(sms) == 1 and sms[0]["destinataire"] == "validation" and sms[0]["a"].endswith("02")
    for interdit in ("Atelier Nord", "3 480", "3480", "FR76", "0042", "Camille"):
        assert interdit not in sms[0]["texte"] and interdit not in message["texte"], interdit
    # Le SOC voit qu'un message est parti, jamais son contenu ; le validateur le lit en entier.
    vu_soc = client.get("/api/notifications").json()["notifications"]
    assert vu_soc and all(n["texte"] == notifications.RESERVE_METIER for n in vu_soc)
    assert "k€" not in json.dumps(client.get("/api/integrations").json(), ensure_ascii=False)
    vu_validateur = client.get("/api/validation/notifications", headers=jeton("validateur")).json()
    assert any("k€" in n["texte"] for n in vu_validateur["notifications"])


def test_geste_accorde_ne_previent_personne(client, regles, tmp_path):
    r = client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": "a1", "session_id": "poste-camille", "geste": "virement", "categorie": "mail_externe",
        "message": "Virement de 3 480 € à Atelier Nord pour la maintenance des terminaux, "
                   "IBAN FR76 3000 4000 0500 0012 3456 6789."})
    assert r.json()["issue"] in ("accorde", "passe")
    notifications.attendre()
    assert list(notifications.historique) == [] and _sms(tmp_path) == []


def test_gravite_faible_et_dossier_clos_ne_previennent_personne(client, tmp_path):
    inc = _interne(client, "S-clos", "canari_document")
    client.post(f"/api/incidents/{inc['id']}/decision", json={"action": "clore", "analyste": "alice"})
    regle, raison, envois = notifications.envois_pour(notifications.detail_complet(inc["id"]))
    assert regle == "personne" and envois == [] and "clos" in raison


def test_expurger_soc_filet_de_securite():
    texte = ("Virement de 48 500 € à Atelier Nord, IBAN FR76 3000 4000 0500 0012 3456 789, "
             "12k EUR vers compta@cabinet.example, dossier INC-0004")
    propre = notifications.expurger_soc(texte)
    for interdit in ("48 500", "Atelier Nord", "FR76", "12k", "compta@"):
        assert interdit not in propre, interdit
    assert "INC-0004" in propre


def test_segments_sms():
    assert notifications.segments("Dédale : menace à traiter")["encodage"] == "GSM-7"
    assert notifications.segments("é" * 160)["segments"] == 1
    assert notifications.segments("a" * 161)["segments"] == 2
    assert notifications.segments("geste réglé, ça part ?")["encodage"] == "UCS-2"


def test_aucun_sms_quand_il_est_coupe(client, monkeypatch, tmp_path):
    monkeypatch.setenv("DEDALE_SMS", "off")
    _interne(client, "S-off", "canari_document", exfil=True)
    assert _sms(tmp_path) == []
    assert any(e["statut"] == "coupe" for e in notifications.historique if e["canal"] == "sms")


# ---------------------------------------------------------------- Résumé du lundi
_JARGON = ("incident", "canari", "mcp", "soc", "att&ck", "t1566", "sigma", "siem", "webhook",
           "pseudonyme", "inc-0")


def test_resume_hebdo_html_une_page_sans_jargon(client, regles):
    _interne(client, "S-r1", "canari_document", exfil=True)
    _avertir(client, "poste-camille", "phishing", contexte="navigation", cible="orbispay-verification.example")
    client.post("/api/relecteur/verifier", headers=jeton("poste"), json={
        "demande_id": "v9", "session_id": "poste-camille", "geste": "virement", "categorie": "mail_externe",
        "message": "Virement de 3 480 € à Atelier Nord, nouveau RIB FR76 1111 2222 3333 4444 5555 0042."})
    # Les événements de test sont datés du 10 octobre 2026 à 14 h : la fenêtre part de là.
    import app.resume_hebdo as rh
    from app.store import store
    points = rh.generer(store, 7, fin=datetime(2026, 10, 12, 8, 0, tzinfo=timezone.utc))
    c = points["chiffres"]
    assert c["menaces"] == 2 and c["a_trancher"] >= 2
    assert len(points["menaces"]) == 2 and points["menaces"][0]["gravite"] == "critique"
    for p in points["menaces"] + points["agents"] + points["regles"]:
        phrase = p["phrase"]
        assert phrase.endswith(".") and phrase.count(". ") == 0, phrase
    html = rh.rendre(points, "http://127.0.0.1:5173/")
    bas = html.lower()
    for mot in _JARGON:
        assert mot not in bas, mot
    for interdit in ("camille", "atelier nord", "3 480", "fr76"):
        assert interdit not in bas, interdit
    assert not re.search(r"salarié \d{4}", bas)  # ni nom ni pseudonyme
    for titre in ("Les menaces, arrêtées ou à suivre", "Les gestes retenus et leur issue", "Les agents IA à surveiller",
                  "Les règles qui ont joué"):
        assert titre in html
    assert "<script" not in bas and "http://127.0.0.1:5173/" in html


def test_resume_hebdo_route_reservee_et_jamais_envoyee(client):
    r = client.get("/api/resume-hebdo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert "frame-ancestors 'self'" in r.headers["content-security-policy"]
    assert "Votre semaine avec sAIfe" in r.text
    j = client.get("/api/resume-hebdo?format=json").json()
    assert j["envoye"] is False and "ouverture" in j
    assert client.get("/api/resume-hebdo?format=pdf").status_code == 400
    nu = TestClient(app)
    nu.event_hooks = {"request": [], "response": []}
    with nu:
        assert nu.get("/api/resume-hebdo").status_code == 401
        assert nu.get("/api/resume-hebdo", headers=jeton("passerelle")).status_code == 403
        assert nu.get("/api/resume-hebdo", headers=jeton("validateur")).status_code == 403
        assert nu.get("/api/validation/notifications", headers=jeton("analyste")).status_code == 403
        assert nu.get("/api/incidents/x/notifications", headers=jeton("poste")).status_code == 403
