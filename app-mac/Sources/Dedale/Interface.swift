import AppKit

// Briques communes aux fenêtres de l'app : teintes du thème clair, boutons, panneau
// flottant, carte en verre clair, fabriques de textes et capture PNG.

// MARK: - Teintes (thème clair)

extension NSColor {
    convenience init(hex: UInt32, alpha: CGFloat = 1) {
        self.init(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255,
                  alpha: alpha)
    }
}

enum Teinte {
    static let encre = NSColor(hex: 0x0B1220)
    static let texte = NSColor(hex: 0x3F4859)
    static let discret = NSColor(hex: 0x6B7385)
    static let bord = NSColor(hex: 0xE3E6EB)
    static let puce = NSColor(hex: 0xF1F3F6)
    static let survol = NSColor(hex: 0xF6F7F9)
    static let cyan = NSColor(hex: 0x22D3EE)
    static let cyanPresse = NSColor(hex: 0x1BB8D1)
    static let cyanSurvol = NSColor(hex: 0x3ADBF2)
    static let cyanFonce = NSColor(hex: 0x0E7490)
    static let rouge = NSColor(hex: 0xB42318)
    static let rougeBord = NSColor(hex: 0xF2D0CC)
    static let rougeFond = NSColor(hex: 0xFEF3F2)
    static let gris = NSColor(hex: 0x9AA1AE)
}

// MARK: - Bouton

/// Bouton plat aux coins arrondis. `.protege` (Annuler, Compris) porte l'accent cyan,
/// `.risque` (Continuer) reste blanc avec un texte rouge sobre, `.neutre` (Fermer) est
/// blanc et gris, `.lien` n'a pas de fond (Voir le mail).
final class BoutonDedale: NSButton {
    enum Style { case protege, risque, neutre, lien }

    private let style: Style
    private var enfonce = false
    private var survole = false

    init(titre: String, style: Style, cible: AnyObject, action: Selector) {
        self.style = style
        super.init(frame: .zero)
        title = titre
        target = cible
        self.action = action
        isBordered = false
        focusRingType = .none
        wantsLayer = true
        layer?.cornerRadius = style == .lien ? 6 : 10
        translatesAutoresizingMaskIntoConstraints = false
        heightAnchor.constraint(equalToConstant: style == .lien ? 24 : 36).isActive = true
        if style == .lien {
            setContentHuggingPriority(.required, for: .horizontal)
        }
        majApparence()
    }

    required init?(coder: NSCoder) { fatalError("non utilisé") }

    override var isEnabled: Bool { didSet { majApparence() } }


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
        let fond: NSColor
        let texte: NSColor
        var taille: CGFloat = 13
        switch style {
        case .protege:
            fond = enfonce ? Teinte.cyanPresse : (survole ? Teinte.cyanSurvol : Teinte.cyan)
            texte = Teinte.encre
            layer?.borderWidth = 0
        case .risque:
            fond = (enfonce || survole) ? Teinte.rougeFond : .white
            texte = Teinte.rouge
            layer?.borderWidth = 1
            layer?.borderColor = Teinte.rougeBord.cgColor
        case .neutre:
            fond = (enfonce || survole) ? Teinte.survol : .white
            texte = Teinte.encre
            layer?.borderWidth = 1
            layer?.borderColor = Teinte.bord.cgColor
        case .lien:
            fond = .clear
            texte = (enfonce || survole) ? Teinte.encre : Teinte.cyanFonce
            taille = 12
            layer?.borderWidth = 0
        }
        layer?.backgroundColor = fond.cgColor
        alphaValue = isEnabled ? 1 : 0.5
        let paragraphe = NSMutableParagraphStyle()
        paragraphe.alignment = style == .lien ? .left : .center
        attributedTitle = NSAttributedString(string: title, attributes: [
            .font: NSFont.systemFont(ofSize: taille, weight: .semibold),
            .foregroundColor: texte,
            .paragraphStyle: paragraphe,
        ])
    }
}

// MARK: - Panneau

/// Fenêtre flottante sans bord, au-dessus de tout, sur tous les bureaux.
final class PanneauAlerte: NSPanel {
    var surEchap: (() -> Void)?

    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    override func cancelOperation(_ sender: Any?) { surEchap?() }

    /// Panneau prêt à l'emploi : verre clair (flou, voile blanc, bord fin) sous `racine`.
    static func carte(largeur: CGFloat, racine: NSView, rayon: CGFloat = Gabarit.rayon) -> PanneauAlerte {
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
        p.appearance = NSAppearance(named: .aqua)

        racine.wantsLayer = true
        p.contentView = racine
        let verre = NSVisualEffectView()
        verre.material = .popover
        verre.blendingMode = .behindWindow
        verre.state = .active
        verre.maskImage = Gabarit.masqueArrondi(rayon: rayon)
        let voile = NSView()
        voile.wantsLayer = true
        voile.layer?.backgroundColor = NSColor.white.withAlphaComponent(0.86).cgColor
        voile.layer?.cornerRadius = rayon
        voile.layer?.borderWidth = 1
        voile.layer?.borderColor = Teinte.bord.cgColor
        for v in [verre, voile] {
            v.translatesAutoresizingMaskIntoConstraints = false
            racine.addSubview(v)
            NSLayoutConstraint.activate([
                v.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
                v.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
                v.topAnchor.constraint(equalTo: racine.topAnchor),
                v.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
            ])
        }
        racine.widthAnchor.constraint(equalToConstant: largeur).isActive = true
        return p
    }
}

// MARK: - Fabriques

