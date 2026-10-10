"""Faux SIEM et faux Teams pour la démo : affiche chaque trame syslog et chaque webhook reçus.

    uv run python -m app.recepteur_siem [--syslog-port N] [--webhook-port N]

Écoute seulement sur 127.0.0.1 : syslog en UDP et en TCP sur le même port (trame RFC 5424, CEF
dedans ; en TCP, trames préfixées par leur longueur, RFC 6587), et webhooks HTTP (formats Slack,
Teams ou JSON de Dédale). Imprime les lignes `export …` à poser avant de lancer le backend.
Rien ne quitte la machine. Sur le modèle de `recepteur_demo` (webhook Slack seul).
"""

from __future__ import annotations

import argparse
import json
import re
import socketserver
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_TAILLE_MAX = 1_000_000
_SYSLOG = re.compile(r"^<(\d{1,3})>1 (\S+) (\S+) (\S+) (\S+) (\S+) (\S+) (.*)$", re.DOTALL)
_EXT = re.compile(r"(\w+)=((?:\\.|[^\\])*?)(?=\s\w+=|$)")


def lire_cef(message: str) -> dict | None:
    """Découpe une ligne CEF : en-tête (sept champs, `\\|` échappé) et extensions."""
    if not message.startswith("CEF:"):
        return None
    champs, courant, i = [], "", 0
    while i < len(message) and len(champs) < 7:
        c = message[i]
        if c == "\\" and i + 1 < len(message):
            courant += message[i + 1]
            i += 2
            continue
        if c == "|":
            champs.append(courant)
            courant = ""
        else:
            courant += c
        i += 1
    if len(champs) < 7:
        return None
    ext = {}
    for cle, valeur in _EXT.findall(message[i:]):
        ext[cle] = valeur.replace("\\=", "=").replace("\\n", "\n").replace("\\\\", "\\")
    return {"version": champs[0].split(":", 1)[1], "fournisseur": champs[1], "produit": champs[2],
            "version_produit": champs[3], "signature": champs[4], "nom": champs[5],
            "severite": int(champs[6]) if champs[6].isdigit() else champs[6], "extensions": ext}


def lire_trame(trame: str) -> dict:
    m = _SYSLOG.match(trame.strip())
    if not m:
        return {"brut": trame.strip()}
    pri = int(m.group(1))
    return {"facilite": pri // 8, "severite_syslog": pri % 8, "horodatage": m.group(2), "hote": m.group(3),
            "application": m.group(4), "msgid": m.group(6), "message": m.group(8), "cef": lire_cef(m.group(8))}


def formater_trame(t: dict) -> str:
    cef = t.get("cef")
    if not cef:
        return f"syslog · {t.get('brut') or t.get('message')}"
    ext = cef["extensions"]
    lignes = ["", "─" * 64,
              f"SIEM · {t['horodatage']} · local{t['facilite'] - 16} · sévérité CEF {cef['severite']}",
              f"{cef['nom']}  [{cef['signature']}]"]
    if ext.get("msg"):
        lignes.append(ext["msg"])
    for cle, lib in (("cs1", "incident"), ("cs3", "technique"), ("suser", "utilisateur"), ("dhost", "domaine"),
                     ("cs6", "console")):
        if ext.get(cle):
            lignes.append(f"  {lib} : {ext[cle]}")
    lignes.append("─" * 64)
    return "\n".join(lignes)


