import AppKit

// Briques communes aux fenêtres de l'app : boutons en pilule, panneau flottant, carte
// blanche, fabriques de textes et capture PNG. Les jetons (teintes, rayons, tailles,
// courbe) sont dans Theme.swift, repris de la console SOC.

// MARK: - Bouton

/// Bouton en pilule, comme ceux de la console. `.protege` (Annuler, Compris, Mettre de côté)
/// est le bouton principal, noir. `.risque` (Continuer, Garder) est en contour, texte rouge,
/// comme « Couper » en option secondaire. `.neutre` (Fermer) est en contour, texte noir.
/// `.lien` est une petite pilule en contour (Voir le mail, comme `.ag-voir`).
final class BoutonDedale: NSButton {
    enum Style { case protege, risque, neutre, lien }

    private let style: Style
    private var enfonce = false
    private var survole = false
    private var hauteur: CGFloat { style == .lien ? 30 : 38 }
    private var marge: CGFloat { style == .lien ? 14 : 20 }

    init(titre: String, style: Style, cible: AnyObject, action: Selector) {
        self.style = style
        super.init(frame: .zero)
        title = titre
        target = cible
        self.action = action
        isBordered = false
        focusRingType = .none
        wantsLayer = true
        layer?.cornerRadius = hauteur / 2
        translatesAutoresizingMaskIntoConstraints = false
        heightAnchor.constraint(equalToConstant: hauteur).isActive = true
        if style == .lien {
            setContentHuggingPriority(.required, for: .horizontal)
        }
        majApparence()
    }

    required init?(coder: NSCoder) { fatalError("non utilisé") }

    override var isEnabled: Bool { didSet { majApparence() } }

    /// Le texte et la marge de la pilule, de chaque côté.
    override var intrinsicContentSize: NSSize {
        NSSize(width: ceil(attributedTitle.size().width) + marge * 2, height: hauteur)
    }

    override func mouseDown(with event: NSEvent) {
        enfonce = true
        majApparence()
        super.mouseDown(with: event)
        enfonce = false
        majApparence()
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self, userInfo: nil))
    }

    override func mouseEntered(with event: NSEvent) { survole = true; majApparence() }
    override func mouseExited(with event: NSEvent) { survole = false; majApparence() }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }

    private func majApparence() {
        let actif = enfonce || survole
        let fond: NSColor
        let texte: NSColor
        let bord: NSColor?
        var taille = Taille.bouton
        switch style {
        case .protege:
            (fond, texte, bord) = (actif ? Teinte.encreSurvol : Teinte.encre, Teinte.fond, nil)
        case .risque:
            (fond, texte, bord) = (actif ? Teinte.rougeSurvol : Teinte.fond, Teinte.rouge,
                                   actif ? Teinte.rougeBord : Teinte.bordFort)
        case .neutre:
            (fond, texte, bord) = (actif ? Teinte.pale(Teinte.encre, 0.04) : Teinte.fond, Teinte.encre, Teinte.bordFort)
        case .lien:
            (fond, texte, bord) = (actif ? Teinte.pale(Teinte.encre, 0.04) : Teinte.fond, Teinte.encre, Teinte.bordFort)
            taille = Taille.libelle
        }
        CATransaction.begin()
        CATransaction.setAnimationDuration(0.3)
        CATransaction.setAnimationTimingFunction(Courbe.fluide)
        layer?.backgroundColor = fond.cgColor
        layer?.borderWidth = bord == nil ? 0 : 1
        layer?.borderColor = bord?.cgColor
        CATransaction.commit()
        alphaValue = isEnabled ? 1 : 0.45
        let paragraphe = NSMutableParagraphStyle()
        paragraphe.alignment = .center
        attributedTitle = NSAttributedString(string: title, attributes: [
            .font: NSFont.systemFont(ofSize: taille, weight: .medium),
            .foregroundColor: texte,
            .paragraphStyle: paragraphe,
        ])
        invalidateIntrinsicContentSize()
    }
}

/// Bouton rond sans fond, pour une icône (fermeture d'un panneau) : fond gris au survol,
/// comme `.modale-fermer` dans la console.
final class BoutonIcone: NSButton {
    private var survole = false

