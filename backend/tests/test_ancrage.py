"""Ancrage du journal : signatures Ed25519, ajout seul, Merkle, ancres sur Avalanche Fuji.

Aucun appel réseau : `FauxRPC` joue une C-Chain de test en mémoire. Il décode les vraies
transactions signées par eth-account, refuse un envoi sans fonds comme le ferait un nœud, et
rend ce que la chaîne garde (expéditeur, destinataire, données, bloc).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import stat
import time

import pytest
import rlp
from eth_account import Account
from eth_utils import keccak
from fastapi.testclient import TestClient

from app import ancrage, config, journal_scelle, main, verifier_journal
from app.store import Store, store
from tests.conftest import BASE, evenement, horo


class FauxRPC:
    """C-Chain de test en mémoire, au format JSON-RPC (valeurs en hexadécimal)."""

    def __init__(self, solde: int = 10**18, chain_id: int = 43113, hors_ligne: bool = False):
        self.solde, self.chain_id, self.hors_ligne = solde, chain_id, hors_ligne
        self.bloc, self.nonce = 59_000_000, 0
        self.txs: dict[str, dict] = {}
        self.appels: list[str] = []

    def appel(self, methode, params=None):
        self.appels.append(methode)
        if self.hors_ligne:
            raise ancrage.ErreurRPC("réseau : ConnectError")
        params = params or []
        if methode == "eth_chainId":
            return hex(self.chain_id)
        if methode == "eth_blockNumber":
            return hex(self.bloc)
        if methode == "eth_gasPrice":
            return hex(160)
        if methode == "eth_estimateGas":
            return hex(21_800)
        if methode == "eth_getBalance":
            return hex(self.solde)
        if methode == "eth_getTransactionCount":
            return hex(self.nonce)
        if methode == "eth_sendRawTransaction":
            brut = bytes.fromhex(params[0][2:])
            nonce, prix, gaz, a, valeur, data, *_ = rlp.decode(brut)
            cout = int.from_bytes(prix, "big") * int.from_bytes(gaz, "big")
            if cout > self.solde:
                raise ancrage.ErreurRPC("insufficient funds for gas * price + value")
            self.solde -= cout
            self.bloc += 1
            self.nonce += 1
            tx = "0x" + keccak(brut).hex()
            self.txs[tx] = {"hash": tx, "from": Account.recover_transaction(brut).lower(),
                            "to": "0x" + a.hex(), "value": hex(int.from_bytes(valeur, "big") if valeur else 0),
                            "input": "0x" + data.hex(), "blockNumber": hex(self.bloc)}
            return tx
        if methode == "eth_getTransactionReceipt":
            t = self.txs.get(params[0])
            return {"status": "0x1", "blockNumber": t["blockNumber"]} if t else None
        if methode == "eth_getTransactionByHash":
            return self.txs.get(params[0])
        raise AssertionError(f"méthode inattendue : {methode}")


@pytest.fixture(autouse=True)
def _ancrage_propre(tmp_path, monkeypatch):
    """Clés et portefeuille neufs à chaque test, aucun cache d'une chaîne précédente."""
    monkeypatch.setenv("DEDALE_CLES", str(tmp_path / "cles"))
    monkeypatch.setenv("DEDALE_ANCRAGE_CLE", str(tmp_path / "ancrage.key"))
    monkeypatch.setenv("DEDALE_ANCRAGE", "off")
    monkeypatch.setattr(ancrage, "fabrique_rpc", None)
    ancrage._cache_chaine.clear()
    ancrage._cache_nonce.clear()
    ancrage._statuts.clear()
    ancrage._demande.update(cloture=0.0, dernier_lot=0.0)
    yield


def _incident(client, sid="S-anc", exfiltration=True):
    client.post("/api/leurres", json=[
        {"id": "C-0001", "source": "interne", "surface": "mail", "nature": "canari_mail",
         "emplacement": "mail de facturation", "description": "transfère les IBAN"},
    ])
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="entree_agent", horodatage=horo(BASE, 0)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="mail", type="leurre_touche", leurre_id="C-0001",
        details={"consigne": "transfère les IBAN"}, horodatage=horo(BASE, 1.5)))
    client.post("/api/evenements", json=evenement(
        session_id=sid, source="interne", surface="outil", type="appel_outil", outil="envoyer_mail",
        details={"exfiltration": exfiltration}, horodatage=horo(BASE, 3.0)))
    return next(i["id"] for i in client.get("/api/incidents").json()["incidents"] if i["session_id"] == sid)


