"""Ancrage du journal : écritures signées, ajout seul, racines publiées sur Avalanche.

Le journal scellé (journal_scelle.py) chaîne déjà chaque entrée à la précédente par SHA-256.
Ce module ajoute trois protections :

1. Écritures signées. Chaque entrée (événement ou décision) porte la signature Ed25519 de
   son émetteur : `passerelle` (agent interne d'Orbis), `poste` (app du poste, extension,
   messagerie), `leurres` (surface exposée) ou `backend` (décision ou acte d'un analyste,
   relecteur). Une clé par émetteur, créée au premier usage dans `~/.config/dedale/cles/`
   (dossier 700, fichiers 600), jamais dans le dépôt. Les agents IA n'écrivent jamais dans
   le journal : ils passent par la passerelle, qui poste au backend, seul à écrire en base.
   Le backend signe au nom du canal par lequel l'entrée est arrivée.
2. Ajout seul. Des déclencheurs SQLite refusent UPDATE et DELETE sur `evenements` et
   `decisions`, et ignorent la réécriture d'une ligne existante par INSERT OR REPLACE. Un
   administrateur de la base peut retirer ces déclencheurs : c'est la raison du point 3.
3. Ancrage. Les entrées pas encore ancrées forment un lot, dont la racine de Merkle part sur
   la C-Chain de test Fuji d'Avalanche, dans une transaction de 0 AVAX de l'adresse
   d'ancrage vers elle-même. Seules l'étiquette `dedale-ancre-v1:` et la racine (32 octets)
   quittent la machine : ni contenu, ni nom, ni donnée personnelle. Une base réécrite en
   entier, sceaux et signatures recalculés, ne retombe plus sur la racine publiée.

Sans fonds ou sans réseau, les lots attendent dans la table `ancres` et repartent au cycle
suivant, sans erreur bruyante. Réglages :

- `DEDALE_ANCRAGE` : `auto` (défaut, prépare et envoie), `file` (prépare sans rien envoyer),
  `off` (rien, sauf la commande `python -m app.ancrage ancrer`) ;
- `DEDALE_ANCRAGE_RPC` : nœud JSON-RPC (défaut : RPC public Fuji). Le chainId reste 43113 :
  un nœud qui annonce une autre chaîne est refusé, aucune transaction ne part ;
- `DEDALE_ANCRAGE_PERIODE` : secondes entre deux lots périodiques (défaut 600) ;
- `DEDALE_CLES`, `DEDALE_ANCRAGE_CLE` : emplacements des clés (défaut `~/.config/dedale/`).

Commandes : `uv run python -m app.ancrage adresse|etat|ancrer`.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from . import config, journal_scelle

_journal = logging.getLogger(__name__)

# ---------------------------------------------------------------- Réglages
RPC_FUJI = "https://api.avax-test.network/ext/bc/C/rpc"
CHAIN_ID = 43113  # Fuji. Fixe : on ne dépense jamais d'AVAX réels par erreur de réglage.
EXPLORATEUR = "https://testnet.snowtrace.io/tx/"
RESEAU = "Avalanche Fuji (C-Chain de test, chainId 43113)"
ETIQUETTE = b"dedale-ancre-v1:"  # 16 octets, suivis des 32 octets de la racine
VERSION_SIGNATURE = "dedale-journal-v1"
EMETTEURS = ("passerelle", "poste", "leurres", "backend")
TABLES_AJOUT_SEUL = ("evenements", "decisions")

TICK = 2.0  # pas de la boucle de fond, en secondes
REGROUPEMENT = 1.0  # attente après une clôture, pour grouper les clôtures voisines
ESPACEMENT = 20.0  # écart minimal entre deux lots déclenchés par des clôtures
DELAI_TROU = 120.0  # un identifiant manquant depuis plus longtemps est tenu pour perdu

# Fabrique d'un client RPC, remplaçable par les tests (faux client sans réseau).
fabrique_rpc: Callable[[], Any] | None = None


def _dossier_config() -> Path:
    return Path(os.environ.get("DEDALE_CONFIG", str(Path.home() / ".config" / "dedale"))).expanduser()


def dossier_cles() -> Path:
    return Path(os.environ.get("DEDALE_CLES", str(_dossier_config() / "cles"))).expanduser()


def fichier_cle_ancrage() -> Path:
    return Path(os.environ.get("DEDALE_ANCRAGE_CLE", str(_dossier_config() / "ancrage.key"))).expanduser()


def mode() -> str:
    valeur = os.environ.get("DEDALE_ANCRAGE", "auto").strip().lower()
    return valeur if valeur in ("auto", "file", "off") else "auto"


def periode() -> float:
    try:
        return max(30.0, float(os.environ.get("DEDALE_ANCRAGE_PERIODE", "600")))
    except ValueError:
        return 600.0


def lien_tx(tx: str | None) -> str | None:
    return f"{EXPLORATEUR}{tx}" if tx else None


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


def _date_lisible(iso: str | None) -> str:
    """« 10/10/2026 à 23:41 », à l'heure de la machine."""
    if not iso:
        return "date inconnue"
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y à %H:%M")
    except ValueError:
        return iso


# ---------------------------------------------------------------- Fichiers secrets
def _ecrire_secret(chemin: Path, contenu: bytes) -> None:
    """Crée un fichier lisible par son seul propriétaire (600), sans jamais en écraser un.

    Écriture dans un fichier temporaire puis lien dur : deux processus qui créent la même clé
    en même temps gardent la première, entière.
    """
    chemin.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(chemin.parent, 0o700)
    temp = chemin.with_name(f".{chemin.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        with contextlib.suppress(FileExistsError):
            os.link(temp, chemin)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temp)


def _lire_secret(chemin: Path) -> bytes:
    if chemin.stat().st_mode & 0o077:
        os.chmod(chemin, 0o600)  # une clé lisible par d'autres est ramenée à 600
    return chemin.read_bytes()


# ---------------------------------------------------------------- Clés Ed25519 des émetteurs
_cles_privees: dict[tuple[str, str], Any] = {}
_cles_publiques: dict[tuple[str, str], Any] = {}