    init(symbole: String, cible: AnyObject, action: Selector, cote: CGFloat = 28) {
        super.init(frame: .zero)
        image = Gabarit.symbole(symbole, taille: 11, couleurs: [Teinte.texte])
        imagePosition = .imageOnly
        target = cible
        self.action = action
        isBordered = false
        focusRingType = .none
        wantsLayer = true
        layer?.cornerRadius = cote / 2
        translatesAutoresizingMaskIntoConstraints = false
        widthAnchor.constraint(equalToConstant: cote).isActive = true
        heightAnchor.constraint(equalToConstant: cote).isActive = true
        setAccessibilityLabel("Fermer")
    }

    required init?(coder: NSCoder) { fatalError("non utilisé") }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self, userInfo: nil))
    }

    override func mouseEntered(with event: NSEvent) { survole = true; layer?.backgroundColor = Teinte.actif.cgColor }
    override func mouseExited(with event: NSEvent) { survole = false; layer?.backgroundColor = nil }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
}

/// Fond d'une pastille : ses coins suivent sa hauteur, elle reste une pilule quelle que soit
/// la taille du texte.
final class FondPilule: NSView {
    override func layout() {
        super.layout()
        layer?.cornerRadius = bounds.height / 2
    }
}

// MARK: - Écran

/// Zone où les fenêtres de l'app ont le droit de se poser : la partie visible de l'écran
/// principal (sans barre de menus ni encoche, sans Dock), moins une marge. Aucune fenêtre
/// n'en sort. `DEDALE_ECRAN=1440x900` simule un écran plus petit (taille en points, barre de
/// menus comprise), calé sur le haut de l'écran réel, pour vérifier qu'aucune fenêtre ne dépasse.
enum Ecran {
    static let marge: CGFloat = 16

    /// La partie visible de l'écran, réelle ou simulée.
    static var visible: NSRect {
        let reelle = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 875)
        let brut = (ProcessInfo.processInfo.environment["DEDALE_ECRAN"] ?? "").lowercased()
        let morceaux = brut.split(separator: "x").compactMap { Double($0) }
        guard morceaux.count == 2, morceaux[0] >= 400, morceaux[1] >= 300 else { return reelle }
        let largeur = min(CGFloat(morceaux[0]), reelle.width)
        let hauteur = min(CGFloat(morceaux[1]) - 25, reelle.height)
        return NSRect(x: reelle.midX - largeur / 2, y: reelle.maxY - hauteur, width: largeur, height: hauteur)
    }

    /// La partie visible moins la marge : là où une fenêtre se pose.
    static var zone: NSRect { visible.insetBy(dx: marge, dy: marge) }

    /// Ramène `cadre` dans la zone. Plus haut que la zone, il garde son haut visible.
    static func borner(_ cadre: NSRect) -> NSRect {
        let z = zone
        var r = cadre
        if r.maxX > z.maxX { r.origin.x = z.maxX - r.width }
        if r.minX < z.minX { r.origin.x = z.minX }
        if r.maxY > z.maxY { r.origin.y = z.maxY - r.height }
        if r.minY < z.minY { r.origin.y = min(z.minY, z.maxY - r.height) }
        return r
    }
}

/// Vue retournée : son origine est en haut, le contenu d'un défilement commence en haut.
final class VueRetournee: NSView {
    override var isFlipped: Bool { true }
}

// MARK: - Logo

/// Le logo de Dédale (`design/logo/`, copié dans `Ressources/`) : deux crochets qui
/// s'emboîtent autour d'un disque. Les PNG sont lus dans le paquet de l'app, sinon dans le
/// dossier `Ressources/` d'app-mac quand le binaire tourne depuis `.build/` (captures, essais).
enum Logo {
    /// Logo noir de l'en-tête des fenêtres, 28 points.
    static let entete: NSImage? = image("LogoEntete", taille: NSSize(width: 28, height: 28))

    /// Icône de la barre de menus, 18 points, en gabarit : macOS la teinte selon la barre.
    static let barreDeMenus: NSImage? = {
        let i = image("MenuBarIcon", taille: NSSize(width: 18, height: 18))
        i?.isTemplate = true
        i?.accessibilityDescription = "Dédale"
        return i
    }()

    /// Image de `taille` points faite de `<nom>.png`, `@2x` et `@3x`, pour rester nette sur
    /// tous les écrans.
    static func image(_ nom: String, taille: NSSize) -> NSImage? {
        let image = NSImage(size: taille)
        for suffixe in ["", "@2x", "@3x"] {
            guard let url = fichier(nom + suffixe), let donnees = try? Data(contentsOf: url),
                  let rep = NSBitmapImageRep(data: donnees) else { continue }
            rep.size = taille
            image.addRepresentation(rep)
        }
        return image.representations.isEmpty ? nil : image
    }