enum Gabarit {
    static let rayon: CGFloat = 14

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
            .font: NSFont.systemFont(ofSize: 13, weight: .semibold),
            .foregroundColor: Teinte.encre,
        ])
        corps.append(NSAttributedString(string: texte, attributes: [
            .font: NSFont.systemFont(ofSize: 13),
            .foregroundColor: Teinte.texte,
        ]))
        t.attributedStringValue = corps
        t.preferredMaxLayoutWidth = largeur
        t.isSelectable = false
        return t
    }

    static func puce(_ texte: String) -> NSView {
        let fond = NSView()
        fond.wantsLayer = true
        fond.layer?.backgroundColor = Teinte.puce.cgColor
        fond.layer?.cornerRadius = 6
        fond.layer?.borderWidth = 1
        fond.layer?.borderColor = Teinte.bord.cgColor
        let t = etiquette(texte, taille: 11, graisse: .medium, couleur: Teinte.texte)
        t.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(t)
        NSLayoutConstraint.activate([
            t.leadingAnchor.constraint(equalTo: fond.leadingAnchor, constant: 8),
            t.trailingAnchor.constraint(equalTo: fond.trailingAnchor, constant: -8),
            t.topAnchor.constraint(equalTo: fond.topAnchor, constant: 3),
            t.bottomAnchor.constraint(equalTo: fond.bottomAnchor, constant: -3),
        ])
        fond.setContentHuggingPriority(.required, for: .horizontal)
        fond.setContentCompressionResistancePriority(.required, for: .horizontal)
        return fond
    }

    static func badgeBouclier() -> NSView {
        let fond = NSView()
        fond.wantsLayer = true
        fond.layer?.backgroundColor = Teinte.cyan.withAlphaComponent(0.16).cgColor
        fond.layer?.cornerRadius = 8
        fond.translatesAutoresizingMaskIntoConstraints = false
        fond.widthAnchor.constraint(equalToConstant: 28).isActive = true
        fond.heightAnchor.constraint(equalToConstant: 28).isActive = true
        let icone = NSImageView()
        icone.image = symbole("shield.lefthalf.filled", taille: 13, couleurs: [Teinte.cyanFonce])
        icone.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(icone)
        NSLayoutConstraint.activate([
            icone.centerXAnchor.constraint(equalTo: fond.centerXAnchor),
            icone.centerYAnchor.constraint(equalTo: fond.centerYAnchor),
        ])
        return fond
    }

    /// En-tête commun : badge bouclier, titre, puce à droite.
    static func entete(titre: String, puce texte: String) -> NSStackView {
        let ressort = NSView()
        ressort.setContentHuggingPriority(.init(1), for: .horizontal)
        let pile = NSStackView(views: [badgeBouclier(), etiquette(titre, taille: 13, graisse: .semibold, couleur: Teinte.encre),
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

    static func masqueArrondi(rayon: CGFloat) -> NSImage {
        let cote = rayon * 2 + 1
        let image = NSImage(size: NSSize(width: cote, height: cote), flipped: false) { r in
            NSColor.black.setFill()
            NSBezierPath(roundedRect: r, xRadius: rayon, yRadius: rayon).fill()
            return true
        }
        image.capInsets = NSEdgeInsets(top: rayon, left: rayon, bottom: rayon, right: rayon)
        image.resizingMode = .stretch
        return image
    }

    /// Dossier des captures de test (`DEDALE_CAPTURE`), ou `nil`.
    static var dossierCapture: URL? {
        guard let d = ProcessInfo.processInfo.environment["DEDALE_CAPTURE"], !d.isEmpty else { return nil }
        return URL(fileURLWithPath: d)
    }

    /// Écrit `<nom>.png` de la vue dans `DEDALE_CAPTURE`, après `delai` secondes.
    static func capturer(_ vue: NSView, nom: String, delai: Double = 0.6) {
        guard let dossier = dossierCapture else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak vue] in
            guard let vue else { return }
            let url = dossier.appendingPathComponent("\(nom).png")
            if Capture.ecrire(vue, vers: url) { journal("capture écrite : \(url.path)") }
        }
    }
}

// MARK: - Capture en PNG

enum Capture {
    /// Rend la vue (et ses calques) sur un fond clair façon bureau, avec une ombre douce.
    /// Le flou du verre n'apparaît pas dans ce rendu : seul le voile blanc est dessiné.
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
                                    colors: [NSColor(hex: 0xF6F7F9).cgColor, NSColor(hex: 0xE6EAF0).cgColor] as CFArray,
                                    locations: [0, 1]) {
            ctx.drawLinearGradient(degrade, start: CGPoint(x: 0, y: toile.maxY), end: CGPoint(x: toile.maxX, y: 0), options: [])
        }
        let carte = CGRect(x: marge, y: marge, width: taille.width, height: taille.height)
        let chemin = CGPath(roundedRect: carte, cornerWidth: rayon, cornerHeight: rayon, transform: nil)
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -12), blur: 36, color: NSColor(white: 0.05, alpha: 0.16).cgColor)
        ctx.addPath(chemin)
        ctx.setFillColor(NSColor(hex: 0xFBFCFD).cgColor)
        ctx.fillPath()
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
        return ecrire(taille: NSSize(width: largeur, height: hauteur), rayon: 10, vers: url) { ctx in
            let graphique = NSGraphicsContext(cgContext: ctx, flipped: true)
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = graphique
            ctx.translateBy(x: 0, y: hauteur)
            ctx.scaleBy(x: 1, y: -1)
            NSColor(white: 1, alpha: 0.96).setFill()
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
