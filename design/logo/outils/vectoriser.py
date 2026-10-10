"""Vectorise design/logo/logo-source.png en design/logo/dedale.svg.

Le logo tient en trois formes : deux polygones aux coins arrondis et un disque.
On ne passe pas par un traceur automatique : on mesure la source, puis on
redessine des droites franches et des congés circulaires.

1. Contours sous-pixel de la source (marching squares, seuil 128).
2. Chaque côté droit est ajusté par moindres carrés ; un côté quasi vertical
   ou horizontal est redressé.
3. Les sommets sont les intersections des côtés voisins ; le rayon de chaque
   congé est ajusté pour coller aux points du contour.
4. Le disque est ajusté par moindres carrés (méthode algébrique).

Usage (depuis la racine du dépôt) :
    uv run --with numpy --with scipy --with scikit-image \
        python design/logo/outils/vectoriser.py

Écrit design/logo/dedale.svg et affiche l'écart à la source.
"""
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from skimage import io, measure

ICI = Path(__file__).resolve().parent.parent
SOURCE = ICI / "logo-source.png"
SORTIE = ICI / "dedale.svg"
ENCRE = "#0d0d0d"
COTE = 750  # côté du viewBox, à peu près la taille du logo dans la source

# Côtés approchés (deux points par côté), dans l'ordre du tracé, en pixels de
# la source. Ils ne servent qu'à trier les points du contour : les valeurs
# finales viennent de l'ajustement.
COTES_A = [((500, 252), (760, 252)), ((770, 262), (770, 292)), ((755, 308), (430, 520)),
           ((421, 530), (421, 632)), ((410, 648), (310, 729)), ((252, 695), (252, 460)),
           ((275, 407), (470, 265))]
COTES_B = [((1002, 575), (1002, 775)), ((985, 825), (750, 993)), ((735, 998), (580, 998)),
           ((562, 985), (562, 905)), ((575, 879), (790, 754)), ((804, 735), (804, 660)),
           ((812, 643), (940, 538))]


def contours():
    img = io.imread(SOURCE)
    if img.ndim == 3:
        img = img[..., :3].mean(-1)
    # find_contours place le centre du pixel sur l'entier : +0,5 pour le repère SVG.
    cs = [c[:, ::-1] + 0.5 for c in measure.find_contours(img.astype(float), 128) if len(c) > 300]
    boite = lambda c: (c[:, 0].min(), c[:, 1].min(), c[:, 0].max(), c[:, 1].max())
    a = next(c for c in cs if boite(c)[1] < 300)
    b = next(c for c in cs if boite(c)[3] > 950)
    d = next(c for c in cs if 450 < boite(c)[0] < 520 and boite(c)[1] > 450)
    return a, b, d


def ajuster_cote(P, a, b, tol=6, marge=0.12):
    a, b = np.asarray(a, float), np.asarray(b, float)
    u = (b - a) / np.linalg.norm(b - a)
    n = np.array([-u[1], u[0]])
    t, s = (P - a) @ u, (P - a) @ n
    L = np.linalg.norm(b - a)
    Q = P[(np.abs(s) < tol) & (t > marge * L) & (t < (1 - marge) * L)]
    c = Q.mean(0)
    d = np.linalg.svd(Q - c)[2][0]
    if d @ u < 0:
        d = -d
    # Redresser un côté presque horizontal ou vertical (moins de 0,5°).
    if abs(d[0]) < 0.009:
        d = np.array([0.0, np.sign(d[1])])
    elif abs(d[1]) < 0.009:
        d = np.array([np.sign(d[0]), 0.0])
    return c, d


def intersection(l1, l2):
    (p1, d1), (p2, d2) = l1, l2
    t = np.linalg.solve(np.array([d1, -d2]).T, p2 - p1)
    return p1 + t[0] * d1


def coins(lignes, rayons):
    res = []
    for i in range(len(lignes)):
        (_, din), (_, dout) = lignes[i - 1], lignes[i]
        V = intersection(lignes[i - 1], lignes[i])
        virage = np.arccos(np.clip(din @ dout, -1, 1))
        convexe = din[0] * dout[1] - din[1] * dout[0] > 0
        t = rayons[i] * np.tan(virage / 2)
        res.append(dict(V=V, Tin=V - din * t, Tout=V + dout * t, r=rayons[i], convexe=convexe, din=din))
    return res