    private static func fichier(_ nom: String) -> URL? {
        if let url = Bundle.main.url(forResource: nom, withExtension: "png") { return url }
        // Binaire lancé depuis .build/ : remonter jusqu'à app-mac/Ressources.
        var dossier = URL(fileURLWithPath: CommandLine.arguments[0]).resolvingSymlinksInPath().deletingLastPathComponent()
        for _ in 0..<6 {
            let candidat = dossier.appendingPathComponent("Ressources/\(nom).png")
            if FileManager.default.fileExists(atPath: candidat.path) { return candidat }
            dossier.deleteLastPathComponent()
        }
        return nil
    }
}

// MARK: - Panneau

/// Fenêtre flottante sans bord, au-dessus de tout, sur tous les bureaux.
final class PanneauAlerte: NSPanel {
    var surEchap: (() -> Void)?

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func cancelOperation(_ sender: Any?) { surEchap?() }

    /// Passe le panneau devant et lui donne le clavier. En capture (`DEDALE_CAPTURE`), le
    /// panneau passe devant sans prendre le clavier : une capture lancée pendant que quelqu'un
    /// tape ailleurs ne lui vole pas ses frappes, et les clics automatiques n'en ont pas besoin.
    func passerDevant() {
        if Gabarit.dossierCapture != nil { orderFrontRegardless() } else { makeKeyAndOrderFront(nil) }
    }

    /// Panneau prêt à l'emploi : carte blanche aux coins de 20 points et au bord fin, comme
    /// une carte de la console, sous `racine`. Toujours en apparence claire.
    static func carte(largeur: CGFloat, racine: NSView, rayon: CGFloat = Rayon.fenetre) -> PanneauAlerte {
        let p = PanneauAlerte(contentRect: NSRect(x: 0, y: 0, width: largeur, height: 200),
                              styleMask: [.borderless, .nonactivatingPanel],
                              backing: .buffered, defer: false)
        p.isFloatingPanel = true
        p.level = .statusBar
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = true
        p.hidesOnDeactivate = false
        p.isReleasedWhenClosed = false
        p.isMovableByWindowBackground = true
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        p.appearance = Apparence.claire

        racine.wantsLayer = true
        p.contentView = racine
        let carte = NSView()
        carte.wantsLayer = true
        carte.layer?.backgroundColor = Teinte.fond.cgColor
        carte.layer?.cornerRadius = rayon
        carte.layer?.borderWidth = 1
        carte.layer?.borderColor = Teinte.bord.cgColor
        carte.translatesAutoresizingMaskIntoConstraints = false
        racine.addSubview(carte)
        NSLayoutConstraint.activate([
            carte.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            carte.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
            carte.topAnchor.constraint(equalTo: racine.topAnchor),
            carte.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
        ])
        racine.widthAnchor.constraint(equalToConstant: largeur).isActive = true
        return p
    }
}

// MARK: - Fabriques

enum Gabarit {
    static let rayon: CGFloat = Rayon.fenetre

    static func etiquette(_ texte: String, taille: CGFloat, graisse: NSFont.Weight = .regular,
                          couleur: NSColor = Teinte.texte) -> NSTextField {
        let t = NSTextField(labelWithString: texte)
        t.font = .systemFont(ofSize: taille, weight: graisse)
        t.textColor = couleur
        t.lineBreakMode = .byTruncatingTail
        return t
    }

    static func paragraphe(_ texte: String, taille: CGFloat, graisse: NSFont.Weight = .regular,
                           couleur: NSColor = Teinte.texte, largeur: CGFloat) -> NSTextField {
        let t = NSTextField(wrappingLabelWithString: texte)
        t.font = .systemFont(ofSize: taille, weight: graisse)
        t.textColor = couleur
        t.preferredMaxLayoutWidth = largeur
        t.isSelectable = false
        return t
    }