def cle_privee(emetteur: str):
    """Clé de signature d'un émetteur, créée au premier usage (`<emetteur>.key`, 600)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if emetteur not in EMETTEURS:
        raise ValueError(f"Émetteur inconnu : {emetteur}")
    dossier = dossier_cles()
    cle_cache = (str(dossier), emetteur)
    if cle_cache in _cles_privees:
        return _cles_privees[cle_cache]
    chemin = dossier / f"{emetteur}.key"
    if not chemin.exists():
        neuve = Ed25519PrivateKey.generate()
        _ecrire_secret(chemin, neuve.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        publique = chemin.with_suffix(".pub")
        if not publique.exists():
            brut = serialization.load_pem_private_key(_lire_secret(chemin), None).public_key()
            _ecrire_secret(publique, brut.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex().encode() + b"\n")
    cle = serialization.load_pem_private_key(_lire_secret(chemin), None)
    _cles_privees[cle_cache] = cle
    return cle


def cle_publique(emetteur: str):
    """Clé publique d'un émetteur, lue dans `<emetteur>.pub`, sinon tirée de sa clé privée.

    La vérification ne lit jamais une clé publique dans la base : celui qui réécrit la base
    ne peut pas y glisser la sienne. None si l'émetteur n'a pas de clé sur cette machine.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if emetteur not in EMETTEURS:
        return None
    dossier = dossier_cles()
    cle_cache = (str(dossier), emetteur)
    if cle_cache in _cles_publiques:
        return _cles_publiques[cle_cache]
    pub, priv = dossier / f"{emetteur}.pub", dossier / f"{emetteur}.key"
    cle = None
    try:
        if pub.exists():
            cle = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub.read_text().strip()))
        elif priv.exists():
            cle = cle_privee(emetteur).public_key()
    except (ValueError, OSError):
        cle = None
    if cle is not None:
        _cles_publiques[cle_cache] = cle
    return cle


def empreinte_cle(emetteur: str) -> str | None:
    """Empreinte courte de la clé publique (16 caractères), pour l'afficher sans la clé."""
    from cryptography.hazmat.primitives import serialization

    cle = cle_publique(emetteur)
    if cle is None:
        return None
    brut = cle.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return hashlib.sha256(brut).hexdigest()[:16]


# ---------------------------------------------------------------- Signer une entrée
def _court(texte: Any, limite: int = 80) -> str | None:
    if texte is None:
        return None
    texte = str(texte).strip()
    return texte[:limite] or None


def emetteur_evenement(ev: dict) -> tuple[str, str | None]:
    """(émetteur, auteur) d'un événement, déduits de son contenu scellé.

    L'auteur n'est connu que pour ce que le backend écrit lui-même : le nom de l'analyste
    pour un acte de la console, le relecteur pour une relecture.
    """
    details = ev.get("details") if isinstance(ev.get("details"), dict) else {}
    surface, source, type_ = ev.get("surface"), ev.get("source"), ev.get("type")
    if surface in ("console", "soc") or type_ in ("console", "correctif", "relecture"):
        auteur = details.get("analyste")
        if not auteur and details.get("relecteur"):
            auteur = f"relecteur {details['relecteur']}"
        return "backend", _court(auteur)
    if source == "interne":
        return "passerelle", None
    if source in ("humain", "physique") or surface == "poste":
        return "poste", None
    if source == "externe":
        return "leurres", None
    return "backend", None


def _message(nature: str, empreinte: str, emetteur: str, auteur: str | None) -> bytes:
    return "\n".join((VERSION_SIGNATURE, nature, empreinte or "", emetteur, auteur or "")).encode("utf-8")


def signer_entree(element: dict, nature: str) -> None:
    """Pose `signataire` et `signature` (128 hex) sur une entrée qui vient d'être scellée.

    Appelé par journal_scelle.sceller_evenement et sceller_decision. Une clé illisible ne
    bloque jamais l'ingestion : l'entrée part sans signature et la vérification le dira.
    """
    try:
        if nature == "evenement":
            emetteur, auteur = emetteur_evenement(element)
        else:
            emetteur, auteur = "backend", _court(element.get("analyste"))
        signature = cle_privee(emetteur).sign(_message(nature, element["sceau"], emetteur, auteur))
        element["signataire"] = emetteur
        element["signature"] = signature.hex()
    except Exception:  # pragma: no cover - dépend du disque
        _journal.exception("Signature impossible : entrée gardée sans signature")
        element["signataire"] = None
        element["signature"] = None


# ---------------------------------------------------------------- Ajout seul (SQLite)
def installer_ajout_seul(conn: sqlite3.Connection) -> None:
    """Déclencheurs d'ajout seul sur `evenements` et `decisions`.

    UPDATE et DELETE échouent avec un message clair. Un INSERT OR REPLACE sur une ligne
    existante est ignoré : la première écriture reste (et l'écrivain du backend ne tombe pas
    si une même entrée lui arrive deux fois).
    """
    for table in TABLES_AJOUT_SEUL:
        conn.execute(
            f"CREATE TRIGGER IF NOT EXISTS {table}_ajout_seul_modif BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'journal en ajout seul : modification interdite sur {table}'); END")
        conn.execute(
            f"CREATE TRIGGER IF NOT EXISTS {table}_ajout_seul_suppr BEFORE DELETE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, 'journal en ajout seul : suppression interdite sur {table}'); END")
        conn.execute(
            f"CREATE TRIGGER IF NOT EXISTS {table}_ajout_seul_reecr BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE id = NEW.id) "
            f"BEGIN SELECT RAISE(IGNORE); END")


def retirer_ajout_seul(conn: sqlite3.Connection) -> None:
    """Ce qu'un administrateur de la base peut toujours faire. Sert aux tests d'altération."""
    for table in TABLES_AJOUT_SEUL:
        for suffixe in ("modif", "suppr", "reecr"):
            conn.execute(f"DROP TRIGGER IF EXISTS {table}_ajout_seul_{suffixe}")


def ajout_seul_actif(conn: sqlite3.Connection) -> bool:
    noms = {f"{t}_ajout_seul_{s}" for t in TABLES_AJOUT_SEUL for s in ("modif", "suppr", "reecr")}
    presents = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    return noms <= presents


_SCHEMA_ANCRES = """
CREATE TABLE IF NOT EXISTS ancres (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cree_a TEXT NOT NULL, motif TEXT,
  ev_de INTEGER, ev_a INTEGER, dec_de INTEGER, dec_a INTEGER,
  n_feuilles INTEGER NOT NULL, racine TEXT NOT NULL, feuilles TEXT NOT NULL,
  statut TEXT NOT NULL DEFAULT 'en_attente', raison TEXT,
  tentatives INTEGER NOT NULL DEFAULT 0, tente_a TEXT, envois INTEGER NOT NULL DEFAULT 0,
  adresse TEXT, tx TEXT, nonce INTEGER, envoye_a TEXT, bloc INTEGER, confirme_a TEXT
);
"""


def preparer(conn: sqlite3.Connection) -> None:
    """Appelé par db.ouvrir : table des ancres et déclencheurs d'ajout seul."""
    conn.executescript(_SCHEMA_ANCRES)
    installer_ajout_seul(conn)
    conn.commit()


