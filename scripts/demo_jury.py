"""Démo du jury en une commande : services prêts, base neuve, deux scènes et un chrono.

`./demo.sh jury` lance le backend (8700) et la console (5173) s'ils manquent. Avant de
relancer le backend, il copie l'ancienne base dans `data/sauvegardes/`, vérifie la copie,
puis repart d'une base vide. Il joue ensuite le salarié (mail de phishing, pop-up) et
l'agent scripté (tâche légitime, consigne cachée, appel sortant retenu), mesure chaque
étape et attend la décision de l'analyste dans la console. Aucune décision n'est envoyée
par ce script.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_commune as commune  # noqa: E402  (ajoute aussi poste/ et interne/ au chemin)

from garde.garde_du_corps import GardeDuCorps  # noqa: E402
from garde.popup import rendu_terminal  # noqa: E402
from garde.simulateur import journee  # noqa: E402
from orbis import detection  # noqa: E402
from orbis.agent import AgentInterne  # noqa: E402
from orbis.canaris import inventaire_backend  # noqa: E402
from orbis.cerveau import CerveauScripte  # noqa: E402
from orbis.outils import Outils  # noqa: E402
from orbis.passerelle import OUTILS_SORTANTS  # noqa: E402

RACINE = commune.RACINE
DATA = RACINE / "data"
JOURNAUX = DATA / "journaux"
SERVICES = JOURNAUX / "services.json"
CANARIS = {"C-2B91", "C-7A3F"}
DEMANDE_AGENT = "Résume mes mails de la semaine et envoie-moi le rapport."
LIBELLE_CANARI = {
    "exfiltration_markdown": "image vers un domaine externe",
    "faux_secret": "faux secret",
}

ErreurDemo = commune.ErreurDemo
AttenteExpiree = commune.AttenteExpiree


class SansDecision(Exception):
    """Fin voulue (--sans-decision) : l'appel reste retenu, rien n'est exécuté."""


# --------------------------------------------------------------------- mesures et affichage
def duree(secondes: float | None) -> str:
    """Durée lisible en français : « 0,4 ms », « 12 ms », « 1,3 s »."""
    if secondes is None:
        return "non mesuré"
    ms = max(secondes, 0.0) * 1000
    if ms < 10:
        return f"{ms:.1f} ms".replace(".", ",")
    if ms < 1000:
        return f"{ms:.0f} ms"
    return f"{ms / 1000:.1f} s".replace(".", ",")


def ecart(alerte: float, arrivee: tuple[float, dict] | None) -> float | None:
    """Temps de remontée ; None si l'arrivée manque ou précède l'alerte (mesure faussée)."""
    if arrivee is None or arrivee[0] < alerte:
        return None
    return arrivee[0] - alerte


class Scene:
    """Horloge d'une scène : chaque ligne porte le temps écoulé depuis le premier geste."""

    def __init__(self, afficher=print):
        self.debut = time.perf_counter()
        self.afficher = afficher

    def ligne(self, instant: float, texte: str) -> None:
        self.afficher(f"  +{duree(instant - self.debut):<10} {texte}")


