#!/usr/bin/env python3
"""Musique de la vidéo de démo de sAIfe, composée par synthèse. Aucune dépendance : la
bibliothèque standard et `wave`. Aucun échantillon, aucune œuvre existante : pas de droits.

    python3 musique.py                       # 150 s, 48 kHz, écrit musique-essai.wav ici
    python3 musique.py --sortie /tmp/m.wav --duree 150
    python3 musique.py --taux 16000          # essai rapide, qualité réduite

Tempo 80 pulsations par minute, 4/4 : une pulsation = 0,75 s, une mesure = 3,0 s, un demi-
mesure (deux pulsations) = 1,5 s. Tous les plans du découpage durent un multiple de 1,5 s,
donc chaque coupe tombe sur une pulsation, à 24, 25 ou 30 images par seconde
(1,5 s = 36, 37,5 ou 45 images : à 25 i/s, caler les coupes sur 3,0 s).

Le plan (secondes, voir GUIDE_VIDEO.md) :
    0,0 - 22,5   acte 1, la comptable est piégée : nappe en la mineur, piano épars
    22,5 - 25,5  SILENCE TOTAL, calé sur l'arrêt sur image (réverbération coupée aussi)
    25,5 - 33,0  montée : bourdon grave, glissando, bruit filtré, ronronnement de cassette
    33,0         coup sourd de fin de bande, puis accord majeur : « Stop. »
    33,0 - 37,5  carton « Stop. » : accord de do majeur arpégé vite, puis la nappe seule
    37,5 - 60,0  acte 2, sAIfe arrête le virement : sol, la mineur, fa, sol, do ; arpège clair
    60,0 - 70,5  montage des garde-fous : une note pincée à chaque coupe (toutes les 1,5 s)
    70,5 - 138,0 tour de la console : progression en boucle, arpège de croches, une basse à 102 s
    138,0 -      logo : accord final à longue résonance, ni coupe sèche ni crescendo
"""
from __future__ import annotations

import argparse
import math
import random
import sys
import wave
from array import array
from itertools import repeat
from operator import add, mul
from pathlib import Path

BPM = 80
PULSE = 60.0 / BPM          # 0,75 s
BAR = 4 * PULSE             # 3,0 s
SR = 48000                  # fixé dans main() selon --taux

# Cues en secondes. Un seul endroit à modifier si le montage bouge.
T_SILENCE = (22.5, 25.5)
T_MONTEE = (25.5, 33.0)
T_REMBOBINAGE = (28.5, 33.0)
T_STOP = 33.0
T_ACTE2 = (37.5, 60.0)
T_MONTAGE = (60.0, 70.5)
T_TOUR = (70.5, 138.0)
T_LOGO = 138.0
T_FINANCE = 102.0
IMPACT = False          # choc sourd sur le gel (l'argent part) ; v2
ACCENT = None           # instant d'un accent clair (sAIfe coupe l'agent) ; v2


def mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def sec(t: float) -> int:
    return int(round(t * SR))


class Piste:
    """Deux canaux flottants. `mixer` ajoute un segment mono à un instant donné."""

    def __init__(self, n: int):
        self.n = n
        self.g = array("d", bytes(8 * n))
        self.d = array("d", bytes(8 * n))

    def mixer(self, debut: float, seg, gauche: float = 1.0, droite: float = 1.0) -> None:
        a = sec(debut)
        b = min(a + len(seg), self.n)
        if b <= a or a < 0:
            return
        if b - a < len(seg):
            seg = seg[: b - a]
        for canal, gain in ((self.g, gauche), (self.d, droite)):
            if gain:
                canal[a:b] = array("d", map(add, canal[a:b], map(mul, seg, repeat(gain))))