# ---------------------------------------------------------------- Merkle
def feuille(nature: str, ident: int, empreinte: str, signataire: str | None, signature: str | None) -> str:
    """Feuille d'une entrée : SHA-256(0x00 ‖ JSON canonique). Le préfixe 0x00 sépare les
    feuilles des nœuds (0x01) : un nœud ne peut pas se faire passer pour une entrée."""
    contenu = journal_scelle.canonique({"nature": nature, "id": ident, "empreinte": empreinte,
                                        "signataire": signataire, "signature": signature})
    return hashlib.sha256(b"\x00" + contenu.encode("utf-8")).hexdigest()


def racine_merkle(feuilles: list[str]) -> str:
    """Racine d'une liste de feuilles (hex). Un nœud seul en bout de niveau monte tel quel."""
    if not feuilles:
        raise ValueError("Un lot vide n'a pas de racine")
    niveau = [bytes.fromhex(f) for f in feuilles]
    while len(niveau) > 1:
        suivant = [hashlib.sha256(b"\x01" + niveau[i] + niveau[i + 1]).digest()
                   for i in range(0, len(niveau) - 1, 2)]
        if len(niveau) % 2:
            suivant.append(niveau[-1])
        niveau = suivant
    return niveau[0].hex()


# ---------------------------------------------------------------- Entrées lues en base
def _colonnes(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _table_existe(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                        (table,)).fetchone() is not None


def _entree_evenement(row) -> dict:
    ev = journal_scelle._ligne_evenement(row)
    recalc = journal_scelle.empreinte(ev.get("sceau_precedent"), ev.get("recu_a"),
                                      journal_scelle._contenu_evenement(ev))
    emetteur, auteur = emetteur_evenement(ev)
    return {"nature": "evenement", "id": ev["id"], "empreinte": recalc, "signataire": ev.get("signataire"),
            "signature": ev.get("signature"), "emetteur": emetteur, "auteur": auteur,
            "recu_a": ev.get("recu_a"),
            "feuille": feuille("evenement", ev["id"], recalc, ev.get("signataire"), ev.get("signature"))}


def _entree_decision(row) -> dict:
    d = dict(row)
    recalc = journal_scelle.empreinte(d.get("sceau_precedent"), d.get("horodatage"),
                                      journal_scelle._contenu_decision(d))
    return {"nature": "decision", "id": d["id"], "empreinte": recalc, "signataire": d.get("signataire"),
            "signature": d.get("signature"), "emetteur": "backend", "auteur": _court(d.get("analyste")),
            "incident_id": d.get("incident_id"),
            "feuille": feuille("decision", d["id"], recalc, d.get("signataire"), d.get("signature"))}


def _entrees_plage(conn: sqlite3.Connection, lot) -> list[dict]:
    entrees = []
    if lot["ev_de"] is not None:
        entrees += [_entree_evenement(r) for r in conn.execute(
            "SELECT * FROM evenements WHERE id BETWEEN ? AND ? ORDER BY id", (lot["ev_de"], lot["ev_a"]))]
    if lot["dec_de"] is not None:
        entrees += [_entree_decision(r) for r in conn.execute(
            "SELECT * FROM decisions WHERE id BETWEEN ? AND ? ORDER BY id", (lot["dec_de"], lot["dec_a"]))]
    return entrees


def _premiers_signes(conn: sqlite3.Connection) -> dict:
    """Plus petit identifiant signé de chaque table : en dessous, une entrée sans signature
    est antérieure à la signature ; au-dessus, sa signature a été retirée."""
    premiers = {}
    for nature, table in (("evenement", "evenements"), ("decision", "decisions")):
        if "signature" in _colonnes(conn, table):
            premiers[nature] = conn.execute(
                f"SELECT MIN(id) FROM {table} WHERE signature IS NOT NULL").fetchone()[0]
        else:
            premiers[nature] = None
    return premiers


def etat_signature(entree: dict, premiers: dict) -> str:
    """`valide`, `falsifiee`, `retiree`, `absente` (antérieure) ou `cle_inconnue`."""
    from cryptography.exceptions import InvalidSignature

    if not entree.get("signature"):
        premier = premiers.get(entree["nature"])
        return "retiree" if premier is not None and entree["id"] > premier else "absente"
    if entree.get("signataire") != entree["emetteur"]:
        return "falsifiee"
    cle = cle_publique(entree["emetteur"])
    if cle is None:
        return "cle_inconnue"
    try:
        cle.verify(bytes.fromhex(entree["signature"]),
                   _message(entree["nature"], entree["empreinte"], entree["emetteur"], entree["auteur"]))
        return "valide"
    except (InvalidSignature, ValueError):
        return "falsifiee"


def resume_signatures(entrees: list[dict], premiers: dict, detail: bool = True) -> dict:
    """Compte des signatures et, entrée par entrée, qui l'a écrite."""
    compte = {"valides": 0, "falsifiees": 0, "retirees": 0, "absentes": 0, "cles_inconnues": 0}
    cles = {"valide": "valides", "falsifiee": "falsifiees", "retiree": "retirees",
            "absente": "absentes", "cle_inconnue": "cles_inconnues"}
    par_emetteur: dict[str, int] = {}
    lignes = []
    for e in entrees:
        etat = etat_signature(e, premiers)
        compte[cles[etat]] += 1
        if etat == "valide":
            par_emetteur[e["emetteur"]] = par_emetteur.get(e["emetteur"], 0) + 1
        if detail:
            lignes.append({"nature": e["nature"], "id": e["id"], "emetteur": e["emetteur"],
                           "auteur": e["auteur"], "signataire": e.get("signataire"), "signature": etat})
    sortie = {**compte, "par_emetteur": par_emetteur, "algorithme": "Ed25519"}
    if detail:
        sortie["entrees"] = lignes
    return sortie


# ---------------------------------------------------------------- Préparer un lot
def _ecrit_depuis(entree: dict, secondes: float) -> bool:
    try:
        recu = datetime.fromisoformat(str(entree.get("recu_a")).replace("Z", "+00:00"))
    except ValueError:
        return True
    if recu.tzinfo is None:
        recu = recu.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - recu).total_seconds() > secondes