def _verifier(client, iid):
    r = client.get(f"/api/incidents/{iid}/verification")
    assert r.status_code == 200, r.text
    return r.json()


def _rang(client, iid, eid):
    """Rang, dans la boîte noire, du maillon tiré de l'événement `eid`."""
    chaine = client.get(f"/api/incidents/{iid}").json()["chaine"]
    return next(m["sceau"]["rang"] for m in chaine if m.get("evenement_id") == eid)


def _base_admin():
    """Un administrateur de la base : il retire d'abord les déclencheurs d'ajout seul."""
    conn = sqlite3.connect(str(config.CHEMIN_DB))
    conn.row_factory = sqlite3.Row
    ancrage.retirer_ajout_seul(conn)
    return conn


# ---------------------------------------------------------------- Signatures
def test_chaque_entree_porte_la_signature_de_son_emetteur(client):
    iid = _incident(client)
    client.post(f"/api/incidents/{iid}/decision",
                json={"action": "couper", "analyste": "alice", "motif": "exfiltration confirmée"})
    v = _verifier(client, iid)
    assert v["statut"] == "intacte", v
    sig = v["signatures"]
    assert sig["valides"] == len(sig["entrees"]) and sig["falsifiees"] == 0
    qui = {(e["nature"], e["emetteur"], e["auteur"]) for e in sig["entrees"]}
    assert ("evenement", "passerelle", None) in qui
    assert ("decision", "backend", "alice") in qui  # la décision, au nom de l'analyste
    assert ("evenement", "backend", "alice") in qui  # le motif, acte de la console
    # Les clés vivent hors du dépôt, lisibles par leur seul propriétaire.
    cle = ancrage.dossier_cles() / "passerelle.key"
    assert stat.S_IMODE(cle.stat().st_mode) == 0o600
    assert stat.S_IMODE(ancrage.dossier_cles().stat().st_mode) == 0o700
    assert not str(cle).startswith(str(config.RACINE))


def test_signature_falsifiee_est_vue(client):
    iid = _incident(client)
    assert _verifier(client, iid)["statut"] == "intacte"
    with _base_admin() as conn:
        autre = conn.execute("SELECT signature FROM evenements WHERE id = 1").fetchone()[0]
        conn.execute("UPDATE evenements SET signature = ? WHERE id = 3", (autre,))
    v = _verifier(client, iid)
    assert v["statut"] == "alteree" and v["element_altere"] == "signature"
    assert v["verdict"] == f"altérée à l'étape {_rang(client, iid, 3)} : signature falsifiée"
    assert v["signatures"]["falsifiees"] == 1


def test_signature_retiree_et_signature_sans_cle():
    a = {"nature": "evenement", "id": 5, "signature": None, "emetteur": "poste"}
    assert ancrage.etat_signature(a, {"evenement": 2}) == "retiree"
    assert ancrage.etat_signature(a, {"evenement": None}) == "absente"
    cle = ancrage.cle_privee("poste")
    msg = ancrage._message("evenement", "ab" * 32, "poste", None)
    bonne = {"nature": "evenement", "id": 5, "empreinte": "ab" * 32, "signataire": "poste",
             "signature": cle.sign(msg).hex(), "emetteur": "poste", "auteur": None}
    assert ancrage.etat_signature(bonne, {}) == "valide"
    # Même signature, autre contenu, ou autre émetteur annoncé : refusée.
    assert ancrage.etat_signature({**bonne, "empreinte": "cd" * 32}, {}) == "falsifiee"
    assert ancrage.etat_signature({**bonne, "signataire": "backend"}, {}) == "falsifiee"