def formater_webhook(message: dict) -> str:
    """Rend lisible un message Slack (blocs), Teams (carte adaptative) ou JSON de Dédale."""
    lignes = ["", "─" * 64]
    if message.get("type") == "message" and message.get("attachments"):
        carte = (message["attachments"][0] or {}).get("content") or {}
        lignes.append("TEAMS")
        for bloc in carte.get("body") or []:
            if bloc.get("type") == "TextBlock":
                lignes.append(str(bloc.get("text")))
            elif bloc.get("type") == "FactSet":
                lignes += [f"  {f.get('title')} : {f.get('value')}" for f in bloc.get("facts") or []]
        for a in carte.get("actions") or []:
            lignes.append(f"→ {a.get('title')} : {a.get('url')}")
    elif message.get("blocks"):
        lignes.append("SLACK")
        for bloc in message["blocks"]:
            texte = bloc.get("text")
            if isinstance(texte, dict):
                lignes.append(str(texte.get("text")).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
            for champ in bloc.get("fields") or []:
                lignes.append("  " + str(champ.get("text")).replace("*", "").replace("\n", " : ", 1))
    elif message.get("source") == "dedale":
        lignes.append(f"JSON · {message.get('destinataire')} · {message.get('regle')}")
        lignes += [str(message.get("titre")), str(message.get("texte")), f"→ {message.get('lien')}"]
    else:
        lignes.append(json.dumps(message, ensure_ascii=False)[:2000])
    lignes.append("─" * 64)
    return "\n".join(lignes)


class _Webhook(BaseHTTPRequestHandler):
    server_version = "DedaleRecepteurSiem/1.0"

    def do_POST(self):  # noqa: N802
        try:
            taille = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            taille = -1
        if taille < 0 or taille > _TAILLE_MAX:
            self._repondre(413, b"trop gros")
            return
        try:
            message = json.loads(self.rfile.read(taille) or b"{}")
            if not isinstance(message, dict):
                raise ValueError
        except ValueError:
            self._repondre(400, b"json invalide")
            return
        self.server.recus.append(message)
        if self.server.afficher:
            print(formater_webhook(message), flush=True)
        self._repondre(200, b"ok")

    def _repondre(self, code: int, corps: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


class _Udp(socketserver.BaseRequestHandler):
    def handle(self):
        donnees = self.request[0]
        self.server.recepteur.recevoir(donnees.decode("utf-8", "replace"))


class _Tcp(socketserver.StreamRequestHandler):
    def handle(self):
        lecteur = self.rfile
        while True:
            longueur = b""
            while True:
                c = lecteur.read(1)
                if not c:
                    return
                if c == b" ":
                    break
                if not c.isdigit() or len(longueur) > 7:
                    # Trame sans préfixe de longueur : lecture à la ligne (non transparent).
                    reste = lecteur.readline()
                    self.server.recepteur.recevoir((longueur + c + reste).decode("utf-8", "replace"))
                    longueur = b""
                    continue
                longueur += c
            trame = lecteur.read(int(longueur))
            self.server.recepteur.recevoir(trame.decode("utf-8", "replace"))


class _ServeurUdp(socketserver.ThreadingUDPServer):
    allow_reuse_address = True


class _ServeurTcp(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Recepteur:
    """Syslog UDP + TCP sur un même port, et webhook HTTP. `trames` et `webhooks` gardent tout."""

    def __init__(self, syslog_port: int = 0, webhook_port: int = 0, afficher: bool = True) -> None:
        self.afficher = afficher
        self.trames: list[dict] = []
        self.verrou = threading.Lock()
        self.tcp = _ServeurTcp(("127.0.0.1", syslog_port), _Tcp)
        port = self.tcp.server_address[1]
        self.udp = _ServeurUdp(("127.0.0.1", port), _Udp)
        self.tcp.recepteur = self.udp.recepteur = self
        self.http = ThreadingHTTPServer(("127.0.0.1", webhook_port), _Webhook)
        self.http.recus = []
        self.http.afficher = afficher
        self._fils: list[threading.Thread] = []

    @property
    def webhooks(self) -> list[dict]:
        return self.http.recus

    def recevoir(self, trame: str) -> None:
        lue = lire_trame(trame)
        with self.verrou:
            self.trames.append(lue)
        if self.afficher:
            print(formater_trame(lue), flush=True)

    def adresses(self) -> dict:
        port = self.tcp.server_address[1]
        return {"udp": f"udp://127.0.0.1:{port}", "tcp": f"tcp://127.0.0.1:{port}",
                "webhook": f"http://127.0.0.1:{self.http.server_address[1]}"}

    def demarrer(self) -> "Recepteur":
        for serveur in (self.tcp, self.udp, self.http):
            fil = threading.Thread(target=serveur.serve_forever, daemon=True)
            fil.start()
            self._fils.append(fil)
        return self

    def arreter(self) -> None:
        for serveur in (self.tcp, self.udp, self.http):
            serveur.shutdown()
            serveur.server_close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Faux SIEM (syslog CEF) et faux Teams (webhook) pour la démo sAIfe.")
    p.add_argument("--syslog-port", type=int, default=0, help="port syslog UDP et TCP (défaut : un port libre)")
    p.add_argument("--webhook-port", type=int, default=0, help="port HTTP des webhooks (défaut : un port libre)")
    args = p.parse_args(argv)
    r = Recepteur(args.syslog_port, args.webhook_port).demarrer()
    a = r.adresses()
    print(f"Faux SIEM à l'écoute : {a['udp']} et {a['tcp']}")
    print(f"Faux Teams et Slack à l'écoute : {a['webhook']}/soc et {a['webhook']}/validation")
    print("Avant de lancer le backend :")
    print(f"  export DEDALE_SYSLOG={a['udp']}")
    print(f"  export DEDALE_NOTIF_SOC_URL={a['webhook']}/soc DEDALE_NOTIF_SOC_FORMAT=teams")
    print(f"  export DEDALE_NOTIF_VALIDATION_URL={a['webhook']}/validation DEDALE_NOTIF_VALIDATION_FORMAT=json",
          flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        r.arreter()
    return 0


if __name__ == "__main__":
    sys.exit(main())