def preparer_lot(conn: sqlite3.Connection, motif: str = "periodique") -> dict | None:
    """Calcule la racine des entrées pas encore ancrées et la met en file. None si rien de neuf.

    Les événements entrent dans l'ordre de leurs identifiants, sans trou : un identifiant
    absent arrête le lot, le temps que l'écrivain le pose. Absent depuis plus de deux minutes,
    il est tenu pour perdu et le lot passe outre.
    """
    if not _table_existe(conn, "ancres"):
        preparer(conn)
    fin_ev = conn.execute("SELECT MAX(ev_a) FROM ancres").fetchone()[0] or 0
    fin_dec = conn.execute("SELECT MAX(dec_a) FROM ancres").fetchone()[0] or 0
    evenements, attendu = [], fin_ev + 1
    for row in conn.execute("SELECT * FROM evenements WHERE id > ? ORDER BY id", (fin_ev,)):
        e = _entree_evenement(row)
        if e["id"] != attendu and not _ecrit_depuis(e, DELAI_TROU):
            break
        evenements.append(e)
        attendu = e["id"] + 1
    decisions = [_entree_decision(r) for r in conn.execute(
        "SELECT * FROM decisions WHERE id > ? ORDER BY id", (fin_dec,))]
    entrees = evenements + decisions
    if not entrees:
        return None
    feuilles = [[e["nature"], e["id"], e["feuille"]] for e in entrees]
    racine = racine_merkle([f[2] for f in feuilles])
    lot = {
        "cree_a": _maintenant(), "motif": motif,
        "ev_de": evenements[0]["id"] if evenements else None,
        "ev_a": evenements[-1]["id"] if evenements else None,
        "dec_de": decisions[0]["id"] if decisions else None,
        "dec_a": decisions[-1]["id"] if decisions else None,
        "n_feuilles": len(feuilles), "racine": racine,
    }
    cur = conn.execute(
        "INSERT INTO ancres (cree_a, motif, ev_de, ev_a, dec_de, dec_a, n_feuilles, racine, feuilles, raison) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (lot["cree_a"], motif, lot["ev_de"], lot["ev_a"], lot["dec_de"], lot["dec_a"], lot["n_feuilles"],
         racine, json.dumps(feuilles), "desactive" if mode() != "auto" else None))
    conn.commit()
    lot["id"] = cur.lastrowid
    return lot


# ---------------------------------------------------------------- Client JSON-RPC
class ErreurRPC(Exception):
    """Le nœud a refusé l'appel ou n'a pas répondu."""


class ClientRPC:
    """Client JSON-RPC minimal (httpx), délai court : l'ancrage n'attend jamais longtemps."""

    def __init__(self, url: str | None = None, delai: float = 6.0):
        self.url = url or os.environ.get("DEDALE_ANCRAGE_RPC", RPC_FUJI)
        self.delai = delai
        self._n = 0

    def appel(self, methode: str, params: list | None = None):
        import httpx

        self._n += 1
        try:
            r = httpx.post(self.url, json={"jsonrpc": "2.0", "id": self._n, "method": methode,
                                           "params": params or []}, timeout=self.delai)
            r.raise_for_status()
            corps = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ErreurRPC(f"réseau : {type(exc).__name__}") from exc
        if isinstance(corps, dict) and corps.get("error"):
            erreur = corps["error"]
            texte = erreur.get("message", "erreur") if isinstance(erreur, dict) else str(erreur)
            raise ErreurRPC(str(texte)[:200])
        return corps.get("result") if isinstance(corps, dict) else None


def client_rpc():
    """Client à utiliser, ou None quand l'ancrage est coupé (`DEDALE_ANCRAGE=off` ou `file`)."""
    if fabrique_rpc is not None:
        return fabrique_rpc()
    return ClientRPC() if mode() == "auto" else None


def _entier(valeur) -> int:
    return int(valeur, 16) if isinstance(valeur, str) else int(valeur or 0)


# ---------------------------------------------------------------- Portefeuille d'ancrage
def compte_ancrage(creer: bool = True):
    """Compte secp256k1 de l'ancrage. Clé dans `ancrage.key` (600), jamais affichée."""
    from eth_account import Account

    chemin = fichier_cle_ancrage()
    if not chemin.exists():
        if not creer:
            return None
        _ecrire_secret(chemin, ("0x" + bytes(Account.create().key).hex() + "\n").encode())
    return Account.from_key(_lire_secret(chemin).decode().strip())


def adresse_ancrage(creer: bool = False) -> str | None:
    compte = compte_ancrage(creer=creer)
    return compte.address if compte is not None else None