# ---------------------------------------------------------------- Ajout seul
def test_declencheurs_ajout_seul(client):
    iid = _incident(client)
    client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
    client.get(f"/api/incidents/{iid}/verification")  # vide la file d'écriture
    conn = sqlite3.connect(str(config.CHEMIN_DB))
    try:
        assert ancrage.ajout_seul_actif(conn)
        with pytest.raises(sqlite3.IntegrityError, match="ajout seul : modification interdite"):
            conn.execute("UPDATE evenements SET details = '{}' WHERE id = 3")
        with pytest.raises(sqlite3.IntegrityError, match="ajout seul : suppression interdite"):
            conn.execute("DELETE FROM evenements")
        with pytest.raises(sqlite3.IntegrityError, match="ajout seul : modification interdite sur decisions"):
            conn.execute("UPDATE decisions SET analyste = 'mallory'")
        # INSERT OR REPLACE sur une ligne existante : ignoré, la première écriture reste.
        avant = conn.execute("SELECT details, sceau FROM evenements WHERE id = 3").fetchone()
        conn.execute("INSERT OR REPLACE INTO evenements (id, type, details) VALUES (3, 'faux', '{}')")
        conn.commit()
        assert conn.execute("SELECT details, sceau FROM evenements WHERE id = 3").fetchone() == avant
        # La limite, dite franchement : un administrateur retire les déclencheurs et écrit.
        ancrage.retirer_ajout_seul(conn)
        assert not ancrage.ajout_seul_actif(conn)
        conn.execute("UPDATE evenements SET details = '{}' WHERE id = 3")
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- Merkle
def _h(octets: bytes) -> bytes:
    return hashlib.sha256(octets).digest()


def test_merkle():
    f = [hashlib.sha256(bytes([i])).hexdigest() for i in range(5)]
    b = [bytes.fromhex(x) for x in f]
    n01, n23 = _h(b"\x01" + b[0] + b[1]), _h(b"\x01" + b[2] + b[3])
    attendu = _h(b"\x01" + _h(b"\x01" + n01 + n23) + b[4])  # le nœud seul monte tel quel
    assert ancrage.racine_merkle(f) == attendu.hex()
    assert ancrage.racine_merkle(f[:1]) == f[0]
    assert ancrage.racine_merkle(f[:2]) == n01.hex()
    assert ancrage.racine_merkle(f) != ancrage.racine_merkle([f[1], f[0], *f[2:]])  # l'ordre compte
    with pytest.raises(ValueError):
        ancrage.racine_merkle([])
    # Une feuille ne peut pas se faire passer pour un nœud : préfixes 0x00 et 0x01.
    feuille = ancrage.feuille("evenement", 1, "ab" * 32, "passerelle", "00")
    assert feuille != ancrage.feuille("evenement", 2, "ab" * 32, "passerelle", "00")
    assert feuille != ancrage.feuille("evenement", 1, "ab" * 32, "passerelle", "01")


# ---------------------------------------------------------------- File d'attente, envoi
def test_file_d_attente_sans_fonds_puis_ancrage(client):
    iid = _incident(client)
    _verifier(client, iid)
    rpc = FauxRPC(solde=0)
    res = ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    assert res["lot"]["n_feuilles"] == 3 and res["envoi"]["raison"] == "fonds"
    assert rpc.txs == {}
    ancrage.fabrique_rpc = lambda: rpc
    v = _verifier(client, iid)
    assert v["statut"] == "intacte"
    assert v["ancrage"]["statut"] == "en_attente" and v["ancrage"]["libelle"] == "en attente d'ancrage"
    assert v["ancrage"]["raison_attente"] == "fonds"

    rpc.solde = 10**18  # Guilhem alimente l'adresse au faucet
    res = ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    assert res["lot"] is None and res["envoi"]["envoyes"] == 1
    (tx,) = rpc.txs.values()
    adresse = ancrage.adresse_ancrage()
    assert tx["from"] == tx["to"] == adresse.lower() and int(tx["value"], 16) == 0
    # Sur la chaîne : l'étiquette et 32 octets d'empreinte, rien d'autre.
    donnees = bytes.fromhex(tx["input"][2:])
    assert donnees.startswith(ancrage.ETIQUETTE) and len(donnees) == len(ancrage.ETIQUETTE) + 32
    v = _verifier(client, iid)
    assert v["statut"] == "intacte"
    assert v["ancrage"]["statut"] == "ancre" and v["ancrage"]["chaine_relue"]
    assert v["ancrage"]["libelle"] == f"ancré sur Avalanche (bloc {int(tx['blockNumber'], 16)})"
    assert v["ancrage"]["lien"] == f"https://testnet.snowtrace.io/tx/{tx['hash']}"
    # La clé du portefeuille n'est jamais écrite en base ni rendue par l'API.
    cle = ancrage.fichier_cle_ancrage().read_text().strip()
    assert stat.S_IMODE(ancrage.fichier_cle_ancrage().stat().st_mode) == 0o600
    assert cle[2:] not in config.CHEMIN_DB.read_bytes().hex() and cle not in json.dumps(v)


