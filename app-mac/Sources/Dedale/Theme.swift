import AppKit
import QuartzCore

// Jetons visuels de l'app, repris de la console SOC (`console/src/index.css`, blocs
// « Direction minimaliste » et « Console v2 » du 10 octobre). Même système des deux côtés :
// police système, presque tout en niveaux de gris, une couleur seulement quand elle porte un
// sens (rouge pour le danger, orange pour ce qui attend une décision, vert pour ce qui est
// réglé), pilules pour les boutons, 16 à 24 points pour les cartes, filets fins, ombres à
// peine visibles. La console n'a qu'un thème clair : chaque fenêtre et chaque menu de l'app
// forcent l'apparence claire, même quand macOS est en mode sombre.
//
// Toutes les teintes, rayons, tailles et courbes de l'interface viennent d'ici. Le nom de la
// variable CSS correspondante suit chaque jeton.

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255,
                  alpha: alpha)
    }
}

enum Teinte {
    // MARK: Fonds
    /// `--fond`, `--panneau` : le fond des fenêtres et des cartes.
    static let fond = NSColor(hex: 0xFFFFFF)
    /// `--puits` : bloc de faits dans une carte (`.inv-faits`), bandeau, toile des captures.
    static let puits = NSColor(hex: 0xF9F9F9)
    /// Fond des pastilles neutres (`.gravite`, `.statut-pill`, `.inv-puce-plus`).
    static let puce = NSColor(hex: 0xF4F4F4)
    /// `--survol` : fond d'un bouton secondaire survolé.
    static let survol = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.04)
    /// `--actif` : fond d'un bouton fantôme survolé ou enfoncé.
    static let actif = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.06)

    // MARK: Filets
    /// `--bord` : bord fin des cartes et des fenêtres.
    static let bord = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.08)
    /// `--bord-fort` : contour des boutons secondaires.
    static let bordFort = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.14)

    // MARK: Texte
    /// `--texte`, `--encre` : titres, texte fort, fond du bouton principal.
    static let encre = NSColor(hex: 0x0D0D0D)
    /// `--accent-survol` : bouton principal survolé.
    static let encreSurvol = NSColor(hex: 0x2F2F2F)
    /// `--texte-doux` : texte courant.
    static let texte = NSColor(hex: 0x5D5D5D)
    /// `--texte-faible` : libellés, notes, métadonnées.
    static let discret = NSColor(hex: 0x737373)
    /// `--inconnu` : point d'un module éteint ou en attente de réponse.
    static let gris = NSColor(hex: 0x8F8F8F)
    /// `--accent-clair` : piste d'un interrupteur éteint.
    static let eteint = NSColor(hex: 0xD4D4D4)

    // MARK: Couleurs porteuses de sens
    /// `--ok` : réglé, protégé, en marche.
    static let ok = NSColor(hex: 0x0F7B55)
    /// `--script`, `--orange` : attend une décision ou une action humaine.
    static let orange = NSColor(hex: 0xC2410C)
    /// `--alerte` : danger, geste risqué.
    static let rouge = NSColor(hex: 0xC4262E)
    /// `--alerte-fonce`.
    static let rougeFonce = NSColor(hex: 0xA11F26)

    /// `color-mix(in srgb, <couleur> <part>, #ffffff)` : une teinte pâle et opaque.
    static func pale(_ couleur: NSColor, _ part: CGFloat) -> NSColor {
        guard let c = couleur.usingColorSpace(.sRGB) else { return couleur }
        return NSColor(srgbRed: c.redComponent * part + (1 - part),
                       green: c.greenComponent * part + (1 - part),
                       blue: c.blueComponent * part + (1 - part), alpha: 1)
    }

    /// Fond d'une puce rouge (`.inv-puce` : rouge à 7 %).
    static let rougeFond = pale(rouge, 0.07)
    /// Fond survolé d'un bouton risqué (rouge à 4 %).
    static let rougeSurvol = pale(rouge, 0.04)
    /// Contour survolé d'un bouton risqué (rouge à 40 %).
    static let rougeBord = rouge.withAlphaComponent(0.4)
    /// Fond d'une pastille verte ou orange (`.statut-pill.s-ok`, `.s-attente` : 9 %).
    static let okFond = pale(ok, 0.09)
    static let orangeFond = pale(orange, 0.09)
}

/// Rayons des coins (`--rayon`, `--rayon-s`, `.inv-carte`, `.inv-faits`, `.pastille-logo`).
enum Rayon {
    /// `--rayon` : pop-ups et panneaux.
    static let fenetre: CGFloat = 20
    /// `.inv-carte` : carte posée dans un panneau.
    static let carte: CGFloat = 18
    /// Petite fenêtre (bulle de confirmation).
    static let bulle: CGFloat = 16
    /// `.inv-faits` : bloc gris dans une carte.
    static let bloc: CGFloat = 14
    /// `--rayon-s` : bandeau, menu.
    static let petit: CGFloat = 12
    /// `.pastille-logo`, tuile d'icône.
    static let tuile: CGFloat = 10
}

/// Tailles de texte, en points (la console est en px, à l'échelle 1 sur macOS).
enum Taille {
    /// Titre d'une pop-up (`.ag-titre` réduit à la largeur d'une pop-up).
    static let titre: CGFloat = 17
    /// Titre d'un panneau ou d'une carte (`.inv-nom`, `.panneau > .titre`).
    static let titrePanneau: CGFloat = 16
    /// Titre d'une carte de module ou d'une issue.
    static let titreCarte: CGFloat = 15
    /// Boutons (`.ag-pilule`).
    static let bouton: CGFloat = 14
    /// Texte courant d'une carte (`.inv-role`, `.inv-faits dd`).
    static let texte: CGFloat = 13.5
    /// Petits libellés (`.ag-lib`, `.inv-proprio`).
    static let libelle: CGFloat = 13
    /// Statut, pastille (`.gravite`, `.statut-pill`).
    static let pastille: CGFloat = 12.5
    /// Notes sous les boutons (`.sig-intro`).
    static let note: CGFloat = 12
    /// Puces de droits (`.inv-puce`).
    static let puce: CGFloat = 12
}

/// Ombres diffuses de la console, jamais dures.
enum Ombre {
    /// `--ombre-haute` : 0 2px 8px noir 4 %, puis 0 12px 48px noir 8 %, et un liseré noir 4 %.
    static let proche = (decalage: CGFloat(2), flou: CGFloat(8), opacite: CGFloat(0.04))
    static let haute = (decalage: CGFloat(12), flou: CGFloat(48), opacite: CGFloat(0.08))
    static let liseré = NSColor(srgbRed: 0, green: 0, blue: 0, alpha: 0.04)
}

/// `--courbe` : cubic-bezier(0.32, 0.72, 0, 1), la même pour toutes les transitions.
enum Courbe {
    static var fluide: CAMediaTimingFunction { CAMediaTimingFunction(controlPoints: 0.32, 0.72, 0, 1) }
}

/// Apparence de toutes les fenêtres et de tous les menus : le thème clair de la console.
enum Apparence {
    static let claire = NSAppearance(named: .aqua)
}
