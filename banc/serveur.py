#!/usr/bin/env python3
"""Banc d'essai sAIfe : une page à boutons pour piloter toute la démo depuis un navigateur.

Tout tourne sur 127.0.0.1. Le serveur sert la page et expose des endpoints qui lancent
les vraies commandes du dépôt en sous-processus. Le jeton analyste est lu ici, côté
serveur, et ajouté aux appels au backend ; il n'apparaît jamais dans la page servie.

Bibliothèque standard seulement : aucun paquet à installer, il tourne avec le python3 du
système. Lancé par `banc/demarrer.sh`, sur 8900 par défaut (`BANC_PORT` pour en changer).

Ce qu'il NE fait pas : il ne relance jamais l'app Mac (port 8712) ni aucun processus
personnel. Il lit l'état de l'app, il ne la touche pas.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

RACINE = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
JOURNAUX = Path(__file__).resolve().parent / "journaux"
JOURNAUX.mkdir(exist_ok=True)

PORT_BANC = int(os.environ.get("BANC_PORT", "8900"))
DOSSIER_JETONS = Path(os.environ.get("DEDALE_JETONS", str(Path.home() / ".config" / "dedale")))

# PATH élargi pour trouver uv, npm, mailpit même si le serveur est lancé sans shell de login.
ENV_ENFANT = {**os.environ}
ENV_ENFANT["PATH"] = ":".join(dict.fromkeys(
    ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
     *ENV_ENFANT.get("PATH", "").split(":")]
))

# --- Services suivis ---------------------------------------------------------------------
# sante : URL ouverte qui prouve que le service répond. demarre : comment le lancer s'il
# manque (None = jamais lancé par le banc, cas de l'app Mac).
BACKEND = "http://127.0.0.1:8700"
SERVICES = {
    "backend": {
        "nom": "Backend sAIfe",
        "port": 8700,
        "sante": BACKEND + "/api/sante",
        "demarre": {"cmd": ["uv", "run", "uvicorn", "app.main:app",
                            "--host", "127.0.0.1", "--port", "8700"],
                    "cwd": RACINE / "backend"},
    },
    "console": {
        "nom": "Console SOC",
        "port": 5173,
        "sante": "http://127.0.0.1:5173/",
        "demarre": {"cmd": ["npm", "run", "dev"], "cwd": RACINE / "console"},
    },
    "mailpit": {
        "nom": "Boîte mail (Mailpit)",
        "port": 8716,
        "sante": "http://127.0.0.1:8716/api/v1/info",
        "demarre": {"cmd": ["./demarrer.sh", "--service"], "cwd": RACINE / "messagerie",
                    "bloquant": True},
    },
    "verdicts": {
        "nom": "Verdicts messagerie",
        "port": 8715,
        "sante": "http://127.0.0.1:8715/sante",
        "demarre": None,  # démarré avec Mailpit par messagerie/demarrer.sh --service
    },
    "app_mac": {
        "nom": "App Mac (bouclier)",
        "port": 8712,
        "sante": "http://127.0.0.1:8712/etat",
        "demarre": None,  # jamais relancée : elle porte peut-être la session de Guilhem
    },
}

# Les deux gestes de virement, repris mot pour mot de docs/DEMO_JURY.md.
VIREMENTS = {
    "normal": {"categorie": "mail_externe", "geste": "virement", "gravite": "critique",
               "message": "Virement de 320 € à Imprimerie du Lys."},
    "rib": {"categorie": "mail_externe", "geste": "virement", "gravite": "critique",
            "message": "Virement de 3 480 € à Atelier Nord, nouveau RIB "
                       "FR76 1111 2222 3333 4444 5555 0042."},
}

CAS_MAIL = ["sosie", "lien_menteur", "piece_exe", "piece_macro", "fraude_president"]
# Le premier de la liste est le modèle par défaut de l'« agent naïf » du banc. qwen2.5:7b est
# le plus « suiveur » des modèles locaux installés : sur le scénario réel il lit le relevé
# piégé, suit la consigne cachée et tente l'exfiltration à chaque essai (5/5 le 11 octobre), ce
# qui donne à chaque fois le parcours complet retenu → coupé → incident d'exfiltration. gpt-oss:20b
# reste au choix : plus prudent, il refuse plus souvent la consigne (bon pour montrer un agent
# qui résiste). Mesures dans docs/mesures/.
MODELES = ["qwen2.5:7b", "gpt-oss:20b"]
VERDICTS = "http://127.0.0.1:8715"
MAILPIT = "http://127.0.0.1:8716"

# --- Journal des actions du banc ---------------------------------------------------------
_actions = deque(maxlen=60)
_verrou_actions = threading.Lock()


def noter(texte: str, detail: str = "") -> None:
    with _verrou_actions:
        _actions.appendleft({"heure": datetime.now().strftime("%H:%M:%S"),
                             "texte": texte, "detail": detail})


def actions() -> list[dict]:
    with _verrou_actions:
        return list(_actions)


# --- Flux de l'agent IA ------------------------------------------------------------------
class AgentEnCours:
    """Un seul agent à la fois. Lit la sortie ligne par ligne et la garde pour la page."""

    def __init__(self) -> None:
        self.lignes: deque[str] = deque(maxlen=400)
        self.proc: subprocess.Popen | None = None
        self.modele = ""
        self.etat = "repos"  # repos | en_cours | fini | erreur
        self.verrou = threading.Lock()

    def en_cours(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def lancer(self, modele: str, essais: int) -> tuple[bool, str]:
        with self.verrou:
            if self.en_cours():
                return False, "Un agent tourne déjà. Attendre qu'il finisse."
            self.lignes.clear()
            self.modele = modele
            self.etat = "en_cours"
            env = {**ENV_ENFANT, "DEDALE_OLLAMA_MODELE": modele, "NILA_SANS_VEILLE": "1"}
            cmd = ["uv", "run", "--extra", "reel", "python", "-u", "-m", "orbis.demo",
                   "--scenario", "reel", "--cerveau", "ollama",
                   "--backend", BACKEND, "--essais", str(essais)]
            self._ajouter(f"$ {' '.join(cmd)}  (modèle {modele})")
            try:
                self.proc = subprocess.Popen(
                    cmd, cwd=str(RACINE / "interne"), env=env,
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                    start_new_session=True)
            except OSError as e:
                self.etat = "erreur"
                self._ajouter(f"[lancement impossible : {e}]")
                return False, str(e)
        threading.Thread(target=self._lire, daemon=True).start()
        return True, "agent lancé"

    def _lire(self) -> None:
        proc = self.proc
        assert proc and proc.stdout
        try:
            for ligne in proc.stdout:
                self._ajouter(ligne.rstrip("\n"))
        finally:
            code = proc.wait()
            self.etat = "fini" if code == 0 else "erreur"
            self._ajouter(f"[agent terminé, code {code}]")
            noter("Agent IA terminé", f"modèle {self.modele}, code {code}")

    def _ajouter(self, ligne: str) -> None:
        self.lignes.append(f"{datetime.now():%H:%M:%S}  {ligne}")

    def vue(self) -> dict:
        return {"etat": self.etat, "modele": self.modele,
                "en_cours": self.en_cours(), "lignes": list(self.lignes)}


AGENT = AgentEnCours()


# --- Outils HTTP -------------------------------------------------------------------------
def jeton_analyste() -> str | None:
    f = DOSSIER_JETONS / "jeton-analyste"
    try:
        return f.read_text().strip()
    except OSError:
        return None


def http_get(url: str, *, jeton: str | None = None, delai: float = 2.5) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="GET")
    if jeton:
        req.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(req, timeout=delai) as rep:
            return rep.status, rep.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError, socket.timeout):
        return 0, b""


def http_post_json(url: str, corps: dict, *, jeton: str | None = None,
                   delai: float = 5.0) -> tuple[int, bytes]:
    donnees = json.dumps(corps).encode("utf-8")
    req = urllib.request.Request(url, data=donnees, method="POST")
    req.add_header("Content-Type", "application/json")
    if jeton:
        req.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(req, timeout=delai) as rep:
            return rep.status, rep.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, OSError, socket.timeout) as e:
        return 0, str(e).encode()


def service_debout(cle: str) -> bool:
    code, _ = http_get(SERVICES[cle]["sante"], delai=1.5)
    return 200 <= code < 400


def etat_services() -> dict:
    out = {}
    for cle, s in SERVICES.items():
        out[cle] = {"nom": s["nom"], "port": s["port"], "debout": service_debout(cle),
                    "lancable": s["demarre"] is not None}
    return out


def etat_app_mac() -> dict:
    """Lu, jamais touché. Dit si le bouclier lit la vraie config du poste (source 'reel')."""
    code, corps = http_get(SERVICES["app_mac"]["sante"], delai=2.0)
    if not (200 <= code < 300):
        return {"debout": False}
    try:
        d = json.loads(corps)
    except json.JSONDecodeError:
        return {"debout": False}
    a = d.get("agents_ia", {})
    return {"debout": True, "poste": d.get("poste"),
            "source": a.get("source"), "serveurs": a.get("serveurs"),
            "risques": a.get("risques"), "soc": d.get("soc")}


def boite_mails() -> dict:
    """Les mails présents dans la boîte d'Orbis, avec le verdict de sAIfe quand il existe.

    Source : le garde-mail (8715), qui relève la boîte et pose un verdict. Repli sur Mailpit
    (8716) si le garde ne répond pas : expéditeur et objet, verdict inconnu.
    """
    code, corps = http_get(VERDICTS + "/mails?limite=40", delai=2.5)
    if 200 <= code < 300:
        try:
            mails = json.loads(corps).get("mails", [])
            out = []
            for m in mails:
                de = m.get("de") or {}
                out.append({"de": de.get("adresse") or de.get("nom") or "?",
                            "objet": m.get("objet") or "(sans objet)",
                            "verdict": m.get("verdict"), "recu_a": m.get("recu_a")})
            return {"source": "garde", "mails": out}
        except (json.JSONDecodeError, AttributeError):
            pass
    code, corps = http_get(MAILPIT + "/api/v1/messages?limit=40", delai=2.5)
    if 200 <= code < 300:
        try:
            msgs = json.loads(corps).get("messages", [])
            out = []
            for m in msgs:
                de = (m.get("From") or {})
                out.append({"de": de.get("Address") or de.get("Name") or "?",
                            "objet": m.get("Subject") or "(sans objet)",
                            "verdict": None, "recu_a": m.get("Created")})
            return {"source": "mailpit", "mails": out}
        except (json.JSONDecodeError, AttributeError):
            pass
    return {"source": None, "mails": []}


# --- Démarrage des services --------------------------------------------------------------
def lancer_service(cle: str) -> str:
    s = SERVICES[cle]
    spec = s["demarre"]
    if spec is None:
        return "non lançable par le banc"
    if service_debout(cle):
        return "déjà debout"
    journal = open(JOURNAUX / f"{cle}.log", "ab")
    journal.write(f"\n=== lancé {datetime.now():%Y-%m-%d %H:%M:%S} ===\n".encode())
    journal.flush()
    if spec.get("bloquant"):
        # Script idempotent qui rend la main une fois prêt (messagerie/demarrer.sh).
        try:
            r = subprocess.run(spec["cmd"], cwd=str(spec["cwd"]), env=ENV_ENFANT,
                               stdin=subprocess.DEVNULL, stdout=journal,
                               stderr=subprocess.STDOUT, timeout=120)
            return "prêt" if r.returncode == 0 else f"code {r.returncode}"
        except (OSError, subprocess.SubprocessError) as e:
            return f"échec : {e}"
    try:
        subprocess.Popen(spec["cmd"], cwd=str(spec["cwd"]), env=ENV_ENFANT,
                         stdin=subprocess.DEVNULL, stdout=journal,
                         stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        return f"échec : {e}"
    # Attendre qu'il réponde, sans dépasser un budget de temps.
    fin = time.time() + 40
    while time.time() < fin:
        if service_debout(cle):
            return "prêt"
        time.sleep(0.6)
    return "lancé, pas encore prêt"


def demarrer_tout() -> dict:
    resultats = {}
    for cle in ("backend", "mailpit", "console"):
        resultats[cle] = lancer_service(cle)
    noter("Démarrer tout", ", ".join(f"{k}: {v}" for k, v in resultats.items()))
    return {"resultats": resultats, "services": etat_services()}


# --- Repartir propre : base backend neuve ------------------------------------------------
# Même logique que scripts/demo_jury.py (mettre_base_de_cote) : on sauvegarde la base et ses
# fichiers voisins dans data/sauvegardes/, on vérifie la copie, puis on repart d'une base
# vide. Réécrit ici pour rester sans dépendance (le serveur du banc est en python standard).
def _pid_sur_port(port: int) -> int | None:
    try:
        sortie = subprocess.run(["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                                capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    return int(sortie[0]) if sortie else None


def _env_du_processus(pid: int) -> dict:
    """Lit DEDALE_DB dans l'environnement du backend en cours, pour sauvegarder le bon fichier."""
    try:
        brut = subprocess.run(["ps", "eww", "-o", "command=", str(pid)],
                              capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    env = {}
    for m in re.finditer(r"(\bDEDALE_[A-Z_]+)=(\S+)", brut):
        env[m.group(1)] = m.group(2)
    return env


def repartir_propre() -> dict:
    pid = _pid_sur_port(8700)
    env_backend = _env_du_processus(pid) if pid else {}
    base = Path(env_backend.get("DEDALE_DB") or str(RACINE / "data" / "dedale.db"))

    # 1. arrêter le backend pour libérer la base (SIGTERM, puis attente de la libération).
    if pid:
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        fin = time.time() + 15
        while time.time() < fin and _pid_sur_port(8700):
            time.sleep(0.4)
        if _pid_sur_port(8700):
            return {"ok": False, "message": "Le backend ne s'est pas arrêté. Base laissée en place."}

    # 2. sauvegarder la base et ses voisins, vérifier la copie, puis retirer l'original.
    sauvegarde = None
    if base.exists():
        try:
            dossier = base.parent / "sauvegardes"
            dossier.mkdir(parents=True, exist_ok=True)
            horo = datetime.now().strftime("%Y%m%d-%H%M%S")
            copie = dossier / f"{base.stem}-{horo}{base.suffix}"
            voisins = [p for p in (base, Path(f"{base}-wal"), Path(f"{base}-shm"),
                                   base.with_name(base.stem + "-politiques.json"))
                       if p.exists()]
            for original in voisins:
                cible = dossier / (copie.name if original == base
                                   else copie.name.replace(copie.suffix,
                                        original.name[len(base.stem):]))
                shutil.copy2(original, cible)
            with sqlite3.connect(f"file:{copie}?mode=ro", uri=True) as cx:
                verdict = cx.execute("PRAGMA quick_check").fetchone()[0]
            if verdict != "ok":
                raise sqlite3.DatabaseError(f"quick_check : {verdict}")
            for original in voisins:
                original.unlink()
            sauvegarde = str(copie)
        except (OSError, sqlite3.DatabaseError) as e:
            return {"ok": False, "message": f"Copie de la base illisible ({e}). "
                                            f"Original laissé en place."}

    # 3. relancer le backend (il recrée une base vide), avec le même DEDALE_DB s'il y en avait un.
    env = {**ENV_ENFANT}
    if "DEDALE_DB" in env_backend:
        env["DEDALE_DB"] = env_backend["DEDALE_DB"]
    journal = open(JOURNAUX / "backend.log", "ab")
    try:
        subprocess.Popen(SERVICES["backend"]["demarre"]["cmd"],
                         cwd=str(RACINE / "backend"), env=env,
                         stdin=subprocess.DEVNULL, stdout=journal,
                         stderr=subprocess.STDOUT, start_new_session=True)
    except OSError as e:
        return {"ok": False, "message": f"Relance du backend impossible : {e}"}
    fin = time.time() + 40
    while time.time() < fin and not service_debout("backend"):
        time.sleep(0.6)
    ok = service_debout("backend")
    noter("Repartir propre", f"base sauvegardée : {sauvegarde or 'aucune'} ; backend {'prêt' if ok else 'pas prêt'}")
    return {"ok": ok, "sauvegarde": sauvegarde,
            "message": "Base vide, backend relancé." if ok
                       else "Base sauvegardée, mais le backend n'a pas redémarré à temps."}


# --- Faux mail et virements --------------------------------------------------------------
def envoyer_mail(cas: str) -> dict:
    if cas not in CAS_MAIL:
        return {"ok": False, "message": f"cas inconnu : {cas}"}
    cmd = ["uv", "run", "python", "envoyer_demo.py", "--cas", cas]
    try:
        r = subprocess.run(cmd, cwd=str(RACINE / "messagerie"), env=ENV_ENFANT,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "message": str(e)}
    sortie = (r.stdout + r.stderr).strip()
    noter(f"Faux mail envoyé : {cas}", sortie[:200])
    return {"ok": r.returncode == 0, "sortie": sortie}


def envoyer_virement(genre: str) -> dict:
    if genre not in VIREMENTS:
        return {"ok": False, "message": f"virement inconnu : {genre}"}
    code, corps = http_post_json("http://127.0.0.1:8712/avertir", VIREMENTS[genre], delai=6.0)
    texte = corps.decode("utf-8", "replace")
    noter(f"Virement ({'RIB changé' if genre == 'rib' else 'normal'})",
          f"app Mac a répondu {code}")
    return {"ok": 200 <= code < 300, "code": code, "reponse": texte}


# --- Journal en direct -------------------------------------------------------------------
def journal_direct() -> dict:
    jeton = jeton_analyste()
    activite, incidents = [], []
    code, corps = http_get(BACKEND + "/api/activite?limite=25", jeton=jeton, delai=3.0)
    if 200 <= code < 300:
        try:
            activite = json.loads(corps).get("activite", [])
        except json.JSONDecodeError:
            pass
    code, corps = http_get(BACKEND + "/api/incidents", jeton=jeton, delai=3.0)
    if 200 <= code < 300:
        try:
            incidents = json.loads(corps).get("incidents", [])
        except json.JSONDecodeError:
            pass
    return {"jeton_present": jeton is not None, "actions": actions(),
            "activite": activite, "incidents": incidents}


# --- Serveur HTTP ------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, obj, code: int = 200) -> None:
        donnees = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(donnees)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(donnees)

    def _fichier(self, chemin: Path, ctype: str) -> None:
        try:
            donnees = chemin.read_bytes()
        except OSError:
            self._json({"erreur": "introuvable"}, 404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(donnees)))
        self.end_headers()
        self.wfile.write(donnees)

    def do_GET(self) -> None:
        chemin = urlparse(self.path).path
        if chemin in ("/", "/index.html"):
            self._fichier(STATIC / "page.html", "text/html; charset=utf-8")
        elif chemin == "/banc.css":
            self._fichier(STATIC / "banc.css", "text/css; charset=utf-8")
        elif chemin == "/banc.js":
            self._fichier(STATIC / "banc.js", "application/javascript; charset=utf-8")
        elif chemin == "/logo.svg":
            self._fichier(STATIC / "logo.svg", "image/svg+xml")
        elif chemin == "/api/etat":
            self._json({"services": etat_services(), "app_mac": etat_app_mac(),
                        "modeles": MODELES, "cas": CAS_MAIL})
        elif chemin == "/api/boite":
            self._json(boite_mails())
        elif chemin == "/api/agent/flux":
            self._json(AGENT.vue())
        elif chemin == "/api/journal":
            self._json(journal_direct())
        else:
            self._json({"erreur": "chemin inconnu"}, 404)

    def do_POST(self) -> None:
        chemin = urlparse(self.path).path
        params = parse_qs(urlparse(self.path).query)

        def p(nom, defaut=""):
            return params.get(nom, [defaut])[0]

        if chemin == "/api/demarrer":
            self._json(demarrer_tout())
        elif chemin == "/api/mail":
            self._json(envoyer_mail(p("cas")))
        elif chemin == "/api/agent":
            modele = p("modele", MODELES[0])
            if modele not in MODELES:
                modele = MODELES[0]
            try:
                essais = max(1, min(3, int(p("essais", "1"))))
            except ValueError:
                essais = 1
            ok, msg = AGENT.lancer(modele, essais)
            noter("Agent IA lancé", f"modèle {modele}, {essais} essai(s)") if ok else None
            self._json({"ok": ok, "message": msg})
        elif chemin == "/api/virement":
            self._json(envoyer_virement(p("genre")))
        elif chemin == "/api/repartir":
            self._json(repartir_propre())
        else:
            self._json({"erreur": "chemin inconnu"}, 404)

    def log_message(self, *a) -> None:  # journal silencieux (le banc a le sien)
        pass


def main() -> None:
    serveur = ThreadingHTTPServer(("127.0.0.1", PORT_BANC), Handler)
    print(f"Banc sAIfe : http://127.0.0.1:{PORT_BANC}")
    noter("Banc démarré", f"port {PORT_BANC}")
    try:
        serveur.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serveur.server_close()


if __name__ == "__main__":
    main()