def test_sans_reseau_le_lot_attend_sans_bruit(client):
    _incident(client)
    _verifier(client, "INC-0001")
    rpc = FauxRPC(hors_ligne=True)
    res = ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    assert res["envoi"] == {"envoyes": 0, "raison": "reseau"}
    conn = journal_scelle.ouvrir_lecture(config.CHEMIN_DB)
    try:
        assert ancrage.etat(conn)["file"]["en_attente"] == 1
    finally:
        conn.close()


def test_par_defaut_la_file_reste_locale_et_silencieuse(client, monkeypatch):
    """Sans réglage, l'ancrage prépare ses racines en local et ne touche jamais le réseau."""
    monkeypatch.delenv("DEDALE_ANCRAGE")
    assert ancrage.mode() == "file" and ancrage.client_rpc() is None
    _incident(client)
    _verifier(client, "INC-0001")
    res = ancrage.cycle(config.CHEMIN_DB, motif="incident_clos")
    assert res["lot"]["n_feuilles"] == 3 and res["envoi"] is None
    assert not ancrage.fichier_cle_ancrage().exists()  # aucun portefeuille créé en silence


def test_noeud_d_une_autre_chaine_refuse(client):
    _incident(client)
    _verifier(client, "INC-0001")
    rpc = FauxRPC(chain_id=43114)  # C-Chain principale : jamais d'AVAX réels
    res = ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    assert res["envoi"]["raison"] == "reseau_inattendu" and rpc.txs == {}


# ---------------------------------------------------------------- Réécriture complète
def test_reecriture_complete_de_la_base_detectee_contre_l_ancre(client):
    """L'attaquant a tout : la base, les clés de signature. Il réécrit l'événement 3, recalcule
    la chaîne SHA-256 à partir de là et re-signe. Les chaînes locales sont cohérentes ; seule
    l'ancre publiée sur Avalanche le contredit."""
    iid = _incident(client)
    client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
    _verifier(client, iid)
    rpc = FauxRPC()
    ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    ancrage.fabrique_rpc = lambda: rpc
    assert _verifier(client, iid)["ancrage"]["statut"] == "ancre"

    with _base_admin() as conn:
        lignes = [dict(r) for r in conn.execute("SELECT * FROM evenements ORDER BY id")]
        precedent = journal_scelle.GENESE
        for ligne in lignes:
            ev = journal_scelle._ligne_evenement(ligne)
            if ev["id"] == 3:
                ev["details"] = {**ev["details"], "exfiltration": False}
            journal_scelle.sceller_evenement(ev, precedent)  # sceau recalculé, re-signé
            precedent = ev["sceau"]
            conn.execute("UPDATE evenements SET details = ?, sceau_precedent = ?, sceau = ?, signature = ? "
                         "WHERE id = ?", (json.dumps(ev["details"], ensure_ascii=False), ev["sceau_precedent"],
                                          ev["sceau"], ev["signature"], ev["id"]))
    with journal_scelle.ouvrir_lecture(config.CHEMIN_DB) as conn:
        assert journal_scelle.verifier_evenements(conn)["intacte"]  # la chaîne locale ne voit rien
        base = ancrage.verifier_base(conn, rpc)
    assert base["signatures"]["falsifiees"] == 0  # signatures refaites avec les vraies clés
    assert base["statut"] == "altere"
    date = base["lots"][0]["date"]
    assert base["alteration"]["libelle"] == f"altéré à l'étape 3 : ne correspond pas à l'ancre du {date}"
    assert [e["id"] for e in base["lots"][0]["ecarts"]] == [3]  # seule l'entrée réécrite est en cause

    v = _verifier(client, iid)
    assert v["statut"] == "alteree"
    assert v["verdict"] == (f"altérée à l'étape {_rang(client, iid, 3)} : champ exfiltration modifié, "
                            f"ne correspond pas à l'ancre du {date}")
    assert v["ancrage"]["statut"] == "altere"

    # La même base, avec aussi la table des ancres réécrite : la chaîne garde la vraie racine.
    with _base_admin() as conn:
        entrees = ancrage._entrees_plage(conn, conn.execute("SELECT * FROM ancres").fetchone())
        feuilles = [[e["nature"], e["id"], e["feuille"]] for e in entrees]
        conn.execute("UPDATE ancres SET feuilles = ?, racine = ?", (json.dumps(feuilles),
                     ancrage.racine_merkle([f[2] for f in feuilles])))
    with journal_scelle.ouvrir_lecture(config.CHEMIN_DB) as conn:
        assert ancrage.verifier_base(conn, rpc)["statut"] == "altere"
        # Sans relire la chaîne, la base se contredit plus : c'est la limite du hors-ligne.
        assert ancrage.verifier_base(conn, None)["statut"] == "ancre"


