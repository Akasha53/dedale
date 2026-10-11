// Rend un carton texte en PNG avec la police système de macOS (SF Pro, optique Display
// choisie par le système au-dessus de 20 pt). Aucune dépendance : le compilateur Swift
// livré avec les outils en ligne de commande d'Xcode suffit.
//
//   swift carton.swift SORTIE.png LARGEUR HAUTEUR [--fond RRGGBB] [--decalage PX] [--police NOM] \
//         "texte|taille|graisse|RRGGBB[|suivi]" ["texte|taille|graisse|RRGGBB[|suivi]" ...]
//
// graisse : regular, medium, semibold, bold. suivi : espacement des lettres en em
// (-0.02 = serré). Sans --fond, le PNG est transparent, prêt pour `overlay`.
// Plusieurs lignes se superposent au centre, avec un interligne de 0,35 fois la taille.
// --police "Helvetica Neue" : repli si la police système ne convient pas (il n'y a pas de
// semibold dans Helvetica Neue : l'écart se fait entre medium et bold).
// Un « \n » dans le texte coupe la ligne. Les mots entre astérisques passent en gras
// (logotype : "s*AI*fe").
import AppKit

func couleur(_ hex: String) -> NSColor {
    var v: UInt64 = 0
    Scanner(string: hex).scanHexInt64(&v)
    return NSColor(srgbRed: CGFloat((v >> 16) & 255) / 255, green: CGFloat((v >> 8) & 255) / 255,
                   blue: CGFloat(v & 255) / 255, alpha: 1)
}

func graisse(_ nom: String) -> NSFont.Weight {
    switch nom {
    case "medium": return .medium
    case "semibold": return .semibold
    case "bold": return .bold
    default: return .regular
    }
}

var args = Array(CommandLine.arguments.dropFirst())
guard args.count >= 4, let L = Int(args[1]), let H = Int(args[2]) else {
    FileHandle.standardError.write(Data("usage : carton.swift SORTIE.png LARGEUR HAUTEUR [--fond RRGGBB] [--decalage PX] ligne...\n".utf8))
    exit(2)
}
let sortie = args[0]
args.removeFirst(3)
var fond: NSColor? = nil
var decalage: CGFloat = 0
var famille: String? = nil
var lignes: [String] = []
var i = 0
while i < args.count {
    if args[i] == "--fond", i + 1 < args.count { fond = couleur(args[i + 1]); i += 2 }
    else if args[i] == "--decalage", i + 1 < args.count { decalage = CGFloat(Double(args[i + 1]) ?? 0); i += 2 }
    else if args[i] == "--police", i + 1 < args.count { famille = args[i + 1]; i += 2 }
    else { lignes.append(args[i]); i += 1 }
}

let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: L, pixelsHigh: H, bitsPerSample: 8,
                           samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
let ctx = NSGraphicsContext(bitmapImageRep: rep)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = ctx
if let f = fond { f.setFill(); NSRect(x: 0, y: 0, width: L, height: H).fill() }

func police(_ taille: Double, _ nom: String, lourd: Bool = false) -> NSFont {
    let w = lourd ? NSFont.Weight.heavy : graisse(nom)
    if let f = famille {
        let n: Int = lourd ? 10 : (nom == "bold" ? 9 : nom == "semibold" ? 8 : nom == "medium" ? 6 : 5)
        if let police = NSFontManager.shared.font(withFamily: f, traits: [], weight: n, size: CGFloat(taille)) { return police }
    }
    return NSFont.systemFont(ofSize: CGFloat(taille), weight: w)
}

struct Bloc { let texte: NSAttributedString; let hauteur: CGFloat; let ecart: CGFloat }
var blocs: [Bloc] = []
let largeurMax = CGFloat(L) * 0.8
for spec in lignes {
    let p = spec.components(separatedBy: "|")
    guard p.count >= 4, let taille = Double(p[1]) else { continue }
    let ps = NSMutableParagraphStyle()
    ps.alignment = .center
    ps.lineHeightMultiple = taille >= 60 ? 1.05 : 1.2
    var attrs: [NSAttributedString.Key: Any] = [
        .font: police(taille, p[2]),
        .foregroundColor: couleur(p[3]),
        .paragraphStyle: ps,
    ]
    if p.count >= 5, let suivi = Double(p[4]) { attrs[.kern] = suivi * taille }
    let brut = p[0].replacingOccurrences(of: "\\n", with: "\n")
    let t = NSMutableAttributedString()
    for (n, morceau) in brut.components(separatedBy: "*").enumerated() {
        var a = attrs
        if n % 2 == 1 { a[.font] = police(taille, "bold", lourd: true) }
        t.append(NSAttributedString(string: morceau, attributes: a))
    }
    let r = t.boundingRect(with: NSSize(width: largeurMax, height: 10000),
                           options: [.usesLineFragmentOrigin, .usesFontLeading])
    blocs.append(Bloc(texte: t, hauteur: ceil(r.height), ecart: CGFloat(taille) * 0.35))
}
let total = blocs.reduce(0) { $0 + $1.hauteur } + blocs.dropFirst().reduce(0) { $0 + $1.ecart }
var y = (CGFloat(H) + total) / 2 - decalage          // origine en bas : on descend depuis le haut
for (n, b) in blocs.enumerated() {
    if n > 0 { y -= b.ecart }
    y -= b.hauteur
    b.texte.draw(with: NSRect(x: (CGFloat(L) - largeurMax) / 2, y: y, width: largeurMax, height: b.hauteur),
                 options: [.usesLineFragmentOrigin, .usesFontLeading])
}
NSGraphicsContext.restoreGraphicsState()
let png = rep.representation(using: .png, properties: [:])!
try png.write(to: URL(fileURLWithPath: sortie))