@contextlib.contextmanager
def _verrou_envoi():
    """Un seul processus envoie à la fois (backend, commande) : pas deux transactions par lot."""
    chemin = fichier_cle_ancrage().with_name("ancrage.lock")
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(chemin, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def donnees_tx(racine: str) -> str:
    return "0x" + (ETIQUETTE + bytes.fromhex(racine)).hex()


def _mettre_en_attente(conn, ids: list[int], raison: str) -> None:
    if ids:
        marques = ",".join("?" * len(ids))
        conn.execute(f"UPDATE ancres SET raison = ?, tentatives = tentatives + 1, tente_a = ? "
                     f"WHERE id IN ({marques})", (raison, _maintenant(), *ids))
        conn.commit()


def envoyer_en_attente(conn: sqlite3.Connection, rpc, max_lots: int = 5) -> dict:
    """Publie les lots en attente, du plus ancien au plus récent. Ne lève jamais d'erreur
    réseau : un lot qui ne part pas garde sa raison (`fonds`, `reseau`, `refusee`…)."""
    lots = conn.execute("SELECT * FROM ancres WHERE statut = 'en_attente' ORDER BY id LIMIT ?",
                        (max_lots,)).fetchall()
    if not lots:
        return {"envoyes": 0, "raison": None}
    compte = compte_ancrage(creer=True)
    adresse = compte.address
    restants = [l["id"] for l in lots]
    envoyes = 0
    try:
        if _entier(rpc.appel("eth_chainId")) != CHAIN_ID:
            _mettre_en_attente(conn, restants, "reseau_inattendu")
            return {"envoyes": 0, "raison": "reseau_inattendu"}
        for lot in lots:
            data = donnees_tx(lot["racine"])
            prix = max(1, _entier(rpc.appel("eth_gasPrice")) * 2)
            try:
                gaz = int(_entier(rpc.appel("eth_estimateGas", [
                    {"from": adresse, "to": adresse, "value": "0x0", "data": data}])) * 1.2)
            except ErreurRPC:
                gaz = 30_000
            solde = _entier(rpc.appel("eth_getBalance", [adresse, "latest"]))
            if solde < gaz * prix:
                _mettre_en_attente(conn, restants, "fonds")
                return {"envoyes": envoyes, "raison": "fonds"}
            nonce = _entier(rpc.appel("eth_getTransactionCount", [adresse, "pending"]))
            signee = compte.sign_transaction({"to": adresse, "value": 0, "gas": gaz, "gasPrice": prix,
                                              "nonce": nonce, "chainId": CHAIN_ID, "data": data})
            try:
                tx = rpc.appel("eth_sendRawTransaction", ["0x" + bytes(signee.raw_transaction).hex()])
            except ErreurRPC as exc:
                raison = "fonds" if "insufficient funds" in str(exc).lower() else "refusee"
                _mettre_en_attente(conn, restants, raison)
                return {"envoyes": envoyes, "raison": raison}
            tx = tx or "0x" + bytes(signee.hash).hex()
            conn.execute(
                "UPDATE ancres SET statut = 'envoyee', raison = NULL, tx = ?, nonce = ?, adresse = ?, "
                "envoye_a = ?, envois = envois + 1, tentatives = tentatives + 1, tente_a = ? WHERE id = ?",
                (tx, nonce, adresse, _maintenant(), _maintenant(), lot["id"]))
            conn.commit()
            envoyes += 1
            restants.remove(lot["id"])
    except ErreurRPC:
        _mettre_en_attente(conn, restants, "reseau")
        return {"envoyes": envoyes, "raison": "reseau"}
    return {"envoyes": envoyes, "raison": None}


def suivre_envoyes(conn: sqlite3.Connection, rpc, attendre_s: float = 0.0) -> None:
    """Passe en `confirmee` (avec le bloc) les lots dont la transaction est minée."""
    fin = time.monotonic() + attendre_s
    while True:
        lots = conn.execute("SELECT * FROM ancres WHERE statut = 'envoyee' ORDER BY id").fetchall()
        if not lots:
            return
        for lot in lots:
            try:
                recu = rpc.appel("eth_getTransactionReceipt", [lot["tx"]])
                if recu and recu.get("blockNumber"):
                    if _entier(recu.get("status", "0x1")) == 1:
                        conn.execute("UPDATE ancres SET statut = 'confirmee', bloc = ?, confirme_a = ? "
                                     "WHERE id = ?", (_entier(recu["blockNumber"]), _maintenant(), lot["id"]))
                    else:
                        conn.execute("UPDATE ancres SET statut = 'en_attente', raison = 'rejetee', tx = NULL "
                                     "WHERE id = ?", (lot["id"],))
                elif not _ecrit_depuis({"recu_a": lot["envoye_a"]}, 900):
                    continue
                elif rpc.appel("eth_getTransactionByHash", [lot["tx"]]) is None:
                    conn.execute("UPDATE ancres SET statut = 'en_attente', raison = 'perdue', tx = NULL "
                                 "WHERE id = ?", (lot["id"],))
            except ErreurRPC:
                return
            conn.commit()
        if time.monotonic() >= fin:
            return
        time.sleep(1.5)


def _ouvrir_ecriture(chemin: Path | str | None = None) -> sqlite3.Connection:
    """Connexion propre à l'ancrage. Elle n'écrit que dans `ancres`, par de courtes
    transactions, jamais pendant un appel réseau : elle ne gêne pas l'écrivain du backend."""
    conn = sqlite3.connect(str(chemin or config.CHEMIN_DB), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def cycle(chemin_db: Path | str | None = None, *, motif: str = "periodique", rpc=None,
          envoyer: bool | None = None, attendre_s: float = 3.0) -> dict:
    """Un passage : met en file le lot des entrées nouvelles, publie ce qui attend, suit les
    transactions envoyées. `envoyer=None` suit `DEDALE_ANCRAGE` (envoi seulement en `auto`)."""
    chemin = Path(chemin_db or config.CHEMIN_DB)
    if not chemin.is_file():
        return {"lot": None, "envoi": None}
    conn = _ouvrir_ecriture(chemin)
    try:
        lot = preparer_lot(conn, motif)
        envoi = None
        if envoyer is None:
            envoyer = rpc is not None or mode() == "auto"
        if envoyer:
            rpc = rpc or client_rpc() or ClientRPC()
            with _verrou_envoi() as libre:
                if libre:
                    envoi = envoyer_en_attente(conn, rpc)
                    suivre_envoyes(conn, rpc, attendre_s)
        return {"lot": lot, "envoi": envoi}
    finally:
        conn.close()


# ---------------------------------------------------------------- Déclenchement
_demande = {"cloture": 0.0, "dernier_lot": 0.0}
_statuts: dict[str, str] = {}


def noter_statut(iid: str, statut: str) -> None:
    """Appelé à chaque scellement d'incident : une clôture demande un lot d'ancrage."""
    avant = _statuts.get(iid)
    _statuts[iid] = statut
    if statut == "clos" and avant != "clos":
        _demande["cloture"] = time.monotonic()


def demander_lot() -> None:
    _demande["cloture"] = time.monotonic()


def motif_a_traiter(dernier_periodique: float) -> str | None:
    """Ce que la boucle de fond doit faire maintenant : `incident_clos`, `periodique` ou rien."""
    t = time.monotonic()
    if (_demande["cloture"] and t - _demande["cloture"] >= REGROUPEMENT
            and t - _demande["dernier_lot"] >= ESPACEMENT):
        _demande["cloture"] = 0.0
        _demande["dernier_lot"] = t
        return "incident_clos"
    if t - dernier_periodique >= periode():
        return "periodique"
    return None


# ---------------------------------------------------------------- Lire la chaîne
_cache_chaine: dict[str, dict] = {}
_cache_nonce: dict[str, tuple[float, int]] = {}


def lire_ancre(rpc, tx: str, adresse: str | None) -> dict | None:
    """La transaction telle que la chaîne la garde. None si le nœud ne répond pas."""
    if tx in _cache_chaine:
        return _cache_chaine[tx]
    try:
        t = rpc.appel("eth_getTransactionByHash", [tx])
    except ErreurRPC:
        return None
    if t is None:
        return {"trouvee": False}
    brut = bytes.fromhex(str(t.get("input") or t.get("data") or "0x")[2:])
    racine = brut[len(ETIQUETTE):].hex() if brut.startswith(ETIQUETTE) and len(brut) == len(ETIQUETTE) + 32 else None
    emetteur = str(t.get("from") or "").lower()
    lu = {
        "trouvee": True, "racine": racine,
        "bloc": _entier(t["blockNumber"]) if t.get("blockNumber") else None,
        "adresse_ok": adresse is not None and emetteur == adresse.lower()
                      and str(t.get("to") or "").lower() == adresse.lower(),
    }
    if lu["bloc"] is not None:
        _cache_chaine[tx] = lu  # une transaction minée ne change plus
    return lu


def _transactions_publiees(rpc, adresse: str | None) -> int | None:
    """Nombre de transactions envoyées par l'adresse d'ancrage, selon la chaîne (30 s de cache)."""
    if rpc is None or adresse is None:
        return None
    vu = _cache_nonce.get(adresse)
    if vu and time.monotonic() - vu[0] < 30:
        return vu[1]
    try:
        n = _entier(rpc.appel("eth_getTransactionCount", [adresse, "latest"]))
    except ErreurRPC:
        return None
    _cache_nonce[adresse] = (time.monotonic(), n)
    return n


# ---------------------------------------------------------------- Vérifier un lot
def _cle(nature: str, ident: int) -> tuple[int, int]:
    return (0 if nature == "evenement" else 1, int(ident))


def verifier_lot(conn: sqlite3.Connection, lot, rpc=None, adresse: str | None = None) -> dict:
    """Recalcule la racine d'un lot depuis la base et la compare à l'ancre.

    La référence est la racine relue sur la chaîne quand le nœud répond, sinon celle de la
    table `ancres`. Les feuilles gardées en base ne servent à situer l'écart que si elles
    retombent sur la référence : une table d'ancres réécrite ne peut pas tromper la recherche.
    """
    stockees = json.loads(lot["feuilles"])
    entrees = _entrees_plage(conn, lot)
    recalc = racine_merkle([e["feuille"] for e in entrees]) if entrees else None
    reference, source = lot["racine"], "base"
    chaine = None
    if rpc is not None and lot["tx"] and lot["statut"] in ("envoyee", "confirmee"):
        # Sans la clé d'ancrage sur cette machine, l'adresse attendue vient de la table.
        chaine = lire_ancre(rpc, lot["tx"], adresse or lot["adresse"])
        if chaine and chaine.get("trouvee") and chaine.get("racine"):
            reference, source = chaine["racine"], "chaine"
    authentiques = racine_merkle([s[2] for s in stockees]) == reference
    introuvable = bool(chaine is not None and chaine.get("trouvee") is False and lot["statut"] == "confirmee")
    table_modifiee = (not authentiques or introuvable
                      or (source == "chaine" and chaine["racine"] != lot["racine"]))
    ancre_usurpee = bool(chaine and chaine.get("trouvee") and not chaine.get("adresse_ok"))

    ecarts = []
    if authentiques and recalc != reference:
        # Les feuilles gardées retombent sur l'ancre : elles disent quelles entrées ont bougé.
        vues = {_cle(s[0], s[1]): s[2] for s in stockees}
        actuelles = {_cle(e["nature"], e["id"]): e["feuille"] for e in entrees}
        for cle in sorted(set(vues) | set(actuelles)):
            if vues.get(cle) == actuelles.get(cle):
                continue
            raison = ("supprimée de la base" if cle not in actuelles
                      else "ajoutée après l'ancre" if cle not in vues else "modifiée")
            ecarts.append({"nature": "evenement" if cle[0] == 0 else "decision", "id": cle[1],
                           "raison": raison})
    conforme = recalc == reference and not table_modifiee and not ancre_usurpee
    statut = ("altere" if not conforme
              else "ancre" if lot["statut"] == "confirmee" else "en_attente")
    return {
        "id": lot["id"], "statut": statut, "statut_envoi": lot["statut"], "raison_attente": lot["raison"],
        "cree_a": lot["cree_a"], "confirme_a": lot["confirme_a"], "date": _date_lisible(lot["confirme_a"] or lot["cree_a"]),
        "ev_de": lot["ev_de"], "ev_a": lot["ev_a"], "dec_de": lot["dec_de"], "dec_a": lot["dec_a"],
        "n_feuilles": lot["n_feuilles"], "racine": lot["racine"], "racine_recalculee": recalc,
        "reference": source, "chaine_relue": source == "chaine", "table_modifiee": table_modifiee,
        "ancre_usurpee": ancre_usurpee, "tx": lot["tx"], "lien": lien_tx(lot["tx"]), "bloc": lot["bloc"],
        "ecarts": ecarts,
    }


def _lots(conn: sqlite3.Connection) -> list:
    if not _table_existe(conn, "ancres"):
        return []
    return conn.execute("SELECT * FROM ancres ORDER BY id").fetchall()


def _dans(lot, nature: str, ident: int) -> bool:
    de, a = (lot["ev_de"], lot["ev_a"]) if nature == "evenement" else (lot["dec_de"], lot["dec_a"])
    return de is not None and de <= ident <= a


def _ancres_manquantes(conn, rpc, adresse) -> int:
    publiees = _transactions_publiees(rpc, adresse)
    if publiees is None:
        return 0
    connues = conn.execute("SELECT COALESCE(SUM(envois), 0) FROM ancres").fetchone()[0] if _table_existe(conn, "ancres") else 0
    return max(0, publiees - connues)


def _raison_attente(lots: list[dict]) -> str | None:
    for l in reversed(lots):
        if l["statut"] == "en_attente" and l.get("raison_attente"):
            return l["raison_attente"]
    return "desactive" if mode() != "auto" else None


_RAISONS = {
    "fonds": "pas encore d'AVAX de test sur l'adresse d'ancrage",
    "reseau": "réseau Fuji injoignable",
    "reseau_inattendu": "le nœud ne répond pas pour Fuji (chainId 43113)",
    "refusee": "transaction refusée par le nœud",
    "rejetee": "transaction rejetée, nouvel essai au prochain cycle",
    "perdue": "transaction perdue, nouvel essai au prochain cycle",
    "desactive": "ancrage coupé sur ce backend (DEDALE_ANCRAGE)",
}


def libelle_attente(raison: str | None) -> str:
    return _RAISONS.get(raison or "", "envoi au prochain cycle")


# ---------------------------------------------------------------- Vérification de toute la base
def verifier_base(conn: sqlite3.Connection, rpc=None) -> dict:
    """Signatures de toutes les entrées, puis chaque lot recalculé et comparé à son ancre."""
    adresse = adresse_ancrage(creer=False)
    premiers = _premiers_signes(conn)
    entrees = [_entree_evenement(r) for r in conn.execute("SELECT * FROM evenements ORDER BY id")]
    entrees += [_entree_decision(r) for r in conn.execute("SELECT * FROM decisions ORDER BY id")]
    signatures = resume_signatures(entrees, premiers, detail=False)

    lots = [verifier_lot(conn, l, rpc, adresse) for l in _lots(conn)]
    couvertes = sum(1 for e in entrees if any(_dans(l, e["nature"], e["id"]) for l in lots))
    en_attente = len(entrees) - couvertes + sum(l["n_feuilles"] for l in lots if l["statut"] == "en_attente")
    manquantes = _ancres_manquantes(conn, rpc, adresse)
    alteres = [l for l in lots if l["statut"] == "altere"]
    confirmes = [l for l in lots if l["statut"] == "ancre"]
    dernier = confirmes[-1] if confirmes else None

    alteration = None
    if alteres:
        l = alteres[0]
        premier = l["ecarts"][0] if l["ecarts"] else None
        if premier and premier["nature"] == "evenement":
            ou = f"altéré à l'étape {premier['id']}"
        elif premier:
            ou = f"altéré à la décision {premier['id']}"
        else:
            ou = f"altéré entre les entrées du lot {l['id']}"
        quoi = "table des ancres réécrite" if l["table_modifiee"] and not premier else (premier or {}).get("raison")
        alteration = {"lot": l["id"], "entree": premier, "raison": quoi, "date": l["date"], "lien": l["lien"],
                      "libelle": f"{ou} : ne correspond pas à l'ancre du {l['date']}"}
    elif manquantes:
        alteration = {"lot": None, "entree": None, "raison": "ancres retirées de la base", "date": None,
                      "lien": None, "libelle": f"altéré : {manquantes} ancre(s) publiée(s) sur Avalanche "
                                               f"manquent dans la base"}

    if alteration:
        statut, libelle = "altere", alteration["libelle"]
    elif dernier and not en_attente:
        statut, libelle = "ancre", f"ancré sur Avalanche (bloc {dernier['bloc']})"
    elif dernier:
        statut = "en_attente"
        libelle = (f"ancré sur Avalanche (bloc {dernier['bloc']}), {en_attente} entrée(s) récente(s) "
                   f"en attente d'ancrage")
    elif entrees:
        statut, libelle = "en_attente", "en attente d'ancrage"
    else:
        statut, libelle = "vide", "journal vide, rien à ancrer"
    return {
        "statut": statut, "libelle": libelle, "reseau": RESEAU, "adresse": adresse,
        "chaine_relue": any(l["chaine_relue"] for l in lots),
        "ajout_seul": ajout_seul_actif(conn), "signatures": signatures,
        "lots": lots, "entrees": len(entrees), "entrees_en_attente": en_attente,
        "raison_attente": _raison_attente(lots) if en_attente else None,
        "derniere_ancre": ({"bloc": dernier["bloc"], "tx": dernier["tx"], "lien": dernier["lien"],
                            "date": dernier["date"]} if dernier else None),
        "ancres_manquantes": manquantes, "alteration": alteration,
    }


# ---------------------------------------------------------------- Vérification d'un incident
def _etape(chaine: list, nature: str, ident: int, decisions_inc: list[int]) -> tuple[int | None, str]:
    """Où se trouve une entrée dans le dossier : rang du maillon, ou numéro de décision."""
    if nature == "decision":
        n = decisions_inc.index(ident) + 1 if ident in decisions_inc else None
        return n, (f"altérée à la décision {n}" if n else f"altérée : décision {ident}")
    for rang, m in enumerate(chaine, start=1):
        if isinstance(m, dict) and m.get("evenement_id") == ident:
            return rang, f"altérée à l'étape {rang}"
    return None, f"altérée : événement {ident}"


def completer_verification(conn: sqlite3.Connection, iid: str, res: dict, rpc=None) -> dict:
    """Ajoute `signatures` et `ancrage` au verdict de journal_scelle.verifier_incident.

    Une signature fausse ou une entrée qui ne retombe plus sur son ancre fait passer le
    dossier en `alteree`, même quand les chaînes de hachage, recalculées, sont cohérentes.
    """
    row = conn.execute("SELECT session_id, chaine FROM incidents WHERE id = ?", (iid,)).fetchone()
    if row is None:
        return res
    try:
        chaine = json.loads(row["chaine"] or "[]")
    except (TypeError, ValueError):
        chaine = []
    entrees = [_entree_evenement(r) for r in conn.execute(
        "SELECT * FROM evenements WHERE session_id = ? ORDER BY id", (row["session_id"],))]
    decs = [_entree_decision(r) for r in conn.execute(
        "SELECT * FROM decisions WHERE incident_id = ? ORDER BY id", (iid,))]
    entrees += decs
    ids_decisions = [d["id"] for d in decs]
    signatures = resume_signatures(entrees, _premiers_signes(conn))
    res["signatures"] = signatures

    adresse = adresse_ancrage(creer=False)
    lots_bruts = _lots(conn)
    lots = {}
    alteration = None
    ancrees, en_attente = [], 0
    for e in entrees:
        lot = next((l for l in lots_bruts if _dans(l, e["nature"], e["id"])), None)
        if lot is None:
            en_attente += 1
            continue
        if lot["id"] not in lots:
            lots[lot["id"]] = verifier_lot(conn, lot, rpc, adresse)
        v = lots[lot["id"]]
        ecart = next((x for x in v["ecarts"] if x["nature"] == e["nature"] and x["id"] == e["id"]), None)
        suspect = ecart is not None or (v["statut"] == "altere" and not v["ecarts"])
        if suspect and alteration is None:
            if ecart is not None:
                etape, verdict = _etape(chaine, e["nature"], e["id"], ids_decisions)
            else:  # table des ancres réécrite : l'écart ne se situe plus
                etape, verdict = None, "altérée"
            alteration = {"nature": e["nature"], "id": e["id"], "etape": etape, "lot": v["id"],
                          "raison": ecart["raison"] if ecart else "table des ancres réécrite",
                          "date": v["date"], "lien": v["lien"],
                          "verdict": f"{verdict} : ne correspond pas à l'ancre du {v['date']}"}
        if v["statut_envoi"] == "confirmee":
            ancrees.append(v)
        else:
            en_attente += 1
    manquantes = _ancres_manquantes(conn, rpc, adresse) if alteration is None else 0
    if alteration is None and manquantes:
        alteration = {"nature": None, "id": None, "etape": None, "lot": None,
                      "raison": "ancres retirées de la base", "date": None, "lien": None,
                      "verdict": f"altérée : {manquantes} ancre(s) publiée(s) sur Avalanche manquent dans la base"}

    derniere = max(ancrees, key=lambda v: (v["bloc"] or 0)) if ancrees else None
    if alteration:
        statut, libelle = "altere", alteration["verdict"].replace("altérée", "altéré", 1)
    elif not entrees:
        statut, libelle = "sans_entree", "rien à ancrer"
    elif en_attente:
        statut, libelle = "en_attente", "en attente d'ancrage"
    else:
        statut, libelle = "ancre", f"ancré sur Avalanche (bloc {derniere['bloc']})"
    attente = [lots[i] for i in lots if lots[i]["statut_envoi"] != "confirmee"]
    res["ancrage"] = {
        "statut": statut, "libelle": libelle, "reseau": RESEAU, "adresse": adresse,
        "bloc": derniere["bloc"] if derniere else None, "tx": derniere["tx"] if derniere else None,
        "lien": derniere["lien"] if derniere else None, "date": derniere["date"] if derniere else None,
        "chaine_relue": any(v["chaine_relue"] for v in lots.values()),
        "entrees": len(entrees), "entrees_ancrees": len(entrees) - en_attente, "entrees_en_attente": en_attente,
        "raison_attente": (_raison_attente(attente) if en_attente else None),
        "alteration": alteration,
    }

    # Le verdict du dossier : une altération déjà vue garde son rang, l'ancre précise la date.
    sig_ko = next((x for x in signatures["entrees"] if x["signature"] in ("falsifiee", "retiree")), None)
    if res.get("statut") == "alteree":
        if alteration and alteration.get("date") and "ne correspond pas" not in res["verdict"]:
            sep = ", " if " : " in res["verdict"] else " : "
            res["verdict"] = f"{res['verdict']}{sep}ne correspond pas à l'ancre du {alteration['date']}"
    elif sig_ko is not None:
        etape, verdict = _etape(chaine, sig_ko["nature"], sig_ko["id"], ids_decisions)
        if sig_ko["signature"] == "retiree":
            quoi, champ = "signature retirée", "signature"
        elif sig_ko.get("signataire") != sig_ko["emetteur"]:
            quoi, champ = "champ signataire modifié", "signataire"
        else:
            quoi, champ = "signature falsifiée", "signature"
        res.update(statut="alteree", verdict=f"{verdict} : {quoi}", etape_alteree=etape,
                   element_altere="signature", champs_modifies=[champ],
                   raison=f"{'événement' if sig_ko['nature'] == 'evenement' else 'décision'} {sig_ko['id']} : "
                          f"la signature Ed25519 de « {sig_ko['emetteur']} » ne correspond pas")
    elif alteration is not None and res.get("statut") in ("intacte", "anterieure_au_scellement"):
        res.update(statut="alteree", verdict=alteration["verdict"], etape_alteree=alteration["etape"],
                   element_altere="ancre", raison=f"{alteration['raison']} depuis l'ancrage")
    return res


def verifier_dossier(conn: sqlite3.Connection, iid: str, rpc=None) -> dict | None:
    """La vérification d'un dossier, la même pour le badge de la console (route
    `/verification`) et pour `python -m app.verifier_journal` : chaînes SHA-256 relues en
    base (journal_scelle.verifier_incident), puis signatures et ancre."""
    res = journal_scelle.verifier_incident(conn, iid)
    return completer_verification(conn, iid, res, rpc) if res else res


# ---------------------------------------------------------------- État pour la console
def etat(conn: sqlite3.Connection | None) -> dict:
    """État de l'ancrage sans appel réseau : adresse, file, dernières ancres, clés."""
    lots = _lots(conn) if conn is not None else []
    compte = {"en_attente": 0, "envoyee": 0, "confirmee": 0}
    for l in lots:
        compte[l["statut"]] = compte.get(l["statut"], 0) + 1
    confirmes = [l for l in lots if l["statut"] == "confirmee"]
    attente = [l for l in lots if l["statut"] == "en_attente"]
    return {
        "mode": mode(), "reseau": RESEAU, "rpc": os.environ.get("DEDALE_ANCRAGE_RPC", RPC_FUJI),
        "adresse": adresse_ancrage(creer=False), "explorateur": EXPLORATEUR, "periode_s": periode(),
        "ajout_seul": ajout_seul_actif(conn) if conn is not None else False,
        "file": compte,
        "raison_attente": attente[-1]["raison"] if attente else None,
        "derniere_ancre": ({"lot": confirmes[-1]["id"], "bloc": confirmes[-1]["bloc"], "tx": confirmes[-1]["tx"],
                            "lien": lien_tx(confirmes[-1]["tx"]), "date": _date_lisible(confirmes[-1]["confirme_a"])}
                           if confirmes else None),
        "cles": {e: empreinte_cle(e) for e in EMETTEURS},
    }


# ---------------------------------------------------------------- Commande
def _afficher_etat(rpc, adresse: str) -> int:
    try:
        cid = _entier(rpc.appel("eth_chainId"))
        bloc = _entier(rpc.appel("eth_blockNumber"))
        solde = _entier(rpc.appel("eth_getBalance", [adresse, "latest"]))
        envoyees = _entier(rpc.appel("eth_getTransactionCount", [adresse, "latest"]))
    except ErreurRPC as exc:
        print(f"Fuji injoignable : {exc}")
        return 2
    print(f"Réseau : {RESEAU}, chainId lu {cid}{'' if cid == CHAIN_ID else ' (INATTENDU)'}")
    print(f"Bloc courant : {bloc}")
    print(f"Adresse d'ancrage : {adresse}")
    print(f"Solde : {solde / 10**18:.6f} AVAX de test, {envoyees} transaction(s) envoyée(s)")
    return 0 if cid == CHAIN_ID else 1


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(prog="python -m app.ancrage",
                                      description="Ancrage du journal Dédale sur Avalanche Fuji.")
    parseur.add_argument("commande", choices=("adresse", "etat", "ancrer"),
                         help="adresse : adresse à alimenter ; etat : lecture sur Fuji ; "
                              "ancrer : met en file les entrées nouvelles et publie ce qui attend")
    parseur.add_argument("--db", default=str(config.CHEMIN_DB), help="base SQLite (défaut : DEDALE_DB)")
    args = parseur.parse_args(argv)
    adresse = adresse_ancrage(creer=True)
    if args.commande == "adresse":
        print(adresse)
        return 0
    rpc = fabrique_rpc() if fabrique_rpc is not None else ClientRPC()
    if args.commande == "etat":
        code = _afficher_etat(rpc, adresse)
        chemin = Path(args.db)
        if chemin.is_file():
            conn = journal_scelle.ouvrir_lecture(chemin)
            try:
                e = etat(conn)
            finally:
                conn.close()
            print(f"File : {e['file'].get('en_attente', 0)} lot(s) en attente, "
                  f"{e['file'].get('envoyee', 0)} envoyé(s), {e['file'].get('confirmee', 0)} confirmé(s)")
        return code
    chemin = Path(args.db)
    if not chemin.is_file():
        print(f"Base introuvable : {chemin}", file=sys.stderr)
        return 2
    res = cycle(chemin, motif="commande", rpc=rpc, envoyer=True, attendre_s=30.0)
    lot = res["lot"]
    print(f"Lot préparé : n°{lot['id']}, {lot['n_feuilles']} entrée(s), racine {lot['racine'][:16]}…"
          if lot else "Aucune entrée nouvelle à mettre en file.")
    conn = journal_scelle.ouvrir_lecture(chemin)
    try:
        lots = _lots(conn)
    finally:
        conn.close()
    for l in lots[-5:]:
        if l["statut"] == "confirmee":
            print(f"Lot {l['id']} ancré : bloc {l['bloc']}, {lien_tx(l['tx'])}")
        elif l["statut"] == "envoyee":
            print(f"Lot {l['id']} envoyé, en attente du bloc : {lien_tx(l['tx'])}")
        else:
            print(f"Lot {l['id']} en attente : {libelle_attente(l['raison'])}")
    attente = [l for l in lots if l["statut"] != "confirmee"]
    return 0 if not attente else 1


if __name__ == "__main__":
    sys.exit(main())