def test_ancre_retiree_de_la_base_est_vue(client):
    iid = _incident(client)
    _verifier(client, iid)
    rpc = FauxRPC()
    ancrage.cycle(config.CHEMIN_DB, rpc=rpc, envoyer=True, attendre_s=0)
    with _base_admin() as conn:
        conn.execute("DELETE FROM ancres")
    with journal_scelle.ouvrir_lecture(config.CHEMIN_DB) as conn:
        base = ancrage.verifier_base(conn, rpc)
    assert base["statut"] == "altere" and base["ancres_manquantes"] == 1


# ---------------------------------------------------------------- Déclenchement et commandes
def test_incident_clos_declenche_un_ancrage(monkeypatch):
    rpc = FauxRPC()
    monkeypatch.setenv("DEDALE_ANCRAGE", "auto")
    monkeypatch.setattr(ancrage, "fabrique_rpc", lambda: rpc)
    monkeypatch.setattr(ancrage, "TICK", 0.05)
    monkeypatch.setattr(ancrage, "REGROUPEMENT", 0.0)
    monkeypatch.setattr(ancrage, "ESPACEMENT", 0.0)
    with TestClient(main.app) as client:
        iid = _incident(client)
        assert rpc.txs == {}  # rien ne part tant que le dossier est ouvert
        client.post(f"/api/incidents/{iid}/decision", json={"action": "couper", "analyste": "alice"})
        fin = time.monotonic() + 10
        while not rpc.txs and time.monotonic() < fin:
            time.sleep(0.05)
        assert len(rpc.txs) == 1
        fin = time.monotonic() + 5
        while time.monotonic() < fin:
            v = _verifier(client, iid)
            if v["ancrage"]["statut"] == "ancre":
                break
            time.sleep(0.05)
        assert v["statut"] == "intacte" and v["ancrage"]["statut"] == "ancre", v["ancrage"]
        r = client.get("/api/ancrage").json()
        assert r["file"]["confirmee"] == 1 and r["adresse"] == ancrage.adresse_ancrage()
        assert set(r["cles"]) == set(ancrage.EMETTEURS)


def test_commandes_verifier_journal_et_ancrage(client, capsys):
    iid = _incident(client)
    _verifier(client, iid)
    assert verifier_journal.main(["--db", str(config.CHEMIN_DB)]) == 0
    sortie = capsys.readouterr().out
    assert "Signatures Ed25519 : 3 valides (passerelle 3), 0 falsifiée" in sortie
    assert "Ajout seul : déclencheurs en place" in sortie
    assert "Ancrage Avalanche : en exploration, aucune ancre publiée (0 racine en file locale)" in sortie

    rpc = FauxRPC()
    ancrage.fabrique_rpc = lambda: rpc
    assert ancrage.main(["adresse"]) == 0
    assert capsys.readouterr().out.strip() == ancrage.adresse_ancrage()
    assert ancrage.main(["ancrer", "--db", str(config.CHEMIN_DB)]) == 0
    assert "ancré : bloc" in capsys.readouterr().out
    assert ancrage.main(["etat", "--db", str(config.CHEMIN_DB)]) == 0
    sortie = capsys.readouterr().out
    assert "Bloc courant" in sortie and "1 confirmé(s)" in sortie

    assert verifier_journal.main(["--db", str(config.CHEMIN_DB)]) == 0
    sortie = capsys.readouterr().out
    assert "Ancrage : Journal intact, ancré sur Avalanche (bloc" in sortie
    assert "https://testnet.snowtrace.io/tx/0x" in sortie
