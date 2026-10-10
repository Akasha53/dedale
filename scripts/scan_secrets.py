#!/usr/bin/env python3
"""Recherche locale de secrets courants sans jamais afficher les valeurs détectées.

Usage: python3 scripts/scan_secrets.py [--worktree] [--history] [--self-test]
Sans option de portée, les fichiers présents et tous les blobs Git sont examinés.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 1_000_000
PATTERNS = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{70,})\b"),
    "openai_key": re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{30,}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "google_api_key": re.compile(r"\bAIza[A-Za-z0-9_-]{35}\b"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "stripe_secret_key": re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}
ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret|access[_-]?key)"
    r"\s*[=:]\s*['\"]?([^\s'\"#,;]{12,})"
)


def _run(*arguments: str, input_bytes: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *arguments], cwd=ROOT, input=input_bytes,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        # Ne jamais réimprimer stderr : un chemin d'entrée peut contenir du texte sensible.
        raise RuntimeError(f"git {arguments[0]} a échoué (code {result.returncode})")
    return result.stdout


def _entropie(valeur: str) -> float:
    frequences = Counter(valeur)
    longueur = len(valeur)
    return -sum((n / longueur) * math.log2(n / longueur) for n in frequences.values())


def _candidat(valeur: str) -> bool:
    valeur = valeur.strip("'\"`)")
    bas = valeur.lower()
    if len(valeur) < 16 or len(valeur) > 200:
        return False
    if any(mot in bas for mot in ("example", "exemple", "placeholder", "replace", "dummy", "fake")):
        return False
    if valeur.startswith(("$", "{", "<", "[", "os.", "process.", "getenv", "env.")):
        return False
    if valeur.isalpha() or valeur.isdigit():
        return False
    return _entropie(valeur) >= 3.5


def _detections(donnees: bytes) -> list[tuple[int, str]]:
    if b"\0" in donnees[:4096]:
        return []
    resultats = []
    for numero, ligne in enumerate(donnees.decode("utf-8", errors="replace").splitlines(), 1):
        for nom, motif in PATTERNS.items():
            if motif.search(ligne):
                resultats.append((numero, nom))
        if any(_candidat(m.group(1)) for m in ASSIGNMENT.finditer(ligne)):
            resultats.append((numero, "affectation_suspecte"))
    return sorted(set(resultats))


def _emplacement_sans_valeur(chemin: str) -> str:
    """Évite aussi de recopier une clé qui aurait été placée dans un nom de fichier."""
    propre = "".join(c if c.isprintable() else "?" for c in chemin)
    for motif in PATTERNS.values():
        propre = motif.sub("[masqué]", propre)
    return ASSIGNMENT.sub(lambda m: m.group(0).replace(m.group(1), "[masqué]"), propre)


def _worktree() -> tuple[list[tuple[str, str, int, str]], int, int]:
    noms = _run("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    fichiers = [Path(n.decode("utf-8", errors="surrogateescape")) for n in noms.split(b"\0") if n]
    resultats = []
    examines = ignores = 0
    for relatif in fichiers:
        chemin = ROOT / relatif
        if not chemin.is_file() or chemin.is_symlink():
            ignores += 1
            continue
        if chemin.stat().st_size > MAX_BYTES:
            ignores += 1
            continue
        donnees = chemin.read_bytes()
        if b"\0" in donnees[:4096]:
            ignores += 1
            continue
        examines += 1
        for ligne, categorie in _detections(donnees):
            resultats.append(("travail", relatif.as_posix(), ligne, categorie))
    return resultats, examines, ignores


def _history() -> tuple[list[tuple[str, str, int, str]], int, int]:
    objets = []
    for ligne in _run("rev-list", "--objects", "--all").splitlines():
        sha, _, nom = ligne.partition(b" ")
        objets.append((sha.decode("ascii"), nom.decode("utf-8", errors="replace")))
    if not objets:
        return [], 0, 0
    requete = "".join(f"{sha}\n" for sha, _ in objets).encode("ascii")
    infos = _run("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", input_bytes=requete)
    types = {}
    for ligne in infos.splitlines():
        sha, type_, taille = ligne.decode("ascii").split()
        types[sha] = (type_, int(taille))

    resultats = []
    examines = ignores = 0
    for sha, nom in objets:
        type_, taille = types[sha]
        if type_ not in ("blob", "commit", "tag"):
            continue
        if taille > MAX_BYTES:
            ignores += 1
            continue
        donnees = _run("cat-file", type_, sha)
        if type_ in ("commit", "tag"):
            # Les en-têtes Git ne sont pas le message rédigé par l'utilisateur.
            donnees = donnees.partition(b"\n\n")[2]
        if b"\0" in donnees[:4096]:
            ignores += 1
            continue
        examines += 1
        for numero, categorie in _detections(donnees):
            objet = (nom or "blob") if type_ == "blob" else type_
            resultats.append(("historique", f"{objet}@{sha[:12]}", numero, categorie))
    return resultats, examines, ignores


def _self_test() -> bool:
    positifs = [
        b"value='ghp_" + b"A" * 36 + b"'",
        b"value='AKIA" + b"A1" * 8 + b"'",
        b"-----BEGIN " + b"PRIVATE KEY-----",
    ]
    negatifs = [b"API_KEY=${DEDALE_API_KEY}", b"password=example-placeholder-value"]
    nom_piege = "cle-ghp_" + "A" * 36
    return (
        all(_detections(v) for v in positifs)
        and all(not _detections(v) for v in negatifs)
        and "[masqué]" in _emplacement_sans_valeur(nom_piege)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", action="store_true", help="fichiers suivis et non ignorés présents")
    parser.add_argument("--history", action="store_true", help="blobs accessibles depuis toutes les refs Git")
    parser.add_argument("--self-test", action="store_true", help="vérifie le détecteur avec des chaînes synthétiques")
    args = parser.parse_args()
    if args.self_test:
        ok = _self_test()
        print("Auto-test : réussi" if ok else "Auto-test : échec")
        return 0 if ok else 2
    portees = []
    if args.worktree or not args.history:
        portees.append(_worktree)
    if args.history or not args.worktree:
        portees.append(_history)
    total = []
    for scanner in portees:
        resultats, examines, ignores = scanner()
        total.extend(resultats)
        unite = "objets" if scanner is _history else "fichiers"
        print(f"{scanner.__name__[1:]} : {examines} {unite} examinés, {ignores} ignorés, {len(resultats)} alertes")
    for portee, chemin, ligne, categorie in total:
        print(f"{portee} : {_emplacement_sans_valeur(chemin)}:{ligne} : {categorie}")
    print(f"Total : {len(total)} alertes ; aucune valeur affichée")
    return 1 if total else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as exc:
        print(f"Scan interrompu : {type(exc).__name__}", file=sys.stderr)
        sys.exit(2)