    /// « Libellé : texte », le libellé en gras.
    static func ligneLibellee(_ libelle: String, _ texte: String, largeur: CGFloat) -> NSTextField {
        let t = NSTextField(wrappingLabelWithString: "")
        let corps = NSMutableAttributedString(string: libelle + " : ", attributes: [
            .font: NSFont.systemFont(ofSize: Taille.texte, weight: .semibold),
            .foregroundColor: Teinte.encre,
        ])
        corps.append(NSAttributedString(string: texte, attributes: [
            .font: NSFont.systemFont(ofSize: Taille.texte),
            .foregroundColor: Teinte.texte,
        ]))
        t.attributedStringValue = corps
        t.preferredMaxLayoutWidth = largeur
        t.isSelectable = false
        return t
    }

    /// Pastille neutre en pilule, comme `.gravite` dans la console : gris très pâle, texte doux.
    static func puce(_ texte: String) -> NSView {
        let fond = FondPilule()
        fond.wantsLayer = true
        fond.layer?.backgroundColor = Teinte.puce.cgColor
        let t = etiquette(texte, taille: Taille.pastille, graisse: .medium, couleur: Teinte.texte)
        t.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(t)
        NSLayoutConstraint.activate([
            t.leadingAnchor.constraint(equalTo: fond.leadingAnchor, constant: 11),
            t.trailingAnchor.constraint(equalTo: fond.trailingAnchor, constant: -11),
            t.topAnchor.constraint(equalTo: fond.topAnchor, constant: 3),
            t.bottomAnchor.constraint(equalTo: fond.bottomAnchor, constant: -3),
        ])
        fond.setContentHuggingPriority(.required, for: .horizontal)
        fond.setContentCompressionResistancePriority(.required, for: .horizontal)
        return fond
    }

    /// Le logo noir de Dédale, 28 points. Sans ses PNG, la marque de la console
    /// (`.pastille-logo` : tuile noire, « D » blanc).
    static func badgeBouclier() -> NSView {
        if let logo = Logo.entete {
            let vue = NSImageView(image: logo)
            vue.imageScaling = .scaleProportionallyUpOrDown
            vue.translatesAutoresizingMaskIntoConstraints = false
            vue.widthAnchor.constraint(equalToConstant: 28).isActive = true
            vue.heightAnchor.constraint(equalToConstant: 28).isActive = true
            vue.setAccessibilityLabel("Dédale")
            return vue
        }
        let fond = NSView()
        fond.wantsLayer = true
        fond.layer?.backgroundColor = Teinte.encre.cgColor
        fond.layer?.cornerRadius = Rayon.tuile - 1
        fond.translatesAutoresizingMaskIntoConstraints = false
        fond.widthAnchor.constraint(equalToConstant: 28).isActive = true
        fond.heightAnchor.constraint(equalToConstant: 28).isActive = true
        let lettre = etiquette("D", taille: 14, graisse: .semibold, couleur: Teinte.fond)
        lettre.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(lettre)
        NSLayoutConstraint.activate([
            lettre.centerXAnchor.constraint(equalTo: fond.centerXAnchor),
            lettre.centerYAnchor.constraint(equalTo: fond.centerYAnchor),
        ])
        fond.setAccessibilityLabel("Dédale")
        return fond
    }

    /// En-tête commun : marque, titre, pastille à droite.
    static func entete(titre: String, puce texte: String) -> NSStackView {
        let ressort = NSView()
        ressort.setContentHuggingPriority(.init(1), for: .horizontal)
        let pile = NSStackView(views: [badgeBouclier(), etiquette(titre, taille: 14, graisse: .semibold, couleur: Teinte.encre),
                                       ressort, puce(texte)])
        pile.orientation = .horizontal
        pile.alignment = .centerY
        pile.spacing = 8
        pile.setCustomSpacing(10, after: pile.arrangedSubviews[0])
        return pile
    }

    static func symbole(_ nom: String, taille: CGFloat, couleurs: [NSColor]) -> NSImage? {
        let config = NSImage.SymbolConfiguration(pointSize: taille, weight: .semibold)
            .applying(NSImage.SymbolConfiguration(paletteColors: couleurs))
        return NSImage(systemSymbolName: nom, accessibilityDescription: nil)?.withSymbolConfiguration(config)
    }

    static func icone(_ nom: String, taille: CGFloat, couleurs: [NSColor], cote: CGFloat = 20) -> NSImageView {
        let v = NSImageView()
        v.image = symbole(nom, taille: taille, couleurs: couleurs)
        v.translatesAutoresizingMaskIntoConstraints = false
        v.widthAnchor.constraint(equalToConstant: cote).isActive = true
        v.heightAnchor.constraint(equalToConstant: cote).isActive = true
        return v
    }

