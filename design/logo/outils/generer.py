"""Décline design/logo/dedale.svg en toutes les tailles utilisées par Dédale.

Usage (depuis la racine du dépôt) :
    python3 design/logo/outils/generer.py

Il faut rsvg-convert (brew install librsvg) et iconutil (fourni avec macOS).
Le script écrit dans design/logo/, puis copie les fichiers utilisés dans la
console, la landing, l'extension et app-mac/Ressources/.
"""
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

LOGO = Path(__file__).resolve().parent.parent
RACINE = LOGO.parent.parent
ENCRE = "#0d0d0d"

maitre = (LOGO / "dedale.svg").read_text()
FORMES = re.findall(r'<path d="([^"]+)"/>', maitre)
DISQUE = re.search(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"/>', maitre).groups()

# Pour la barre de menus : le disque, plus petit et recentré dans le creux,
# laisse un vide d'environ 2 px entre lui et les crochets à 16 px.
DISQUE_GABARIT = ("361", "377.25", "108")


def logo(couleur, x=0.0, y=0.0, taille=750.0, disque=DISQUE):
    """Le logo en groupe SVG, posé dans un carré de `taille` à (x, y)."""
    k = taille / 750
    cx, cy, r = disque
    return (
        f'<g fill="{couleur}" transform="translate({x:g} {y:g}) scale({k:.6g})">'
        + "".join(f'<path d="{d}"/>' for d in FORMES)
        + f'<circle cx="{cx}" cy="{cy}" r="{r}"/></g>'
    )


def svg(vb, contenu, titre="Dédale"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vb} {vb}" role="img" '
            f'aria-label="{titre}">\n{contenu}\n</svg>\n')


def tuile(cote, marge, rayon, part, liseré=False, disque=DISQUE):
    """Carré blanc arrondi, logo noir au centre. `part` : côté du logo / côté de la tuile."""
    t = cote - 2 * marge
    l = t * part
    bord = (f'<rect x="{marge + 0.5:g}" y="{marge + 0.5:g}" width="{t - 1:g}" height="{t - 1:g}" '
            f'rx="{rayon - 0.5:g}" fill="none" stroke="#000" stroke-opacity=".12"/>') if liseré else ""
    return svg(cote, f'<rect x="{marge:g}" y="{marge:g}" width="{t:g}" height="{t:g}" rx="{rayon:g}" fill="#fff"/>'
               + bord + logo(ENCRE, (cote - l) / 2, (cote - l) / 2, l, disque))


def icone_app(petite=False):
    """Icône d'app macOS : grille 1024, corps 824 arrondi, logo noir au centre."""
    if petite:  # 16 et 32 px : corps plus grand, sans ombre, logo plus présent, disque simplifié
        corps, rayon, l = 992, 222, 700
        o = (1024 - corps) / 2
        return svg(1024,
                   f'<rect x="{o:g}" y="{o:g}" width="{corps}" height="{corps}" rx="{rayon}" fill="#fff"/>'
                   f'<rect x="{o + 4:g}" y="{o + 4:g}" width="{corps - 8}" height="{corps - 8}" rx="{rayon - 4}" '
                   f'fill="none" stroke="#000" stroke-opacity=".14" stroke-width="8"/>'
                   + logo(ENCRE, (1024 - l) / 2, (1024 - l) / 2, l, DISQUE_GABARIT))
    l = 500
    return svg(1024, f"""<defs>
<linearGradient id="fond" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#eceef1"/></linearGradient>
<filter id="ombre" x="-20%" y="-20%" width="140%" height="140%">
<feGaussianBlur in="SourceAlpha" stdDeviation="12"/><feOffset dy="10"/>
<feComponentTransfer><feFuncA type="linear" slope="0.3"/></feComponentTransfer>
<feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>
</defs>
<rect x="100" y="100" width="824" height="824" rx="185" fill="url(#fond)" filter="url(#ombre)"/>
<rect x="101" y="101" width="822" height="822" rx="184" fill="none" stroke="#000" stroke-opacity=".07" stroke-width="2"/>
{logo(ENCRE, (1024 - l) / 2, (1024 - l) / 2, l)}""")


def png(source_svg, sortie, cote):
    sortie.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(source_svg)
    subprocess.run(["rsvg-convert", "-w", str(cote), "-h", str(cote), f.name, "-o", str(sortie)], check=True)
    Path(f.name).unlink()


def ico(pngs, sortie):
    """favicon.ico avec des entrées PNG (lues par tous les navigateurs actuels)."""
    donnees = [p.read_bytes() for p in pngs]
    tailles = [struct.unpack(">I", d[16:20])[0] for d in donnees]
    tete = struct.pack("<HHH", 0, 1, len(donnees))
    pos = 6 + 16 * len(donnees)
    entrees = b""
    for d, t in zip(donnees, tailles):
        entrees += struct.pack("<BBBBHHII", t % 256, t % 256, 0, 0, 1, 32, len(d), pos)
        pos += len(d)
    sortie.write_bytes(tete + entrees + b"".join(donnees))


def ecrire(chemin, texte):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(texte)