def enveloppe(n: int, attaque: float, relache: float) -> list[float]:
    """Attaque et relâchement en sinus carré, plateau à 1 entre les deux."""
    a, r = max(1, sec(attaque)), max(1, sec(relache))
    a, r = min(a, n // 2), min(r, n // 2)
    env = [1.0] * n
    for i in range(a):
        env[i] = math.sin(0.5 * math.pi * i / a) ** 2
    for i in range(r):
        env[n - 1 - i] = math.sin(0.5 * math.pi * i / r) ** 2
    return env


def somme(a, b):
    return array("d", map(add, a, b))


def nappe(notes: list[int], duree: float, niveau: float = 0.05, attaque: float = 1.4,
          relache: float = 2.2, vibrato: float = 0.0):
    """Nappe douce : chaque note est un sinus, une octave au-dessus à faible niveau, doublée
    avec un léger désaccord pour que la nappe respire. Retourne (gauche, droite)."""
    n = sec(duree)
    env = enveloppe(n, attaque, relache)
    sorties = []
    for cote, cents in ((0, -4.0), (1, +4.0)):
        tot = array("d", bytes(8 * n))
        for m in notes:
            f = mtof(m) * 2 ** (cents / 1200)
            w1, w2 = 2 * math.pi * f / SR, 2 * math.pi * 2 * f / SR
            ph = random.random() * 6.28
            if vibrato:
                lfo = 2 * math.pi * 0.17 / SR
                seg = [math.sin(w1 * i + ph + vibrato * math.sin(lfo * i)) + 0.18 * math.sin(w2 * i + ph)
                       for i in range(n)]
            else:
                seg = [math.sin(w1 * i + ph) + 0.18 * math.sin(w2 * i + ph) for i in range(n)]
            tot = somme(tot, seg)
        sorties.append(array("d", (v * e * niveau for v, e in zip(tot, env))))
    return sorties


_CACHE_PIANO: dict[tuple[float, float], array] = {}


def piano(m: float, duree: float = 3.5, velocite: float = 0.5):
    """Piano additif : partiels légèrement inharmoniques, chacun avec sa décroissance, un
    léger coup de marteau au début. Les notes graves durent plus, les aiguës moins.
    Le rendu de base est mis en cache : une même note revient des dizaines de fois dans l'arpège."""
    cle = (m, duree)
    if cle not in _CACHE_PIANO:
        f = mtof(m)
        n = sec(duree)
        base = max(0.6, 2.8 - (m - 36) * 0.045)             # constante de temps du fondamental, en s
        parts = [(1, 1.0, 1.0), (2, 0.50, 0.62), (3, 0.28, 0.42), (4, 0.15, 0.30), (5, 0.07, 0.22)]
        out = array("d", bytes(8 * n))
        b = 0.00018 * (1 + (m - 60) / 40)                    # inharmonicité
        for k, amp, ratio in parts:
            fk = f * k * math.sqrt(1 + b * k * k)
            if fk > 0.45 * SR:
                continue
            w = 2 * math.pi * fk / SR
            tau = base * ratio * SR
            out = somme(out, [amp * math.sin(w * i) * math.exp(-i / tau) for i in range(n)])
        attaque = 0.004 * SR
        for i in range(int(attaque)):
            out[i] *= i / attaque
        fin = min(n, int(0.25 * SR))
        for i in range(fin):
            out[n - 1 - i] *= i / fin
        rnd = random.random
        for i in range(int(0.012 * SR)):                     # marteau
            out[i] += (rnd() * 2 - 1) * 0.05 * (1 - i / (0.012 * SR))
        _CACHE_PIANO[cle] = out
    return array("d", map(mul, _CACHE_PIANO[cle], repeat(velocite * 0.35)))


def pincee(m: float, duree: float = 0.9, velocite: float = 0.5):
    """Note pincée courte, sinus plus triangle léger, pour le montage."""
    f = mtof(m)
    n = sec(duree)
    w = 2 * math.pi * f / SR
    tau = 0.16 * SR
    out = array("d", (velocite * 0.30 * (math.sin(w * i) + 0.25 * math.sin(3 * w * i) / 3 + 0.12 * math.sin(2 * w * i))
                      * math.exp(-i / tau) for i in range(n)))
    for i in range(min(n, int(0.003 * SR))):
        out[i] *= i / (0.003 * SR)
    return out


def bruit(duree: float, lisse_depart: float, lisse_fin: float):
    """Bruit blanc passé dans un filtre à un pôle dont la coupure monte : le souffle de la montée."""
    n = sec(duree)
    rnd = random.random
    y = 0.0
    out = array("d", bytes(8 * n))
    for i in range(n):
        a = lisse_depart + (lisse_fin - lisse_depart) * (i / n) ** 2
        y += a * ((rnd() * 2 - 1) - y)
        out[i] = y
    return out


def montee(debut: float, fin: float, rembobinage_debut: float):
    """La montée avant « Stop » : bourdon grave, glissando exponentiel, souffle qui s'ouvre, puis,
    pendant le rembobinage, un ronronnement de cassette (bruit modulé à 17 Hz, hauteur qui grimpe)."""
    duree = fin - debut
    n = sec(duree)
    env = [min(1.0, (i / n) ** 1.6) for i in range(n)]
    fo = 2 * math.pi / SR
    gliss, phase = array("d", bytes(8 * n)), 0.0
    for i in range(n):
        p = i / n
        f = 110.0 * (7.0 ** p)                               # 110 Hz vers 770 Hz
        phase += fo * f
        gliss[i] = math.sin(phase) + 0.4 * math.sin(2 * phase)
    bourdon = [math.sin(fo * 55.0 * i) + 0.5 * math.sin(fo * 110.0 * i) for i in range(n)]
    souffle = bruit(duree, 0.01, 0.35)
    mix = array("d", (e * (0.064 * g + 0.072 * b + 0.48 * s) for e, g, b, s in zip(env, gliss, bourdon, souffle)))
    # ronronnement
    dr = fin - rembobinage_debut
    nr = sec(dr)
    off = sec(rembobinage_debut - debut)
    rnd = random.random
    y = 0.0
    ph = 0.0
    for i in range(nr):
        p = i / nr
        a = 0.08 + 0.35 * p
        y += a * ((rnd() * 2 - 1) - y)
        ph += fo * (180 + 900 * p)
        flutter = 0.55 + 0.45 * math.sin(2 * math.pi * 17.0 * i / SR)
        mix[off + i] += (0.07 * y * flutter + 0.012 * math.sin(ph)) * (0.4 + 0.6 * p)
    return mix


def impact_sourd():
    """Choc sourd et grave pour le gel (l'argent part) : plus bas et plus étouffé que la fin de bande."""
    n = sec(0.7)
    fo = 2 * math.pi / SR
    out = array("d", bytes(8 * n))
    for i in range(n):
        t = i / SR
        out[i] = 0.5 * math.sin(fo * (50 - 16 * t) * i) * math.exp(-t / 0.22)
    return out


def coup_sourd():
    """Fin de bande : un choc grave court, et un clic."""
    n = sec(0.9)
    fo = 2 * math.pi / SR
    out = array("d", bytes(8 * n))
    rnd = random.random
    for i in range(n):
        t = i / SR
        thump = math.sin(fo * (62 - 20 * t) * i) * math.exp(-t / 0.16)
        clic = (rnd() * 2 - 1) * math.exp(-t / 0.006) * 0.25
        out[i] = 0.40 * thump + clic
    return out


# --- harmonie ---------------------------------------------------------------------------
# accords en notes MIDI (60 = do central)
AM9 = [45, 52, 59, 60]            # la mineur 9 : la2 mi3 si3 do4
FMAJ7 = [41, 48, 52, 57]          # fa majeur 7
DM9 = [38, 45, 52, 57]            # ré mineur : ré2 la2 mi3 la3
CMAJ9 = [48, 55, 59, 62]          # do majeur 9 : do3 sol3 si3 ré4
G6 = [43, 50, 55, 59]             # sol, ré, sol, si
AMIN = [45, 52, 57, 60]
F6 = [41, 48, 53, 57]

ACTE1 = [AM9, FMAJ7, AM9, DM9, AM9]                # 5 accords de 4,5 s = 22,5 s
ACTE2 = [G6, AMIN, FMAJ7, G6, CMAJ9]               # 5 accords de 4,5 s = 22,5 s ; do majeur sonne déjà sur « Stop »
TOUR = [CMAJ9, G6, AMIN, F6]                       # boucle de 4 accords de 6 s


def motif_acte1(accord: list[int], t0: float, rng: random.Random, p: Piste, discret: bool):
    hauts = [accord[2] + 12, accord[3] + 12, accord[1] + 12, accord[3] + 24]
    quand = [0.0, 1.5, 2.25, 3.0] if not discret else [0.0, 2.25]
    for k, dt in enumerate(quand):
        m = hauts[k % len(hauts)]
        v = 0.55 - 0.08 * (k % 2)
        n = piano(m, 3.8, v)
        pan = 0.5 + 0.25 * math.sin(m)
        p.mixer(t0 + dt + rng.uniform(-0.012, 0.012), n, 1 - pan * 0.5, 0.5 + pan * 0.5)


def arpege(accord: list[int], t0: float, duree: float, rng: random.Random, p: Piste, niveau: float):
    """Croches (0,375 s), notes de l'accord une octave plus haut, alternance gauche et droite."""
    haut = [accord[1] + 12, accord[2] + 12, accord[3] + 12, accord[2] + 12, accord[3] + 24, accord[2] + 12]
    k = 0
    t = 0.0
    while t < duree - 0.2:
        m = haut[k % len(haut)]
        v = niveau * (1.0 if k % 4 == 0 else 0.7)
        n = piano(m, 1.9, v)
        cote = 0.25 if k % 2 == 0 else 0.75
        p.mixer(t0 + t + rng.uniform(-0.006, 0.006), n, 1 - cote * 0.6, 0.4 + cote * 0.6)
        k += 1
        t += PULSE / 2
    return


def accords_acte2() -> list[list[int]]:
    """Un accord par plan de 4,5 s ; l'acte finit toujours sur sol puis do majeur (5 plans : ACTE2)."""
    n = max(2, round((T_ACTE2[1] - T_ACTE2[0]) / 4.5))
    milieu = [G6, AMIN, FMAJ7, AMIN]
    return [milieu[i % len(milieu)] for i in range(n - 2)] + [G6, CMAJ9]


def composer(duree: float) -> Piste:
    random.seed(80)
    rng = random.Random(80)
    p = Piste(sec(duree))
    # --- acte 1 : nappe + piano épars, jusqu'au gel (silence)
    i = 0
    t0 = 0.0
    while t0 < T_SILENCE[0] - 0.1:
        ac = ACTE1[i % len(ACTE1)]
        g, d = nappe(ac, 4.5 + 2.0, niveau=0.055, attaque=1.6, relache=2.4)
        p.mixer(t0, g, 1, 0)
        p.mixer(t0, d, 0, 1)
        motif_acte1(ac, t0 + 0.75 if i == 0 else t0, rng, p, discret=(i == 0))
        i += 1
        t0 += 4.5
    if IMPACT:
        # choc sourd sur le gel, juste avant le silence : on entend l'attaque, le silence coupe la queue
        p.mixer(max(0.0, T_SILENCE[0] - 0.22), impact_sourd(), 1, 1)
    # --- montée jusqu'à « Stop » : on ne laisse pas de nappe, elle viendrait d'avant le silence
    m = montee(T_MONTEE[0], T_STOP - 0.15, T_REMBOBINAGE[0])
    p.mixer(T_MONTEE[0], m, 0.9, 0.9)
    # --- « Stop » : choc, puis accord de do majeur qui s'ouvre sous le carton
    p.mixer(T_STOP, coup_sourd(), 1, 1)
    g, d = nappe(CMAJ9, 4.5 + 2.4, niveau=0.06, attaque=0.25, relache=2.6)
    p.mixer(T_STOP, g, 1, 0)
    p.mixer(T_STOP, d, 0, 1)
    for k, m_ in enumerate([60, 64, 67, 71, 74]):          # accord arpégé rapide sur « Stop »
        p.mixer(T_STOP + 0.04 + 0.11 * k, piano(m_, 4.5, 0.55), 1, 1)
    # --- acte 2 : même scène, tonalité majeure
    for i, ac in enumerate(accords_acte2()):
        t0 = T_ACTE2[0] + i * 4.5
        g, d = nappe(ac, 4.5 + 2.4, niveau=0.06, attaque=1.0, relache=2.6)
        p.mixer(t0, g, 1, 0)
        p.mixer(t0, d, 0, 1)
        arpege(ac, t0, 4.5, rng, p, 0.30 if i < len(accords_acte2()) - 1 else 0.22)
    # --- montage : une note pincée à chaque coupe de 1,5 s
    gamme = [72, 76, 79, 81, 84, 79, 76, 81]               # pentatonique de do, montante puis descendante
    k = 0
    t = T_MONTAGE[0]
    while t < T_MONTAGE[1] - 0.1:
        p.mixer(t, pincee(gamme[k % len(gamme)], 1.1, 0.55 + 0.1 * (k % 2)), 0.9 - 0.1 * (k % 2), 0.8 + 0.1 * (k % 2))
        k += 1
        t += 1.5
    for i in range(int((T_MONTAGE[1] - T_MONTAGE[0]) / 6.0) + 1):
        ac = TOUR[i % len(TOUR)]
        t0 = T_MONTAGE[0] + i * 6.0
        g, d = nappe(ac, 6.0 + 2.4, niveau=0.05, attaque=1.2, relache=2.6)
        p.mixer(t0, g, 1, 0)
        p.mixer(t0, d, 0, 1)
    # --- tour de la console : boucle, arpège, couches ajoutées
    t = T_TOUR[0]
    i = 0
    while t < T_TOUR[1] - 0.1:
        ac = TOUR[i % len(TOUR)]
        d = min(6.0, T_TOUR[1] - t)
        g, dr = nappe(ac, d + 2.6, niveau=0.055, attaque=1.0, relache=2.8)
        p.mixer(t, g, 1, 0)
        p.mixer(t, dr, 0, 1)
        niveau = 0.26 + 0.05 * min(2, (t - T_TOUR[0]) / 24.0)       # l'arpège gagne un peu
        arpege(ac, t, d, rng, p, niveau)
        if t >= T_FINANCE:                                        # validation de la finance : une basse
            p.mixer(t, piano(ac[0] - 12, 5.8, 0.35), 1, 1)
        t += d
        i += 1
    # --- logo : accord final, longue résonance
    g, d = nappe(CMAJ9 + [72], duree - T_LOGO, niveau=0.06, attaque=1.8, relache=duree - T_LOGO - 0.5)
    p.mixer(T_LOGO, g, 1, 0)
    p.mixer(T_LOGO, d, 0, 1)
    for k, (m_, dt, v) in enumerate([(36, 0.0, 0.6), (60, 0.15, 0.5), (67, 0.9, 0.4), (71, 1.8, 0.35), (74, 2.9, 0.3),
                                     (79, 4.3, 0.25), (83, 6.5, 0.18)]):
        p.mixer(T_LOGO + dt, piano(m_, 9.0 if k < 2 else 6.0, v), 0.95, 0.95)
    if ACCENT is not None:                                        # sAIfe coupe l'agent : deux notes claires
        for k, m_ in enumerate([72, 79]):
            p.mixer(ACCENT + 0.03 * k, piano(m_, 2.4, 0.5), 1, 1)
    return p


# --- réverbération, silence, sortie ---------------------------------------------------------

def passe_bas(x, a: float):
    y = array("d", bytes(8 * len(x)))
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def peigne(x, d: int, g: float):
    n = len(x)
    y = array("d", x)
    for s in range(d, n, d):
        e = min(s + d, n)
        prec = y[s - d: e - d]
        y[s:e] = array("d", map(add, y[s:e], map(mul, prec, repeat(g))))
    return y


def passe_tout(x, d: int, g: float):
    n = len(x)
    y = array("d", bytes(8 * n))
    for s in range(0, n, d):
        e = min(s + d, n)
        xb = x[s:e]
        terme = array("d", map(mul, xb, repeat(-g)))
        if s:
            xp = x[s - d: e - d]
            yp = y[s - d: e - d]
            terme = array("d", map(add, map(add, terme, xp), map(mul, yp, repeat(g))))
        y[s:e] = terme
    return y


def reverbere(x, decalage: int):
    k = SR / 44100
    delais = [int((v + decalage) * k) for v in (2309, 2711, 3181, 3571)]
    peignes = [peigne(x, d, 0.90) for d in delais]
    tot = array("d", bytes(8 * len(x)))
    for c in peignes:
        tot = somme(tot, c)
    tot = array("d", map(mul, tot, repeat(0.25)))
    tot = passe_tout(tot, int(556 * k), 0.5)
    tot = passe_tout(tot, int(441 * k), 0.5)
    return passe_bas(tot, 0.35)


def finir(p: Piste, duree: float, sortie: Path) -> dict:
    n = p.n
    # envoi à la réverbération : tout, filtré pour garder la douceur
    env_g = passe_bas(p.g, 0.5)
    env_d = passe_bas(p.d, 0.5)
    hum_g = reverbere(env_g, 0)
    hum_d = reverbere(env_d, 31)
    g = array("d", map(add, p.g, map(mul, hum_g, repeat(0.55))))
    d = array("d", map(add, p.d, map(mul, hum_d, repeat(0.55))))
    # silence total : tout se tait à 22,5 s, y compris la queue de réverbération
    a, b = sec(T_SILENCE[0]), sec(T_SILENCE[1])
    f = sec(0.015)
    for canal in (g, d):
        for i in range(f):
            canal[a - f + i] *= 1 - i / f
        for i in range(a, b):
            canal[i] = 0.0
    # début et fin
    entree = sec(1.5)
    sortie_f = sec(3.0)
    for canal in (g, d):
        for i in range(entree):
            canal[i] *= (i / entree) ** 2
        for i in range(sortie_f):
            canal[n - 1 - i] *= (i / sortie_f) ** 2
    crete = max(max(map(abs, g)), max(map(abs, d)), 1e-9)
    gain = 0.60 / crete                                          # crête à -4,4 dBFS
    out = array("h", bytes(2 * 2 * n))
    tanh = math.tanh
    for i in range(n):
        out[2 * i] = int(32767 * tanh(g[i] * gain * 1.1) / tanh(1.1))
        out[2 * i + 1] = int(32767 * tanh(d[i] * gain * 1.1) / tanh(1.1))
    if sys.byteorder == "big":
        out.byteswap()
    with wave.open(str(sortie), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(out.tobytes())
    return {"duree": n / SR, "gain": gain}


def main() -> int:
    global SR, T_ACTE2, T_MONTAGE, T_TOUR, T_LOGO, T_FINANCE
    global T_SILENCE, T_MONTEE, T_REMBOBINAGE, T_STOP, IMPACT, ACCENT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sortie", default=str(Path(__file__).with_name("musique-essai.wav")))
    ap.add_argument("--duree", type=float, default=150.0, help="secondes (150 par défaut, 140 au moins)")
    ap.add_argument("--taux", type=int, default=48000, help="fréquence d'échantillonnage")
    # Montage v1 et suivants : les cues se règlent sans toucher au code (voir montage.sh).
    ap.add_argument("--acte2-fin", type=float, help=f"fin de l'acte 2 ({T_ACTE2[1]} par défaut)")
    ap.add_argument("--montage-fin", type=float, help=f"fin des notes pincées ({T_MONTAGE[1]} par défaut)")
    ap.add_argument("--logo", type=float, help=f"début du logo ({T_LOGO} par défaut)")
    ap.add_argument("--finance", type=float, help=f"entrée de la basse de piano ({T_FINANCE} par défaut)")
    # v2 : gel dramatique plus tôt, Stop plus court, choc sourd et accent
    ap.add_argument("--freeze", type=float, help="instant du gel, début du silence (22,5 par défaut)")
    ap.add_argument("--silence-duree", type=float, default=3.0, help="durée du silence (3 par défaut)")
    ap.add_argument("--stop", type=float, help="instant du choc « Stop » (33 par défaut)")
    ap.add_argument("--rewind", type=float, help="début du rembobinage (28,5 par défaut)")
    ap.add_argument("--acte2-debut", type=float, help="début des accords de l'acte 2 (37,5 par défaut)")
    ap.add_argument("--impact", action="store_true", help="choc sourd sur le gel")
    ap.add_argument("--accent", type=float, help="instant d'un accent clair (sAIfe coupe l'agent)")
    a = ap.parse_args()
    if a.freeze is not None or a.silence_duree != 3.0:
        base = a.freeze if a.freeze is not None else T_SILENCE[0]
        T_SILENCE = (base, base + a.silence_duree)
    if a.stop is not None:
        T_STOP = a.stop
    if a.freeze is not None or a.stop is not None or a.rewind is not None or a.silence_duree != 3.0:
        T_REMBOBINAGE = (a.rewind if a.rewind is not None else T_SILENCE[1], T_STOP)
        T_MONTEE = (T_SILENCE[1], T_STOP)
    if a.acte2_debut is not None:
        T_ACTE2 = (a.acte2_debut, T_ACTE2[1])
    IMPACT = a.impact
    ACCENT = a.accent
    if a.acte2_fin is not None:
        T_ACTE2 = (T_ACTE2[0], a.acte2_fin)
        T_MONTAGE = (a.acte2_fin, max(a.acte2_fin, T_MONTAGE[1]))
    if a.montage_fin is not None:
        T_MONTAGE = (T_MONTAGE[0], a.montage_fin)
    if a.logo is not None:
        T_LOGO = a.logo
    if a.finance is not None:
        T_FINANCE = a.finance
    T_TOUR = (T_MONTAGE[1], T_LOGO)
    if a.duree < T_LOGO + 4:
        print(f"durée trop courte : le logo commence à {T_LOGO} s", file=sys.stderr)
        return 2
    SR = a.taux
    p = composer(a.duree)
    info = finir(p, a.duree, Path(a.sortie))
    print(f"{a.sortie} : {info['duree']:.1f} s, {SR} Hz, stéréo 16 bits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
