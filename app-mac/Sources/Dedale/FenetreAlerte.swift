import AppKit

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
    static let cyan = NSColor(hex: 0x22D3EE)
    static let cyanPresse = NSColor(hex: 0x1BB8D1)
    static let cyanSurvol = NSColor(hex: 0x3ADBF2)
    static let cyanFonce = NSColor(hex: 0x0E7490)
    static let rouge = NSColor(hex: 0xB42318)
    static let rougeBord = NSColor(hex: 0xF2D0CC)
    static let rougeFond = NSColor(hex: 0xFEF3F2)
}

// MARK: - Bouton

/// Bouton plat aux coins arrondis. `.protege` (Annuler) porte l'accent cyan,
/// `.risque` (Continuer) reste blanc avec un texte rouge sobre.
final class BoutonDedale: NSButton {
    enum Style { case protege, risque }

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
        layer?.cornerRadius = 10
        translatesAutoresizingMaskIntoConstraints = false
        heightAnchor.constraint(equalToConstant: 36).isActive = true
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
        }
        layer?.backgroundColor = fond.cgColor
        alphaValue = isEnabled ? 1 : 0.5
        let paragraphe = NSMutableParagraphStyle()
        paragraphe.alignment = .center
        attributedTitle = NSAttributedString(string: title, attributes: [
            .font: NSFont.systemFont(ofSize: 13, weight: .semibold),
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
}

// MARK: - Pop-up

/// La pop-up d'un geste à risque : verre clair, message, détail, Annuler / Continuer.
final class FenetreAlerte: NSObject {
    static let largeur: CGFloat = 400
    static let rayon: CGFloat = 14

    let avertissement: Avertissement
    /// Appelé une seule fois, avec "annuler" ou "continuer".
    var surChoix: ((String) -> Void)?
    /// Appelé quand la pop-up a disparu.
    var surFermeture: (() -> Void)?

    private let panneau: PanneauAlerte
    private let racine = NSView()
    private let pile = NSStackView()
    private var boutonAnnuler: BoutonDedale!
    private var boutonContinuer: BoutonDedale!
    private let zoneBoutons = NSStackView()
    private let note: NSTextField
    private let ligneEtat = NSStackView()
    private let iconeEtat = NSImageView()
    private let texteEtat: NSTextField
    private var choisi = false
    /// Entrée et Échap n'agissent qu'une seconde après l'apparition : quelqu'un qui tape
    /// dans une autre fenêtre ne ferme pas l'alerte sans l'avoir vue.
    private var clavierActif = false

    init(_ a: Avertissement) {
        avertissement = a
        panneau = PanneauAlerte(contentRect: NSRect(x: 0, y: 0, width: Self.largeur, height: 220),
                                styleMask: [.borderless, .nonactivatingPanel],
                                backing: .buffered, defer: false)
        note = NSTextField(wrappingLabelWithString: "Si vous continuez, l'équipe sécurité est prévenue.")
        texteEtat = NSTextField(wrappingLabelWithString: "")
        super.init()
        construire()
    }

    // MARK: Construction

    private func construire() {
        panneau.isFloatingPanel = true
        panneau.level = .statusBar
        panneau.isOpaque = false
        panneau.backgroundColor = .clear
        panneau.hasShadow = true
        panneau.hidesOnDeactivate = false
        panneau.isReleasedWhenClosed = false
        panneau.isMovableByWindowBackground = true
        panneau.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panneau.appearance = NSAppearance(named: .aqua)
        panneau.surEchap = { [weak self] in
            guard let self, self.clavierActif else { return }
            self.choisir("annuler")
        }

        racine.wantsLayer = true
        panneau.contentView = racine

        // Verre clair : flou de ce qui est derrière, voile blanc, bord fin gris clair.
        let verre = NSVisualEffectView()
        verre.material = .popover
        verre.blendingMode = .behindWindow
        verre.state = .active
        verre.maskImage = Self.masqueArrondi(rayon: Self.rayon)
        let voile = NSView()
        voile.wantsLayer = true
        voile.layer?.backgroundColor = NSColor.white.withAlphaComponent(0.86).cgColor
        voile.layer?.cornerRadius = Self.rayon
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

        let interieur = Self.largeur - 48
        pile.orientation = .vertical
        pile.alignment = .leading
        pile.spacing = 10
        pile.edgeInsets = NSEdgeInsets(top: 22, left: 24, bottom: 22, right: 24)
        pile.translatesAutoresizingMaskIntoConstraints = false
        racine.addSubview(pile)
        NSLayoutConstraint.activate([
            pile.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            pile.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
            pile.topAnchor.constraint(equalTo: racine.topAnchor),
            pile.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
            racine.widthAnchor.constraint(equalToConstant: Self.largeur),
        ])

        // En-tête : badge bouclier, « Dédale », catégorie du geste.
        let badge = Self.badgeBouclier()
        let nom = Self.etiquette("Dédale", taille: 13, graisse: .semibold, couleur: Teinte.encre)
        let categorie = Self.puce(avertissement.libelleCategorie)
        let ressort = NSView()
        ressort.setContentHuggingPriority(.init(1), for: .horizontal)
        let entete = NSStackView(views: [badge, nom, ressort, categorie])
        entete.orientation = .horizontal
        entete.alignment = .centerY
        entete.spacing = 8
        entete.setCustomSpacing(10, after: badge)

        let message = Self.paragraphe(avertissement.message, taille: 17, graisse: .semibold,
                                      couleur: Teinte.encre, largeur: interieur)
        let detail = Self.paragraphe(avertissement.detail, taille: 13, graisse: .regular,
                                     couleur: Teinte.texte, largeur: interieur)
        detail.isHidden = avertissement.detail.isEmpty

        boutonContinuer = BoutonDedale(titre: "Continuer", style: .risque, cible: self, action: #selector(continuer))
        boutonAnnuler = BoutonDedale(titre: "Annuler", style: .protege, cible: self, action: #selector(annuler))
        zoneBoutons.setViews([boutonContinuer, boutonAnnuler], in: .leading)
        zoneBoutons.orientation = .horizontal
        zoneBoutons.distribution = .fillEqually
        zoneBoutons.spacing = 10

        note.font = .systemFont(ofSize: 11)
        note.textColor = Teinte.discret
        note.preferredMaxLayoutWidth = interieur

        texteEtat.font = .systemFont(ofSize: 13, weight: .medium)
        texteEtat.textColor = Teinte.encre
        texteEtat.preferredMaxLayoutWidth = interieur - 28
        iconeEtat.translatesAutoresizingMaskIntoConstraints = false
        iconeEtat.widthAnchor.constraint(equalToConstant: 20).isActive = true
        iconeEtat.heightAnchor.constraint(equalToConstant: 20).isActive = true
        ligneEtat.setViews([iconeEtat, texteEtat], in: .leading)
        ligneEtat.orientation = .horizontal
        ligneEtat.alignment = .centerY
        ligneEtat.spacing = 8
        ligneEtat.isHidden = true

        for v in [entete, message, detail, zoneBoutons, note, ligneEtat] as [NSView] {
            pile.addArrangedSubview(v)
            v.widthAnchor.constraint(equalToConstant: interieur).isActive = true
        }
        pile.setCustomSpacing(14, after: entete)
        pile.setCustomSpacing(20, after: detail)
        pile.setCustomSpacing(20, after: message)
        if !detail.isHidden { pile.setCustomSpacing(6, after: message) }
        pile.setCustomSpacing(10, after: zoneBoutons)
    }

    // MARK: Affichage

    func montrer() {
        ajusterTaille(garderLeHaut: false)
        panneau.alphaValue = 0
        panneau.makeKeyAndOrderFront(nil)
        panneau.makeFirstResponder(boutonAnnuler)
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.18
            panneau.animator().alphaValue = 1
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self, !self.choisi else { return }
            self.clavierActif = true
            self.boutonAnnuler.keyEquivalent = "\r"
        }
        journal("pop-up affichée : \(avertissement.categorie), « \(avertissement.message) »")
        crochetsDeTest(etape: "popup")

        // Démo filmée sans souris : DEDALE_CLIC_AUTO=continuer|annuler appuie sur le vrai
        // bouton (performClick) après DEDALE_CLIC_DELAI secondes.
        let env = ProcessInfo.processInfo.environment
        if let auto = env["DEDALE_CLIC_AUTO"], ["continuer", "annuler"].contains(auto) {
            let delai = Double(env["DEDALE_CLIC_DELAI"] ?? "") ?? 2
            DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in
                guard let self, !self.choisi else { return }
                journal("clic automatique (test) sur « \(auto == "continuer" ? "Continuer" : "Annuler") »")
                (auto == "continuer" ? self.boutonContinuer : self.boutonAnnuler)?.performClick(nil)
            }
        }
    }

    @objc private func annuler() { choisir("annuler") }
    @objc private func continuer() { choisir("continuer") }

    private func choisir(_ choix: String) {
        guard !choisi else { return }
        choisi = true
        boutonAnnuler.isEnabled = false
        boutonContinuer.isEnabled = false
        journal("choix du salarié : \(choix)")
        surChoix?(choix)
    }

    /// Montre l'issue du choix, puis ferme la pop-up.
    func confirmer(choix: String, remonte: Bool) {
        let symbole: String
        let couleur: NSColor
        if choix == "annuler" {
            symbole = "checkmark.circle.fill"
            couleur = Teinte.cyanFonce
            texteEtat.stringValue = "C'est annulé. Vous êtes protégé."
        } else if remonte {
            symbole = "exclamationmark.triangle.fill"
            couleur = Teinte.rouge
            texteEtat.stringValue = "Vous avez continué. L'équipe sécurité est prévenue."
        } else {
            symbole = "exclamationmark.triangle.fill"
            couleur = Teinte.rouge
            texteEtat.stringValue = "Vous avez continué. Le SOC est injoignable, rien n'a été signalé."
        }
        let config = NSImage.SymbolConfiguration(pointSize: 16, weight: .semibold)
            .applying(NSImage.SymbolConfiguration(paletteColors: [.white, couleur]))
        iconeEtat.image = NSImage(systemSymbolName: symbole, accessibilityDescription: nil)?
            .withSymbolConfiguration(config)
        zoneBoutons.isHidden = true
        note.isHidden = true
        ligneEtat.isHidden = false
        ajusterTaille(garderLeHaut: true)
        crochetsDeTest(etape: "popup-\(choix)")
        DispatchQueue.main.asyncAfter(deadline: .now() + 2.4) { [weak self] in self?.fermer() }
    }

    private func fermer() {
        NSAnimationContext.runAnimationGroup({ ctx in
            ctx.duration = 0.2
            panneau.animator().alphaValue = 0
        }, completionHandler: { [weak self] in
            guard let self else { return }
            self.panneau.orderOut(nil)
            self.surFermeture?()
        })
    }

    private func ajusterTaille(garderLeHaut: Bool) {
        racine.layoutSubtreeIfNeeded()
        let taille = NSSize(width: Self.largeur, height: ceil(racine.fittingSize.height))
        var cadre = panneau.frame
        if garderLeHaut {
            cadre.origin.y = cadre.maxY - taille.height
        } else if let ecran = NSScreen.main?.visibleFrame {
            cadre.origin.x = ecran.midX - taille.width / 2
            cadre.origin.y = ecran.minY + ecran.height * 0.62 - taille.height / 2
        }
        cadre.size = taille
        panneau.setFrame(cadre, display: true)
        panneau.invalidateShadow()
    }

    // MARK: Capture (test)

    /// DEDALE_CAPTURE=<dossier> : l'application écrit un PNG de sa propre pop-up
    /// (aucun droit d'enregistrement d'écran nécessaire, elle ne lit que sa fenêtre).
    private func crochetsDeTest(etape: String) {
        guard let dossier = ProcessInfo.processInfo.environment["DEDALE_CAPTURE"], !dossier.isEmpty else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
            guard let self else { return }
            let url = URL(fileURLWithPath: dossier).appendingPathComponent("\(etape).png")
            if Capture.ecrire(self.racine, vers: url) { journal("capture écrite : \(url.path)") }
        }
    }

    // MARK: Fabriques

    private static func etiquette(_ texte: String, taille: CGFloat, graisse: NSFont.Weight, couleur: NSColor) -> NSTextField {
        let t = NSTextField(labelWithString: texte)
        t.font = .systemFont(ofSize: taille, weight: graisse)
        t.textColor = couleur
        return t
    }

    private static func paragraphe(_ texte: String, taille: CGFloat, graisse: NSFont.Weight,
                                   couleur: NSColor, largeur: CGFloat) -> NSTextField {
        let t = NSTextField(wrappingLabelWithString: texte)
        t.font = .systemFont(ofSize: taille, weight: graisse)
        t.textColor = couleur
        t.preferredMaxLayoutWidth = largeur
        t.isSelectable = false
        return t
    }

    private static func puce(_ texte: String) -> NSView {
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

    private static func badgeBouclier() -> NSView {
        let fond = NSView()
        fond.wantsLayer = true
        fond.layer?.backgroundColor = Teinte.cyan.withAlphaComponent(0.16).cgColor
        fond.layer?.cornerRadius = 8
        fond.translatesAutoresizingMaskIntoConstraints = false
        fond.widthAnchor.constraint(equalToConstant: 28).isActive = true
        fond.heightAnchor.constraint(equalToConstant: 28).isActive = true
        let icone = NSImageView()
        let config = NSImage.SymbolConfiguration(pointSize: 13, weight: .semibold)
            .applying(NSImage.SymbolConfiguration(paletteColors: [Teinte.cyanFonce]))
        icone.image = NSImage(systemSymbolName: "shield.lefthalf.filled", accessibilityDescription: "Dédale")?
            .withSymbolConfiguration(config)
        icone.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(icone)
        NSLayoutConstraint.activate([
            icone.centerXAnchor.constraint(equalTo: fond.centerXAnchor),
            icone.centerYAnchor.constraint(equalTo: fond.centerYAnchor),
        ])
        return fond
    }

    private static func masqueArrondi(rayon: CGFloat) -> NSImage {
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
}

// MARK: - Capture d'une vue en PNG

enum Capture {
    /// Rend la vue (et ses calques) sur un fond clair façon bureau, avec une ombre douce.
    /// Le flou du verre n'apparaît pas dans ce rendu : seul le voile blanc est dessiné.
    @discardableResult
    static func ecrire(_ vue: NSView, vers url: URL) -> Bool {
        guard let couche = vue.layer else { return false }
        let echelle: CGFloat = 2
        let marge: CGFloat = 56
        let taille = vue.bounds.size
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
        let chemin = CGPath(roundedRect: carte, cornerWidth: FenetreAlerte.rayon, cornerHeight: FenetreAlerte.rayon, transform: nil)
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
        if couche.isGeometryFlipped {
            ctx.translateBy(x: 0, y: taille.height)
            ctx.scaleBy(x: 1, y: -1)
        }
        couche.render(in: ctx)
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
}