def echantillons(lignes, rayons, pas=0.2):
    cs, pts = coins(lignes, rayons), []
    for i, c in enumerate(cs):
        if c["r"] > 0:
            nrm = np.array([-c["din"][1], c["din"][0]]) * (1 if c["convexe"] else -1)
            C = c["Tin"] + nrm * c["r"]
            a0 = np.arctan2(*(c["Tin"] - C)[::-1])
            da = np.arctan2(*(c["Tout"] - C)[::-1]) - a0
            da = (da % (2 * np.pi)) if c["convexe"] else -((-da) % (2 * np.pi))
            k = max(2, int(abs(da) * c["r"] / pas))
            aa = a0 + da * np.linspace(0, 1, k)
            pts.append(np.c_[C[0] + c["r"] * np.cos(aa), C[1] + c["r"] * np.sin(aa)])
        suivant = cs[(i + 1) % len(cs)]["Tin"]
        k = max(2, int(np.linalg.norm(suivant - c["Tout"]) / pas))
        pts.append(c["Tout"] + np.outer(np.linspace(0, 1, k), suivant - c["Tout"]))
    return np.vstack(pts)


def rayons_initiaux(P, lignes):
    """Rayon de départ : longueur droite mesurée sur la source, de part et d'autre du sommet."""
    etendues = []
    for p, d in lignes:
        n = np.array([-d[1], d[0]])
        t = np.sort(((P - p) @ d)[np.abs((P - p) @ n) < 0.6])
        blocs = np.split(t, np.where(np.diff(t) > 4)[0] + 1)
        bloc = max(blocs, key=len)
        etendues.append((bloc.min(), bloc.max()))
    r0 = []
    for i, c in enumerate(coins(lignes, [0] * len(lignes))):
        (pp, dp), (pn, dn) = lignes[i - 1], lignes[i]
        tin = (c["V"] - pp) @ dp - etendues[i - 1][1]
        tout = etendues[i][0] - (c["V"] - pn) @ dn
        virage = np.arccos(np.clip(dp @ dn, -1, 1))
        r0.append(max(0.5, (tin + tout) / 2 / np.tan(virage / 2)))
    return np.array(r0)


def chemin(lignes, rayons, decalage):
    f = lambda v: f"{v[0] - decalage[0]:.2f} {v[1] - decalage[1]:.2f}".replace(".00", "")
    cs = coins(lignes, rayons)
    d = f"M{f(cs[0]['Tout'])}"
    for i in range(1, len(cs) + 1):
        c = cs[i % len(cs)]
        d += f"L{f(c['Tin'])}A{c['r']:.1f} {c['r']:.1f} 0 0 {1 if c['convexe'] else 0} {f(c['Tout'])}"
    return d + "Z"


def main():
    A, B, D = contours()
    formes = []
    for P, cotes in ((A, COTES_A), (B, COTES_B)):
        lignes = [ajuster_cote(P, a, b) for a, b in cotes]
        r0 = rayons_initiaux(P, lignes)
        f = lambda r: cKDTree(echantillons(lignes, np.abs(r))).query(P)[0]
        r = np.round(np.abs(least_squares(f, r0, diff_step=1e-3, x_scale=5).x), 1)
        ecart = f(r)
        print(f"forme : écart max {ecart.max():.2f} px, moyen {ecart.mean():.2f} px (source 1254 px)")
        formes.append((lignes, r))
    x, y = D[:, 0], D[:, 1]
    sol = np.linalg.lstsq(np.c_[x, y, np.ones_like(x)], x**2 + y**2, rcond=None)[0]
    cx, cy = sol[0] / 2, sol[1] / 2
    r = np.sqrt(sol[2] + cx**2 + cy**2)
    print(f"disque : écart max {np.abs(np.hypot(x - cx, y - cy) - r).max():.2f} px")
    # Centrer le logo dans un carré de COTE unités.
    tout = np.vstack([A, B])
    centre = (tout.min(0) + tout.max(0)) / 2
    dec = centre - COTE / 2
    chemins = [chemin(l, r_, dec) for l, r_ in formes]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {COTE} {COTE}" role="img" aria-label="Dédale">\n'
        f'  <g fill="{ENCRE}">\n'
        f'    <path d="{chemins[0]}"/>\n'
        f'    <path d="{chemins[1]}"/>\n'
        f'    <circle cx="{cx - dec[0]:.2f}" cy="{cy - dec[1]:.2f}" r="{r:.2f}"/>\n'
        f"  </g>\n</svg>\n"
    )
    SORTIE.write_text(svg)
    print(f"écrit {SORTIE} (décalage source {dec[0]:.2f}, {dec[1]:.2f})")


if __name__ == "__main__":
    main()