    static func ressort() -> NSView {
        let v = NSView()
        v.setContentHuggingPriority(.init(1), for: .horizontal)
        return v
    }

    /// Dossier des captures de test (`DEDALE_CAPTURE`), ou `nil`.
    static var dossierCapture: URL? {
        guard let d = ProcessInfo.processInfo.environment["DEDALE_CAPTURE"], !d.isEmpty else { return nil }
        return URL(fileURLWithPath: d)
    }

    /// Écrit `<nom>.png` de la vue dans `DEDALE_CAPTURE`, après `delai` secondes.
    static func capturer(_ vue: NSView, nom: String, delai: Double = 0.6, rayon: CGFloat = Rayon.fenetre) {
        guard let dossier = dossierCapture else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak vue] in
            guard let vue else { return }
            let url = dossier.appendingPathComponent("\(nom).png")
            if Capture.ecrire(vue, vers: url, rayon: rayon) { journal("capture écrite : \(url.path)") }
        }
    }
}

// MARK: - Capture en PNG

enum Capture {
    /// Rend la vue (et ses calques) sur une toile gris clair, avec l'ombre diffuse de la console.
    @discardableResult
    static func ecrire(_ vue: NSView, vers url: URL, rayon: CGFloat = Gabarit.rayon) -> Bool {
        guard let couche = vue.layer else { return false }
        let taille = vue.bounds.size
        return ecrire(taille: taille, rayon: rayon, vers: url) { ctx in
            if couche.isGeometryFlipped {
                ctx.translateBy(x: 0, y: taille.height)
                ctx.scaleBy(x: 1, y: -1)
            }
            couche.render(in: ctx)
        }
    }