def main():
    # Logo seul
    ecrire(LOGO / "dedale-noir.svg", svg(750, logo("#000")))
    ecrire(LOGO / "dedale-blanc.svg", svg(750, logo("#fff")))
    # Gabarit macOS : noir pur sur transparent, 16 sur 18 de haut, disque simplifié
    ecrire(LOGO / "dedale-gabarit.svg", svg(18, logo("#000", 1, 1, 16, DISQUE_GABARIT)))
    for c in (256, 512, 1024):
        png(svg(750, logo(ENCRE)), LOGO / "png" / f"dedale-noir-{c}.png", c)
        png(svg(750, logo("#fff")), LOGO / "png" / f"dedale-blanc-{c}.png", c)

    # Favicons : tuile blanche arrondie, logo noir
    fav = LOGO / "favicons"
    # Le favicon s'affiche en 16 et 32 px : disque simplifié, comme le gabarit.
    favicon_svg = tuile(64, 0, 14, 0.76, disque=DISQUE_GABARIT)
    ecrire(fav / "favicon.svg", favicon_svg)
    png(tuile(64, 0, 14, 0.8, disque=DISQUE_GABARIT), fav / "favicon-16.png", 16)
    png(favicon_svg, fav / "favicon-32.png", 32)
    png(tuile(64, 0, 14, 0.74, liseré=True), fav / "favicon-48.png", 48)
    png(svg(180, f'<rect width="180" height="180" fill="#fff"/>' + logo(ENCRE, 36, 36, 108)),
        fav / "apple-touch-icon.png", 180)
    ico([fav / "favicon-16.png", fav / "favicon-32.png", fav / "favicon-48.png"], fav / "favicon.ico")

    # Extension Chrome : 128 avec 16 px de marge transparente, comme le demande Chrome
    ext = LOGO / "extension"
    ecrire(ext / "icone.svg", tuile(128, 16, 22, 0.74, liseré=True))
    png(tuile(64, 0, 14, 0.8, disque=DISQUE_GABARIT), ext / "icone-16.png", 16)
    png(tuile(64, 0, 14, 0.76, disque=DISQUE_GABARIT), ext / "icone-32.png", 32)
    png(tuile(64, 0, 14, 0.74, liseré=True), ext / "icone-48.png", 48)
    png(tuile(128, 16, 22, 0.74, liseré=True), ext / "icone-128.png", 128)

    # App Mac : icône d'app
    ecrire(LOGO / "dedale-app.svg", icone_app())
    jeu = LOGO / "AppIcon.iconset"
    for base in (16, 32, 128, 256, 512):
        for echelle in (1, 2):
            c = base * echelle
            nom = f"icon_{base}x{base}" + ("@2x" if echelle == 2 else "") + ".png"
            png(icone_app(petite=c <= 32), jeu / nom, c)
    subprocess.run(["iconutil", "-c", "icns", str(jeu), "-o", str(LOGO / "AppIcon.icns")], check=True)

    # App Mac : barre de menus (gabarit) et en-tête des pop-ups (logo seul, 28 pt)
    mac = LOGO / "app-mac"
    gabarit = (LOGO / "dedale-gabarit.svg").read_text()
    png(gabarit, mac / "MenuBarIcon.png", 18)
    png(gabarit, mac / "MenuBarIcon@2x.png", 36)
    entete = svg(28, logo("#000", 1, 1, 26))
    for e, suffixe in ((1, ""), (2, "@2x"), (3, "@3x")):
        png(entete, mac / f"LogoEntete{suffixe}.png", 28 * e)

    # Copies vers les endroits qui les servent
    copies = {
        fav / "favicon.svg": ["console/public/favicon.svg", "landing/favicon.svg"],
        fav / "favicon.ico": ["console/public/favicon.ico", "landing/favicon.ico"],
        fav / "apple-touch-icon.png": ["console/public/apple-touch-icon.png", "landing/apple-touch-icon.png"],
        LOGO / "dedale.svg": ["console/src/assets/dedale.svg", "landing/img/dedale.svg"],
        LOGO / "AppIcon.icns": ["app-mac/Ressources/AppIcon.icns"],
        mac / "MenuBarIcon.png": ["app-mac/Ressources/MenuBarIcon.png"],
        mac / "MenuBarIcon@2x.png": ["app-mac/Ressources/MenuBarIcon@2x.png"],
        mac / "LogoEntete.png": ["app-mac/Ressources/LogoEntete.png"],
        mac / "LogoEntete@2x.png": ["app-mac/Ressources/LogoEntete@2x.png"],
        mac / "LogoEntete@3x.png": ["app-mac/Ressources/LogoEntete@3x.png"],
    }
    for nom in ("icone.svg", "icone-16.png", "icone-32.png", "icone-48.png", "icone-128.png"):
        copies[ext / nom] = [f"extension/icones/{nom}"]
    for src, cibles in copies.items():
        for cible in cibles:
            (RACINE / cible).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, RACINE / cible)
    print("Décliné dans design/logo/ et copié dans la console, la landing, l'extension et app-mac/Ressources/.")


if __name__ == "__main__":
    main()