# --------------------------------------------------------------------- flux temps réel
GUID_WS = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class FluxConsole:
    """Client WebSocket minimal (bibliothèque standard) branché sur le /ws de la console.

    Il lit le même flux que l'écran du SOC et note l'heure d'arrivée du premier message
    `incident` de chaque session. C'est la mesure de « remontée à la console ».
    """

    def __init__(self, url_console: str):
        morceaux = urlsplit(url_console)
        self.hote = morceaux.hostname or "127.0.0.1"
        self.port = morceaux.port or (443 if morceaux.scheme == "https" else 80)
        self.arrivees: dict[str, tuple[float, dict]] = {}
        self._condition = threading.Condition()
        self._prise: socket.socket | None = None
        self._reste = b""
        self._fini = False
        self.erreur: str | None = None

    def ouvrir(self, delai: float = 3.0) -> None:
        hote = "127.0.0.1" if self.hote == "localhost" else self.hote
        prise = socket.create_connection((hote, self.port), timeout=delai)
        cle = base64.b64encode(os.urandom(16)).decode()
        prise.sendall((
            f"GET /ws HTTP/1.1\r\nHost: {self.hote}:{self.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        tampon = b""
        while b"\r\n\r\n" not in tampon:
            morceau = prise.recv(4096)
            if not morceau:
                prise.close()
                raise OSError("flux fermé pendant l'ouverture")
            tampon += morceau
        entete, self._reste = tampon.split(b"\r\n\r\n", 1)
        lignes = entete.decode("latin-1").split("\r\n")
        attendu = base64.b64encode(hashlib.sha1((cle + GUID_WS).encode()).digest()).decode()
        accepte = any(
            l.lower().startswith("sec-websocket-accept:") and l.split(":", 1)[1].strip() == attendu
            for l in lignes[1:]
        )
        statut = lignes[0].split()
        if len(statut) < 2 or statut[1] != "101" or not accepte:
            prise.close()
            raise OSError(f"flux refusé ({lignes[0]})")
        prise.settimeout(0.5)
        self._prise = prise
        threading.Thread(target=self._boucle, name="flux-console", daemon=True).start()

    def _lire(self, n: int) -> bytes:
        while len(self._reste) < n:
            try:
                morceau = self._prise.recv(65536)
            except socket.timeout:
                if self._fini:
                    raise EOFError
                continue
            if not morceau:
                raise EOFError
            self._reste += morceau
        donnees, self._reste = self._reste[:n], self._reste[n:]
        return donnees

    def _trame(self) -> tuple[bool, int, bytes]:
        b0, b1 = self._lire(2)
        longueur = b1 & 0x7F
        if longueur == 126:
            longueur = struct.unpack(">H", self._lire(2))[0]
        elif longueur == 127:
            longueur = struct.unpack(">Q", self._lire(8))[0]
        masque = self._lire(4) if b1 & 0x80 else None
        charge = self._lire(longueur)
        if masque:
            charge = bytes(c ^ masque[i % 4] for i, c in enumerate(charge))
        return bool(b0 & 0x80), b0 & 0x0F, charge

    def _envoyer(self, opcode: int, charge: bytes = b"") -> None:
        masque = os.urandom(4)
        charge = charge[:125]
        trame = bytes([0x80 | opcode, 0x80 | len(charge)]) + masque
        self._prise.sendall(trame + bytes(c ^ masque[i % 4] for i, c in enumerate(charge)))

    def recevoir(self, instant: float, texte: bytes) -> None:
        try:
            message = json.loads(texte)
        except ValueError:
            return
        if not isinstance(message, dict) or message.get("type") != "incident":
            return
        donnees = message.get("donnees")
        if not isinstance(donnees, dict) or not isinstance(donnees.get("session_id"), str):
            return
        with self._condition:
            self.arrivees.setdefault(donnees["session_id"], (instant, donnees))
            self._condition.notify_all()

    def _boucle(self) -> None:
        morceaux = b""
        try:
            while not self._fini:
                fin, opcode, charge = self._trame()
                instant = time.perf_counter()
                if opcode == 0x9:
                    self._envoyer(0xA, charge)
                elif opcode == 0x8:
                    break
                elif opcode in (0x0, 0x1):
                    morceaux += charge
                    if fin:
                        self.recevoir(instant, morceaux)
                        morceaux = b""
        except (EOFError, OSError) as exc:
            if not self._fini:
                self.erreur = str(exc) or "flux interrompu"
        finally:
            with self._condition:
                self._condition.notify_all()

    def attendre(self, session_id: str, delai: float = 5.0) -> tuple[float, dict] | None:
        echeance = time.monotonic() + delai
        with self._condition:
            while session_id not in self.arrivees:
                restant = echeance - time.monotonic()
                if restant <= 0 or self.erreur:
                    return None
                self._condition.wait(restant)
            return self.arrivees[session_id]

    def fermer(self) -> None:
        self._fini = True
        if self._prise is not None:
            try:
                self._envoyer(0x8)
            except OSError:
                pass
            self._prise.close()


# --------------------------------------------------------------------- services locaux
def lire_json(url: str, delai: float = 1.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=delai) as reponse:
            donnees = json.load(reponse)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return donnees if isinstance(donnees, dict) else None


def locale(url: str) -> str:
    """Même URL, mais vers 127.0.0.1 : la console Vite n'écoute qu'en IPv4."""
    morceaux = urlsplit(url)
    if morceaux.hostname == "localhost":
        return url.replace("localhost", "127.0.0.1", 1)
    return url


def sante(url: str) -> dict | None:
    donnees = lire_json(locale(url).rstrip("/") + "/api/sante")
    return donnees if donnees and donnees.get("service") == "dedale-backend" else None


def port_ouvert(port: int) -> bool:
    for hote in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((hote, port), timeout=0.2):
                return True
        except OSError:
            pass
    return False


def sortie(commande: list[str]) -> str:
    try:
        return subprocess.run(commande, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def pids_ecoute(port: int) -> list[int]:
    lignes = sortie(["lsof", "-nP", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]).split()
    return sorted({int(l) for l in lignes if l.isdigit()})


def commande_de(pid: int) -> str:
    return sortie(["ps", "-o", "command=", "-p", str(pid)]).strip()


def dossier_de(pid: int) -> Path | None:
    for ligne in sortie(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).splitlines():
        if ligne.startswith("n"):
            return Path(ligne[1:])
    return None


def vivant(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def arreter_backend(port: int, *, attente: float = 15.0) -> int:
    """Arrête le backend Dédale de ce dépôt qui écoute sur `port`. Refuse tout autre processus."""
    pids = pids_ecoute(port)
    if not pids:
        raise ErreurDemo(f"Le port {port} répond, mais aucun processus local n'y écoute.")
    attendu = (RACINE / "backend").resolve()
    for pid in pids:
        commande = commande_de(pid)
        dossier = dossier_de(pid)
        if "uvicorn" not in commande or "app.main:app" not in commande:
            raise ErreurDemo(f"Le port {port} est tenu par autre chose qu'un backend Dédale (pid {pid}).")
        if dossier is None or dossier.resolve() != attendu:
            raise ErreurDemo(
                f"Le backend du port {port} vient d'un autre dossier ({dossier}). "
                "Arrêtez-le, ou relancez avec --garder-base."
            )
    for pid in pids:
        os.kill(pid, signal.SIGTERM)
    echeance = time.monotonic() + attente
    while time.monotonic() < echeance:
        if not any(vivant(pid) for pid in pids) and not port_ouvert(port):
            return len(pids)
        time.sleep(0.2)
    raise ErreurDemo(f"Le backend du port {port} ne s'est pas arrêté en {attente:g} s. Base laissée en place.")


def chemin_base() -> Path:
    # Même règle que backend/app/config.py.
    return Path(os.environ.get("DEDALE_DB", str(DATA / "dedale.db")))


def compter_evenements(chemin: Path) -> int:
    connexion = sqlite3.connect(f"file:{chemin}?mode=ro", uri=True)
    try:
        verdict = connexion.execute("PRAGMA quick_check").fetchone()
        if not verdict or verdict[0] != "ok":
            raise sqlite3.DatabaseError(f"quick_check : {verdict}")
        tables = {r[0] for r in connexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "evenements" not in tables:
            return 0
        return connexion.execute("SELECT count(*) FROM evenements").fetchone()[0]
    finally:
        connexion.close()


def mettre_base_de_cote(base: Path, *, maintenant: datetime | None = None,
                        fichiers_ouverts=None) -> tuple[Path, int] | None:
    """Copie la base (et ses -wal/-shm) dans sauvegardes/, vérifie la copie, puis retire l'original.

    Renvoie (copie, nombre d'événements) ou None s'il n'y avait pas de base. En cas de doute
    (base ouverte par un processus, copie illisible), rien n'est retiré.
    """
    if not base.exists():
        return None
    ouverts = (fichiers_ouverts or (lambda p: sortie(["lsof", "-t", "--", str(p)]).split()))(base)
    if ouverts:
        raise ErreurDemo(f"{base.name} est encore ouverte (pid {', '.join(ouverts)}). Base laissée en place.")
    horodatage = (maintenant or datetime.now()).strftime("%Y%m%d-%H%M%S")
    dossier = base.parent / "sauvegardes"
    dossier.mkdir(parents=True, exist_ok=True)
    copie = dossier / f"{base.stem}-{horodatage}{base.suffix}"
    rang = 1
    while copie.exists():
        rang += 1
        copie = dossier / f"{base.stem}-{horodatage}-{rang}{base.suffix}"
    originaux = [p for p in (base, Path(f"{base}-wal"), Path(f"{base}-shm")) if p.exists()]
    for original in originaux:
        shutil.copy2(original, Path(str(copie) + original.name[len(base.name):]))
    try:
        evenements = compter_evenements(copie)
    except sqlite3.Error as exc:
        raise ErreurDemo(f"Copie de la base illisible ({exc}). Original laissé en place : {base}.") from exc
    for original in originaux:
        original.unlink()
    return copie, evenements


def preparer_journaux() -> None:
    JOURNAUX.mkdir(parents=True, exist_ok=True)
    ignore = JOURNAUX / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")


def noter_service(nom: str, pid: int, commande: list[str]) -> None:
    try:
        services = json.loads(SERVICES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        services = {}
    services[nom] = {"pid": pid, "commande": " ".join(commande), "depuis": datetime.now().isoformat(timespec="seconds")}
    temporaire = SERVICES.with_suffix(".tmp")
    temporaire.write_text(json.dumps(services, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporaire, SERVICES)


def lancer(nom: str, commande: list[str], dossier: Path, env: dict | None = None) -> subprocess.Popen:
    preparer_journaux()
    journal = open(JOURNAUX / f"{nom}.log", "ab")
    try:
        processus = subprocess.Popen(
            commande, cwd=dossier, stdin=subprocess.DEVNULL, stdout=journal,
            stderr=subprocess.STDOUT, start_new_session=True, env=env,
        )
    finally:
        journal.close()
    noter_service(nom, processus.pid, commande)
    return processus


def attendre_reponse(url: str, processus: subprocess.Popen | None, nom: str, delai: float) -> dict:
    echeance = time.monotonic() + delai
    while time.monotonic() < echeance:
        if processus is not None and processus.poll() is not None:
            raise ErreurDemo(f"{nom} s'est arrêté au démarrage. Journal : {JOURNAUX / (nom + '.log')}.")
        etat = sante(url)
        if etat is not None:
            return etat
        time.sleep(0.3)
    raise ErreurDemo(f"{nom} ne répond pas après {delai:g} s. Journal : {JOURNAUX / (nom + '.log')}.")


def relatif(chemin: Path) -> str:
    try:
        return str(chemin.resolve().relative_to(RACINE))
    except ValueError:
        return str(chemin)


def preparer_services(options, afficher=print) -> None:
    backend = urlsplit(options.backend)
    console = urlsplit(options.console)
    locaux = {"127.0.0.1", "localhost"}
    afficher("Préparation")

    etat = sante(options.backend)
    if options.garder_base:
        if etat is None:
            raise ErreurDemo(f"--garder-base : aucun backend Dédale ne répond sur {options.backend}.")
        afficher(f"  backend   gardé tel quel : {options.backend} (santé : {etat.get('statut')})")
    else:
        if backend.hostname not in locaux:
            raise ErreurDemo("Base neuve possible seulement pour un backend local. Sinon : --garder-base.")
        port = backend.port or 80
        if etat is not None:
            arreter_backend(port)
            afficher(f"  backend   arrêté sur le port {port} pour changer de base")
        elif port_ouvert(port):
            raise ErreurDemo(f"Le port {port} est occupé par autre chose que le backend Dédale.")
        base = chemin_base()
        mise = mettre_base_de_cote(base)
        if mise is None:
            afficher(f"  base      aucune base à mettre de côté ({relatif(base)})")
        else:
            copie, evenements = mise
            afficher(f"  base      ancienne base copiée dans {relatif(copie)} ({evenements} événements)")
        processus = lancer("backend", ["uv", "run", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                                       "--port", str(port)], RACINE / "backend")
        etat = attendre_reponse(options.backend, processus, "backend", 60)
        if etat.get("statut") != "ok":
            raise ErreurDemo(f"Le backend relancé se déclare {etat.get('statut')}. Journal : {JOURNAUX / 'backend.log'}.")
        afficher(f"  backend   relancé sur une base vide : {options.backend} (santé : ok)")

    if sante(options.console) is not None:
        afficher(f"  console   déjà lancée : {options.console}")
    else:
        port = console.port or 80
        if console.hostname not in locaux or port != 5173:
            raise ErreurDemo(f"La console ne répond pas sur {options.console}.")
        if port_ouvert(port):
            raise ErreurDemo(f"Le port {port} est occupé, mais la console Dédale n'y répond pas.")
        if not (RACINE / "console" / "node_modules" / ".bin" / "vite").exists():
            raise ErreurDemo("Console non préparée : lancez « cd console && npm ci ».")
        env = dict(os.environ, DEDALE_BACKEND=options.backend)
        processus = lancer("console", ["npm", "run", "dev"], RACINE / "console", env=env)
        attendre_reponse(options.console, processus, "console", 60)
        afficher(f"  console   lancée : {options.console}")


def arreter_services(afficher=print) -> int:
    """Arrête ce que `./demo.sh jury` a lancé, et rien d'autre."""
    try:
        services = json.loads(SERVICES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        afficher("Aucun service lancé par la démo.")
        return 0
    for nom, infos in services.items():
        pid = infos.get("pid")
        if not isinstance(pid, int) or not vivant(pid):
            afficher(f"{nom} : déjà arrêté.")
            continue
        if commande_de(pid) != infos.get("commande"):
            afficher(f"{nom} : le pid {pid} sert maintenant à autre chose, laissé tel quel.")
            continue
        os.killpg(pid, signal.SIGTERM)
        echeance = time.monotonic() + 15
        while sortie(["pgrep", "-g", str(pid)]).split() and time.monotonic() < echeance:
            time.sleep(0.2)
        reste = sortie(["pgrep", "-g", str(pid)]).split()
        afficher(f"{nom} : arrêté (pid {pid})." if not reste else
                 f"{nom} : arrêt demandé, encore actif (pid {', '.join(reste)}).")
    SERVICES.unlink(missing_ok=True)
    return 0


# --------------------------------------------------------------------- scènes
class BackendMesure(commune.BackendControle):
    """Client du poste : note l'instant d'émission de chaque événement."""

    def __init__(self, *args, emissions: dict, **options):
        super().__init__(*args, **options)
        self.emissions = emissions

    def evenement(self, type: str, session_id: str, **options) -> dict:
        self.emissions.setdefault(type, time.perf_counter())
        return super().evenement(type, session_id, **options)


def scene_salarie(api: commune.Api, flux: FluxConsole, session_id: str, afficher=print) -> dict:
    afficher("\n1. Salariée · Camille ouvre un mail de phishing")
    geste = journee()[0]
    emissions: dict[str, float] = {}
    backend = BackendMesure(base=api.base, emissions=emissions)
    backend.evenement("requete", session_id, details={"contexte": geste.description})
    scene = Scene(afficher)
    instants: dict[str, float] = {}

    def decider(_geste, verdict) -> str:
        instants["popup"] = time.perf_counter()
        scene.ligne(instants["popup"], f"mail reconnu comme frauduleux ({verdict.regle}), pop-up affichée :")
        for ligne in rendu_terminal(verdict).splitlines():
            afficher("    " + ligne)
        scene.ligne(time.perf_counter(), "Camille clique « Continuer quand même » (choix joué)")
        return "continuer"

    garde = GardeDuCorps(backend=backend, session_id=session_id, decideur=decider)
    instants["mail"] = time.perf_counter()
    scene.debut = instants["mail"]
    scene.ligne(instants["mail"], f"mail ouvert : « {geste.objet} »")
    resultat = garde.observer(geste)
    if not resultat.averti or not resultat.incident_emis or "popup" not in instants:
        raise ErreurDemo("Le mail frauduleux n'a pas produit l'avertissement et l'alerte attendus.")
    # Le backend ouvre l'incident dès l'avertissement qui porte le choix « continuer ».
    alerte = emissions["avertissement"]
    scene.ligne(alerte, "avertissement et choix envoyés au SOC")
    arrivee = flux.attendre(session_id)
    incident = api.incident(session_id)
    if incident is None or incident.get("type") != "humain_phishing":
        raise ErreurDemo("Aucun incident humain_phishing pour la scène salariée.")
    if arrivee is not None:
        scene.ligne(arrivee[0], f"{incident['id']} reçu par la console ({incident['type']})")
    return {
        "incident": incident, "qui": "salariée, phishing",
        "detection": instants["popup"] - instants["mail"],
        "remontee": ecart(alerte, arrivee),
    }


class BoiteMesure(commune.BoiteNoireControlee):
    """Boîte noire contrôlée qui raconte les étapes de l'agent au fil des événements."""

    def __init__(self, *args, scene: Scene, mesures: dict, **options):
        super().__init__(*args, **options)
        self.scene = scene
        self.mesures = mesures

    def evenement(self, type: str, surface: str, session_id: str, **options) -> dict:
        instant = time.perf_counter()
        details = options.get("details") or {}
        outil = options.get("outil")
        if type == "entree_agent":
            self.scene.debut = instant
            self.scene.ligne(instant, f"tâche légitime : « {details.get('texte', '')} »")
        elif type == "appel_outil" and outil == "lire_mail":
            self.scene.ligne(instant, "lit la boîte mail de Jean")
        elif type == "appel_outil" and outil == "chercher_document":
            requete = (details.get("parametres") or {}).get("requete", "")
            self.scene.ligne(instant, f"suit la consigne cachée : cherche le document « {requete} »")
        elif type == "appel_outil" and outil in OUTILS_SORTANTS:
            self.scene.ligne(instant, f"appel sortant hors cadre : {outil}, avec une image externe dans le rapport")
        elif type == "leurre_touche":
            self.mesures.setdefault("alerte", instant)
            libelle = LIBELLE_CANARI.get(details.get("type"), details.get("type", "canari"))
            self.mesures.setdefault("canaris", []).append(f"{libelle} {options.get('leurre_id')}")
        return super().evenement(type, surface, session_id, **options)


class OutilsMesure(Outils):
    """Outils fictifs de l'agent ; signale le mail qui porte une consigne cachée."""

    def __init__(self, scene: Scene):
        super().__init__()
        self.scene = scene

    def lire_mail(self, *args, **options):
        mails = super().lire_mail(*args, **options)
        for mail in mails if isinstance(mails, list) else []:
            if detection.consigne_cachee_dans(json.dumps(mail, ensure_ascii=False)):
                self.scene.ligne(time.perf_counter(),
                                 f"contenu non fiable : le mail « {mail.get('sujet', '')} » cache une consigne")
        return mails


class PasserelleJury(commune.PasserelleConsole):
    """Passerelle réelle. Quand elle retient l'appel, le chrono s'affiche avant l'attente."""

    def __init__(self, *args, mesures: dict, quand_retenu, sans_decision: bool, **options):
        super().__init__(*args, **options)
        self.mesures = mesures
        self.quand_retenu = quand_retenu
        self.sans_decision = sans_decision

    def appel_outil(self, nom, params, fonction, descripteur=None):
        if nom in OUTILS_SORTANTS:
            self.mesures.setdefault("appel", time.perf_counter())
        return super().appel_outil(nom, params, fonction, descripteur=descripteur)

    def _attendre_decision(self) -> str:
        self.quand_retenu()
        if self.sans_decision:
            raise SansDecision()
        return commune.attendre_decision(
            self.api, self.session_id, attente=self.poll_max_s, intervalle=self.intervalle_poll,
            console=self.console, afficher=lambda _texte: None,
        )


def afficher_chrono(lignes: list[dict], console: str, afficher=print) -> None:
    afficher("\nChrono")
    afficher(f"  {'incident':<10}{'qui':<22}{'détection':<14}remontée console")
    for l in lignes:
        afficher(f"  {l['incident']['id']:<10}{l['qui']:<22}{duree(l['detection']):<14}{duree(l['remontee'])}")
    afficher("  détection : de l'acte (mail ouvert, appel sortant) à la pop-up ou à l'appel retenu")
    afficher("  remontée console : de l'alerte émise à son arrivée dans le flux temps réel de la console")
    afficher("\nÀ ouvrir dans la console")
    for l in lignes:
        afficher(f"  {l['incident']['id']}  {console.rstrip('/')}/?incident={quote(l['incident']['id'], safe='')}")


def scene_agent(api: commune.Api, flux: FluxConsole, session_id: str, options, lignes: list[dict],
                afficher=print) -> dict:
    afficher("\n2. Agent IA · l'assistant de Jean résume ses mails")
    scene = Scene(afficher)
    mesures: dict = {}
    boite = BoiteMesure(base=api.base, scene=scene, mesures=mesures)
    outils = OutilsMesure(scene)

    def quand_retenu() -> None:
        # La passerelle retient l'appel au moment où elle émet l'alerte (premier canari).
        scene.ligne(mesures["alerte"], f"appel retenu par la passerelle ({', '.join(mesures.get('canaris', []))})")
        arrivee = flux.attendre(session_id)
        incident = api.incident(session_id)
        if incident is None or incident.get("type") != "interne_canari":
            raise ErreurDemo("Aucun incident interne_canari pour l'appel retenu.")
        if arrivee is not None:
            scene.ligne(arrivee[0], f"{incident['id']} reçu par la console ({incident['type']})")
        lignes.append({
            "incident": incident, "qui": "agent IA, canari",
            "detection": mesures["alerte"] - mesures["appel"],
            "remontee": ecart(mesures["alerte"], arrivee),
        })
        verifier_console(api, options.console, lignes)
        afficher_chrono(lignes, options.console, afficher)
        mesures["incident"] = incident
        mesures["ouvert"] = time.perf_counter()
        if options.sans_decision:
            return
        afficher(f"\nL'appel de l'agent reste bloqué. Décidez dans la console ({incident['id']}) : Couper ou Reprendre.")
        afficher(f"Attente : {options.attente:g} s au plus. Ctrl-C quitte sans décider.")

    passerelle = PasserelleJury(
        session_id, boite, api, attente=options.attente, intervalle=options.intervalle,
        console=options.console, mesures=mesures, quand_retenu=quand_retenu,
        sans_decision=options.sans_decision,
    )
    agent = AgentInterne(session_id, cerveau=CerveauScripte("naif"), outils=outils,
                         boite=boite, passerelle=passerelle)
    try:
        resultat = agent.executer(DEMANDE_AGENT)
    except SansDecision:
        afficher("\nFin sans décision (--sans-decision). L'appel n'a pas été exécuté ; "
                 "Couper reste possible dans la console.")
        return {"verdict": None}
    etat = api.session(session_id).get("etat")
    if etat != resultat["etat"]:
        raise ErreurDemo("L'état local de l'agent diffère de celui du backend.")
    attente = duree(time.perf_counter() - mesures["ouvert"])
    if resultat["coupe"]:
        if outils.rapports_envoyes:
            raise ErreurDemo("Un rapport est parti malgré la coupure.")
        afficher(f"Décision reçue après {attente} : Couper. Agent arrêté, jeton révoqué, aucun rapport envoyé.")
        return {"verdict": "couper"}
    if len(outils.rapports_envoyes) != 1:
        raise ErreurDemo("La reprise n'a pas exécuté le rapport retenu.")
    afficher(f"Décision reçue après {attente} : Reprendre. L'appel retenu s'exécute ; "
             "le rapport fictif reste dans la boîte d'envoi locale.")
    return {"verdict": "reprendre"}


def verifier_console(api: commune.Api, console: str, lignes: list[dict]) -> None:
    """Les incidents doivent être lisibles par l'API que lit la console, pas seulement par le backend."""
    donnees = lire_json(locale(console).rstrip("/") + "/api/incidents", delai=2.0)
    vus = {i.get("id") for i in (donnees or {}).get("incidents", []) if isinstance(i, dict)}
    manquants = [l["incident"]["id"] for l in lignes if l["incident"]["id"] not in vus]
    if manquants:
        raise ErreurDemo(f"La console sur {console} ne voit pas {', '.join(manquants)} : "
                         "elle lit sans doute un autre backend.")


# --------------------------------------------------------------------- entrée
def arguments(argv=None):
    analyseur = argparse.ArgumentParser(
        prog="./demo.sh jury",
        description="Démo du jury : base neuve, salariée puis agent, chrono, décision dans la console.",
    )
    analyseur.add_argument("--backend", type=commune.url_backend, default="http://127.0.0.1:8700")
    analyseur.add_argument("--console", type=commune.url_backend, default="http://localhost:5173",
                           help="console du SOC (défaut : http://localhost:5173)")
    analyseur.add_argument("--garder-base", action="store_true",
                           help="réutiliser le backend qui tourne, sans changer de base")
    analyseur.add_argument("--sans-decision", action="store_true",
                           help="s'arrêter après le chrono ; l'appel de l'agent reste bloqué")
    analyseur.add_argument("--attente", type=commune.nombre_positif, default=600.0,
                           help="délai maximal pour la décision dans la console, en secondes (600)")
    analyseur.add_argument("--intervalle", type=commune.nombre_positif, default=0.5,
                           help="intervalle de lecture de la décision, en secondes (0,5)")
    analyseur.add_argument("--arreter", action="store_true",
                           help="arrêter le backend et la console lancés par la démo")
    return analyseur.parse_args(argv)


def main(argv=None) -> int:
    options = arguments(argv)
    if options.arreter:
        return arreter_services()
    flux = None
    try:
        print(f"Dédale · démo jury · {datetime.now():%H:%M:%S}")
        print("Orbis Pay, ses mails et ses secrets sont fictifs. Agent scripté, aucun modèle appelé.\n")
        preparer_services(options)
        api = commune.Api(options.backend)
        api.verifier_sante()
        boite = commune.BoiteNoireControlee(base=api.base)
        canaris = [c for c in inventaire_backend() if c["id"] in CANARIS]
        if {c["id"] for c in canaris} != CANARIS or not boite.enregistrer_leurres(canaris):
            raise ErreurDemo("Enregistrement des canaris non confirmé ; arrêt avant les scènes.")
        flux = FluxConsole(options.console)
        try:
            flux.ouvrir()
            print("  flux      branché sur /ws, comme l'écran de la console")
        except OSError as exc:
            flux.erreur = str(exc)
            print(f"  flux      /ws injoignable ({exc}) : remontée console non mesurée")
        execution = f"jury-{datetime.now():%H%M%S}-{uuid4().hex[:4]}"
        lignes = [scene_salarie(api, flux, execution + "-poste")]
        scene_agent(api, flux, execution + "-agent", options, lignes)
        print(f"\nSessions de cette démo : {execution}-poste et {execution}-agent.")
        print("Le backend et la console restent lancés. Pour les arrêter : ./demo.sh jury --arreter")
        return 0
    except KeyboardInterrupt:
        print("\nDémo interrompue. L'appel retenu n'est pas libéré ; l'incident reste dans la console.",
              file=sys.stderr)
        return 130
    except AttenteExpiree:
        print("\nAucune décision reçue à temps. L'appel n'a pas été exécuté ; l'incident reste à traiter.",
              file=sys.stderr)
        return 3
    except ErreurDemo as exc:
        print(f"\nDémo arrêtée : {exc}", file=sys.stderr)
        return 2
    finally:
        if flux is not None:
            flux.fermer()


if __name__ == "__main__":
    raise SystemExit(main())