    /// Dessine une carte de `taille` points sur le fond de bureau ; `dessiner` reçoit un
    /// contexte dont l'origine est le coin bas gauche de la carte.
    @discardableResult
    static func ecrire(taille: NSSize, rayon: CGFloat, vers url: URL, dessiner: (CGContext) -> Void) -> Bool {
        let echelle: CGFloat = 2
        let marge: CGFloat = 56
        let largeur = Int((taille.width + marge * 2) * echelle)
        let hauteur = Int((taille.height + marge * 2) * echelle)
        guard let espace = CGColorSpace(name: CGColorSpace.sRGB),
              let ctx = CGContext(data: nil, width: largeur, height: hauteur, bitsPerComponent: 8, bytesPerRow: 0,
                                  space: espace, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            return false
        }
        ctx.scaleBy(x: echelle, y: echelle)
        let toile = CGRect(x: 0, y: 0, width: taille.width + marge * 2, height: taille.height + marge * 2)
        if let degrade = CGGradient(colorsSpace: espace,
                                    colors: [Teinte.puits.cgColor, Teinte.puce.cgColor] as CFArray,
                                    locations: [0, 1]) {
            ctx.drawLinearGradient(degrade, start: CGPoint(x: 0, y: toile.maxY), end: CGPoint(x: toile.maxX, y: 0), options: [])
        }
        let carte = CGRect(x: marge, y: marge, width: taille.width, height: taille.height)
        let chemin = CGPath(roundedRect: carte, cornerWidth: rayon, cornerHeight: rayon, transform: nil)
        // --ombre-haute : une ombre proche, une ombre large, puis le liseré.
        for o in [Ombre.proche, Ombre.haute] {
            ctx.saveGState()
            ctx.setShadow(offset: CGSize(width: 0, height: -o.decalage), blur: o.flou,
                          color: NSColor(srgbRed: 0, green: 0, blue: 0, alpha: o.opacite).cgColor)
            ctx.addPath(chemin)
            ctx.setFillColor(Teinte.fond.cgColor)
            ctx.fillPath()
            ctx.restoreGState()
        }
        ctx.saveGState()
        ctx.addPath(CGPath(roundedRect: carte.insetBy(dx: -0.5, dy: -0.5), cornerWidth: rayon + 0.5,
                           cornerHeight: rayon + 0.5, transform: nil))
        ctx.setStrokeColor(Ombre.liseré.cgColor)
        ctx.setLineWidth(1)
        ctx.strokePath()
        ctx.restoreGState()

        ctx.saveGState()
        ctx.addPath(chemin)
        ctx.clip()
        ctx.translateBy(x: marge, y: marge)
        dessiner(ctx)
        ctx.restoreGState()

        guard let image = ctx.makeImage(),
              let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            return false
        }
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try png.write(to: url)
            return true
        } catch {
            journal("capture impossible : \(error.localizedDescription)")
            return false
        }
    }

    /// Rendu du menu par l'app elle-même (pas une capture d'écran système) : les lignes du
    /// NSMenu, dans leur état du moment, dessinées comme un menu clair de macOS.
    @discardableResult
    static func ecrireMenu(_ menu: NSMenu, vers url: URL) -> Bool {
        let hLigne: CGFloat = 24
        let hSeparateur: CGFloat = 11
        let marge: CGFloat = 6
        let items = menu.items.filter { !$0.isHidden }
        // Largeur ajustée au plus long titre, comme un vrai menu.
        let plusLong = items.map { item -> CGFloat in
            let titre = item.attributedTitle?.size().width
                ?? NSAttributedString(string: item.title, attributes: [.font: NSFont.menuFont(ofSize: 13)]).size().width
            let gauche: CGFloat = 22 + (item.image != nil ? 16 : 0)
            let droite: CGFloat = item.hasSubmenu || !item.keyEquivalent.isEmpty ? 64 : 28
            return gauche + titre + droite
        }.max() ?? 240
        let largeur = min(max(240, ceil(plusLong)), 560)
        let hauteur = items.reduce(marge * 2) { $0 + ($1.isSeparatorItem ? hSeparateur : hLigne) }
        return ecrire(taille: NSSize(width: largeur, height: hauteur), rayon: Rayon.petit, vers: url) { ctx in
            let graphique = NSGraphicsContext(cgContext: ctx, flipped: true)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = graphique
            ctx.translateBy(x: 0, y: hauteur)
            ctx.scaleBy(x: 1, y: -1)
            Teinte.fond.setFill()
            NSBezierPath(rect: NSRect(x: 0, y: 0, width: largeur, height: hauteur)).fill()
            var y = marge
            for item in items {
                if item.isSeparatorItem {
                    Teinte.bord.setFill()
                    NSBezierPath(rect: NSRect(x: 14, y: y + hSeparateur / 2, width: largeur - 28, height: 1)).fill()
                    y += hSeparateur
                    continue
                }
                let actif = item.isEnabled && (item.action != nil || item.hasSubmenu)
                var x: CGFloat = 14
                if item.state == .on {
                    let coche = NSAttributedString(string: "✓", attributes: [
                        .font: NSFont.menuFont(ofSize: 13), .foregroundColor: Teinte.encre])
                    coche.draw(at: NSPoint(x: 6, y: y + 3))
                }
                if items.contains(where: { $0.state == .on }) { x = 22 }
                if let image = item.image {
                    let cote = min(image.size.height, 14)
                    image.draw(in: NSRect(x: x, y: y + (hLigne - cote) / 2, width: image.size.width * cote / max(image.size.height, 1), height: cote))
                    x += 16
                }
                let couleur = actif ? Teinte.encre : Teinte.discret
                let titre = NSMutableAttributedString(attributedString: item.attributedTitle
                    ?? NSAttributedString(string: item.title, attributes: [.font: NSFont.menuFont(ofSize: 13)]))
                if item.attributedTitle == nil {
                    titre.addAttribute(.foregroundColor, value: couleur, range: NSRange(location: 0, length: titre.length))
                }
                let taille = titre.size()
                let reserve: CGFloat = item.hasSubmenu || !item.keyEquivalent.isEmpty ? 50 : 12
                titre.draw(with: NSRect(x: x, y: y + (hLigne - taille.height) / 2, width: largeur - x - reserve, height: taille.height),
                           options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine])
                let droite: String? = item.hasSubmenu ? "›" : (item.keyEquivalent.isEmpty ? nil : "⌘" + item.keyEquivalent.uppercased())
                if let droite {
                    let d = NSAttributedString(string: droite, attributes: [
                        .font: NSFont.menuFont(ofSize: 13), .foregroundColor: Teinte.discret])
                    d.draw(at: NSPoint(x: largeur - 14 - d.size().width, y: y + (hLigne - d.size().height) / 2))
                }
                y += hLigne
            }
            NSGraphicsContext.restoreGraphicsState()
        }
    }
}
