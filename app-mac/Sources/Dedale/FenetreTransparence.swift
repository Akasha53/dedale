import AppKit

// MARK: - Briques des panneaux du poste

enum Coque {
    /// Double coque : un plateau gris clair au bord fin, et dedans une carte blanche aux coins
    /// concentriques. `contenu` remplit la carte avec `marge` points autour.
    static func creer(_ contenu: NSView, marge: NSEdgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16),
                      rayon: CGFloat = 16) -> NSView {
        let coque = NSView()
        coque.wantsLayer = true
        coque.layer?.backgroundColor = Teinte.puce.cgColor
        coque.layer?.cornerRadius = rayon
        coque.layer?.borderWidth = 1
        coque.layer?.borderColor = Teinte.bord.withAlphaComponent(0.7).cgColor
        let coeur = NSView()
        coeur.wantsLayer = true
        coeur.layer?.backgroundColor = NSColor.white.cgColor
        coeur.layer?.cornerRadius = rayon - 4
        coeur.layer?.shadowColor = NSColor(white: 0.05, alpha: 1).cgColor
        coeur.layer?.shadowOpacity = 0.05
        coeur.layer?.shadowRadius = 8
        coeur.layer?.shadowOffset = CGSize(width: 0, height: -1)
        for (parent, enfant, m) in [(coque, coeur, NSEdgeInsets(top: 4, left: 4, bottom: 4, right: 4)), (coeur, contenu, marge)] {
            enfant.translatesAutoresizingMaskIntoConstraints = false
            parent.addSubview(enfant)
            NSLayoutConstraint.activate([
                enfant.leadingAnchor.constraint(equalTo: parent.leadingAnchor, constant: m.left),
                enfant.trailingAnchor.constraint(equalTo: parent.trailingAnchor, constant: -m.right),
                enfant.topAnchor.constraint(equalTo: parent.topAnchor, constant: m.top),
                enfant.bottomAnchor.constraint(equalTo: parent.bottomAnchor, constant: -m.bottom),
            ])
        }
        return coque
    }

    /// Pilule de texte : neutre (gris), risque (rouge pâle) ou accent (cyan pâle).
    enum Ton { case neutre, risque, accent }

    static func pilule(_ texte: String, ton: Ton = .neutre, symbole: String? = nil) -> NSView {
        let fond = NSView()
        fond.wantsLayer = true
        let (bg, bord, encre): (NSColor, NSColor, NSColor)
        switch ton {
        case .neutre: (bg, bord, encre) = (Teinte.puce, Teinte.bord, Teinte.texte)
        case .risque: (bg, bord, encre) = (Teinte.rougeFond, Teinte.rougeBord, Teinte.rouge)
        case .accent: (bg, bord, encre) = (Teinte.cyan.withAlphaComponent(0.12), Teinte.cyan.withAlphaComponent(0.35), Teinte.cyanFonce)
        }
        fond.layer?.backgroundColor = bg.cgColor
        fond.layer?.cornerRadius = 10
        fond.layer?.borderWidth = 1
        fond.layer?.borderColor = bord.cgColor
        var vues: [NSView] = []
        if let symbole { vues.append(Gabarit.icone(symbole, taille: 9, couleurs: [encre], cote: 11)) }
        vues.append(Gabarit.etiquette(texte, taille: 11, graisse: .medium, couleur: encre))
        let pile = NSStackView(views: vues)
        pile.orientation = .horizontal
        pile.spacing = 4
        pile.edgeInsets = NSEdgeInsets(top: 3, left: 9, bottom: 3, right: 9)
        pile.translatesAutoresizingMaskIntoConstraints = false
        fond.addSubview(pile)
        NSLayoutConstraint.activate([
            pile.leadingAnchor.constraint(equalTo: fond.leadingAnchor),
            pile.trailingAnchor.constraint(equalTo: fond.trailingAnchor),
            pile.topAnchor.constraint(equalTo: fond.topAnchor),
            pile.bottomAnchor.constraint(equalTo: fond.bottomAnchor),
        ])
        fond.setContentHuggingPriority(.required, for: .horizontal)
        fond.setContentCompressionResistancePriority(.required, for: .horizontal)
        return fond
    }

    /// Rangée de pilules qui passe à la ligne au-delà de `largeur`.
    static func rangees(_ pilules: [NSView], largeur: CGFloat, espace: CGFloat = 6) -> NSStackView {
        let colonne = NSStackView()
        colonne.orientation = .vertical
        colonne.alignment = .leading
        colonne.spacing = espace
        var ligne = NSStackView()
        var occupe: CGFloat = 0
        for p in pilules {
            let w = p.fittingSize.width
            if occupe > 0, occupe + espace + w > largeur {
                colonne.addArrangedSubview(ligne)
                ligne = NSStackView()
                occupe = 0
            }
            ligne.orientation = .horizontal
            ligne.spacing = espace
            ligne.addArrangedSubview(p)
            occupe += (occupe > 0 ? espace : 0) + w
        }
        if !ligne.arrangedSubviews.isEmpty { colonne.addArrangedSubview(ligne) }
        return colonne
    }

    /// Petite étiquette en capitales espacées, au-dessus d'un texte.
    static func surtitre(_ texte: String) -> NSTextField {
        let t = NSTextField(labelWithString: "")
        t.attributedStringValue = NSAttributedString(string: texte.uppercased(), attributes: [
            .font: NSFont.systemFont(ofSize: 9.5, weight: .semibold),
            .foregroundColor: Teinte.discret,
            .kern: 0.9,
        ])
        return t
    }

    /// Bouton de fermeture discret, en haut à droite d'un panneau.
    static func boutonFermer(cible: AnyObject, action: Selector) -> NSButton {
        let b = NSButton(image: Gabarit.symbole("xmark", taille: 10, couleurs: [Teinte.discret]) ?? NSImage(),
                         target: cible, action: action)
        b.isBordered = false
        b.wantsLayer = true
        b.layer?.cornerRadius = 11
        b.layer?.backgroundColor = Teinte.puce.cgColor
        b.translatesAutoresizingMaskIntoConstraints = false
        b.widthAnchor.constraint(equalToConstant: 22).isActive = true
        b.heightAnchor.constraint(equalToConstant: 22).isActive = true
        return b
    }
}

/// Fenêtre d'un panneau du poste : carte en verre clair, au centre de l'écran, fermée par
/// Échap ou par son bouton. `racine` reçoit le contenu.
class FenetrePanneau: NSObject {
    let racine = NSView()
    let panneau: PanneauAlerte
    let largeur: CGFloat
    var surFermeture: (() -> Void)?

    init(largeur: CGFloat) {
        self.largeur = largeur
        panneau = PanneauAlerte.carte(largeur: largeur, racine: racine, rayon: 18)
        super.init()
        panneau.surEchap = { [weak self] in self?.fermer() }
    }

    func poser(_ pile: NSStackView) {
        pile.translatesAutoresizingMaskIntoConstraints = false
        racine.subviews.filter { $0 is NSStackView }.forEach { $0.removeFromSuperview() }
        racine.addSubview(pile)
        NSLayoutConstraint.activate([
            pile.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            pile.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
            pile.topAnchor.constraint(equalTo: racine.topAnchor),
            pile.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
        ])
    }

    func montrer(capture: String) {
        ajuster(centrer: !panneau.isVisible)
        if !panneau.isVisible {
            panneau.alphaValue = 0
            panneau.makeKeyAndOrderFront(nil)
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.22
                ctx.timingFunction = CAMediaTimingFunction(controlPoints: 0.32, 0.72, 0, 1)
                panneau.animator().alphaValue = 1
            }
        }
        Gabarit.capturer(racine, nom: capture, delai: 0.8)
    }

    func ajuster(centrer: Bool) {
        racine.layoutSubtreeIfNeeded()
        let taille = NSSize(width: largeur, height: ceil(racine.fittingSize.height))
        var cadre = panneau.frame
        if centrer, let ecran = NSScreen.main?.visibleFrame {
            cadre.origin.x = ecran.midX - taille.width / 2
            cadre.origin.y = ecran.minY + ecran.height * 0.55 - taille.height / 2
        } else {
            cadre.origin.y = cadre.maxY - taille.height
        }
        cadre.size = taille
        panneau.setFrame(cadre, display: true)
        panneau.invalidateShadow()
    }

    @objc func fermer() {
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.18
            panneau.animator().alphaValue = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [self] in
            panneau.orderOut(nil)
            surFermeture?()
        }
    }

    /// En-tête : badge bouclier, titre, sous-titre, bouton de fermeture.
    func entete(titre: String, sousTitre: String) -> NSView {
        // Largeur utile moins le badge (28), le bouton (22) et trois espaces de 12.
        let largeurTexte = largeur - 56 - 28 - 22 - 36 - 8
        let sous = Gabarit.paragraphe(sousTitre, taille: 12, couleur: Teinte.discret, largeur: largeurTexte)
        sous.widthAnchor.constraint(equalToConstant: largeurTexte).isActive = true
        let textes = NSStackView(views: [
            Gabarit.etiquette(titre, taille: 15, graisse: .semibold, couleur: Teinte.encre), sous,
        ])
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 3
        let ligne = NSStackView(views: [Gabarit.badgeBouclier(), textes, Gabarit.ressort(),
                                        Coque.boutonFermer(cible: self, action: #selector(fermer))])
        ligne.orientation = .horizontal
        ligne.alignment = .top
        ligne.spacing = 12
        return ligne
    }
}

// MARK: - « Ce que Dédale regarde sur ce poste »

/// Le panneau de transparence : chaque module, ce qu'il lit, ce qui part à la SOC, un
/// interrupteur par module, et ce que l'app ne lit jamais.
final class FenetreTransparence: FenetrePanneau {
    /// État de chaque module en une ligne (« ~/Downloads surveillé »), fourni par l'app.
    var etatModule: ((ModulePoste) -> String)?
    var piedDePage: String = ""

    init() { super.init(largeur: 560) }

    func afficher() {
        construire()
        montrer(capture: "transparence")
    }

    /// Reconstruit le contenu (interrupteurs et états à jour) sans bouger la fenêtre.
    func rafraichir() {
        guard panneau.isVisible else { return }
        construire()
        ajuster(centrer: false)
    }

    private func construire() {
        let w = largeur - 56
        let pile = NSStackView()
        pile.orientation = .vertical
        pile.alignment = .leading
        pile.spacing = 10
        pile.edgeInsets = NSEdgeInsets(top: 24, left: 28, bottom: 22, right: 28)

        let tete = entete(titre: "Ce que Dédale regarde sur ce poste",
                          sousTitre: "Chaque module se coupe ici. Coupé, il ne lit et n'envoie plus rien.")
        pile.addArrangedSubview(tete)
        tete.widthAnchor.constraint(equalToConstant: w).isActive = true
        pile.setCustomSpacing(18, after: tete)

        for m in ModulePoste.allCases {
            let carte = carteModule(m, largeur: w)
            pile.addArrangedSubview(carte)
            carte.widthAnchor.constraint(equalToConstant: w).isActive = true
        }
        if let derniere = pile.arrangedSubviews.last { pile.setCustomSpacing(18, after: derniere) }

        let jamais = carteJamais(largeur: w)
        pile.addArrangedSubview(jamais)
        jamais.widthAnchor.constraint(equalToConstant: w).isActive = true
        pile.setCustomSpacing(16, after: jamais)

        let bouton = BoutonDedale(titre: "Fermer", style: .neutre, cible: self, action: #selector(fermer))
        bouton.widthAnchor.constraint(equalToConstant: 96).isActive = true
        let pied = NSStackView(views: [Gabarit.etiquette(piedDePage, taille: 11, couleur: Teinte.discret),
                                       Gabarit.ressort(), bouton])
        pied.orientation = .horizontal
        pied.alignment = .centerY
        pile.addArrangedSubview(pied)
        pied.widthAnchor.constraint(equalToConstant: w).isActive = true
        poser(pile)
    }

    private func carteModule(_ m: ModulePoste, largeur w: CGFloat) -> NSView {
        let actif = ReglagesModules.partage.actif(m)
        let interieur = w - 40

        let tuile = NSView()
        tuile.wantsLayer = true
        tuile.layer?.cornerRadius = 9
        tuile.layer?.backgroundColor = (actif ? Teinte.cyan.withAlphaComponent(0.14) : Teinte.puce).cgColor
        tuile.translatesAutoresizingMaskIntoConstraints = false
        let icone = Gabarit.icone(m.symbole, taille: 14, couleurs: [actif ? Teinte.cyanFonce : Teinte.discret])
        tuile.addSubview(icone)
        NSLayoutConstraint.activate([
            tuile.widthAnchor.constraint(equalToConstant: 32), tuile.heightAnchor.constraint(equalToConstant: 32),
            icone.centerXAnchor.constraint(equalTo: tuile.centerXAnchor),
            icone.centerYAnchor.constraint(equalTo: tuile.centerYAnchor),
        ])
        let titre = Gabarit.etiquette(m.titre, taille: 14, graisse: .semibold, couleur: Teinte.encre)
        let etat = Gabarit.etiquette(actif ? (etatModule?(m) ?? "Actif") : "Coupé", taille: 11,
                                     couleur: actif ? Teinte.discret : Teinte.rouge)
        let textes = NSStackView(views: [titre, etat])
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 1
        let inter = Interrupteur(allume: actif)
        inter.target = self
        inter.action = #selector(basculer(_:))
        inter.identifier = NSUserInterfaceItemIdentifier(m.rawValue)
        inter.setAccessibilityLabel("Module \(m.titre)")
        let haut = NSStackView(views: [tuile, textes, Gabarit.ressort(), inter])
        haut.orientation = .horizontal
        haut.alignment = .centerY
        haut.spacing = 12

        func bloc(_ libelle: String, _ texte: String) -> NSView {
            let p = NSStackView(views: [Coque.surtitre(libelle),
                                        Gabarit.paragraphe(texte, taille: 12, couleur: actif ? Teinte.texte : Teinte.discret,
                                                           largeur: (interieur - 16) / 2)])
            p.orientation = .vertical
            p.alignment = .leading
            p.spacing = 4
            return p
        }
        let lit = bloc("Lit", m.lit)
        let envoie = bloc("Envoie à la SOC", m.envoie)
        let colonnes = NSStackView(views: [lit, envoie])
        colonnes.orientation = .horizontal
        colonnes.alignment = .top
        colonnes.distribution = .fillEqually
        colonnes.spacing = 16

        let contenu = NSStackView(views: [haut, colonnes])
        contenu.orientation = .vertical
        contenu.alignment = .leading
        contenu.spacing = 12
        haut.widthAnchor.constraint(equalToConstant: interieur).isActive = true
        colonnes.widthAnchor.constraint(equalToConstant: interieur).isActive = true
        return Coque.creer(contenu)
    }

    private func carteJamais(largeur w: CGFloat) -> NSView {
        let titre = NSStackView(views: [
            Gabarit.icone("eye.slash", taille: 13, couleurs: [Teinte.encre], cote: 18),
            Gabarit.etiquette("Ce que Dédale ne lit jamais", taille: 13, graisse: .semibold, couleur: Teinte.encre),
        ])
        titre.orientation = .horizontal
        titre.spacing = 6
        let pilules = ModulePoste.jamais.map { Coque.pilule($0, symbole: "nosign") }
        let rangees = Coque.rangees(pilules, largeur: w - 40)
        let note = Gabarit.paragraphe("L'app ne demande aucune autorisation d'enregistrer l'écran ou de suivre le clavier.",
                                      taille: 11, couleur: Teinte.discret, largeur: w - 40)
        let contenu = NSStackView(views: [titre, rangees, note])
        contenu.orientation = .vertical
        contenu.alignment = .leading
        contenu.spacing = 10
        return Coque.creer(contenu)
    }

    @objc private func basculer(_ inter: Interrupteur) {
        guard let id = inter.identifier?.rawValue, let m = ModulePoste(rawValue: id) else { return }
        let allume = inter.allume
        // Laisse l'animation de l'interrupteur finir avant de redessiner la carte.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.22) { [weak self] in
            ReglagesModules.partage.regler(m, actif: allume)
            self?.rafraichir()
            if let self { Gabarit.capturer(self.racine, nom: "transparence-\(m.rawValue)-\(allume ? "actif" : "coupe")") }
        }
    }

    /// Test : bascule un module par le vrai interrupteur, comme un clic.
    func basculerParClic(_ m: ModulePoste) {
        guard let inter = Self.interrupteurs(dans: racine).first(where: { $0.identifier?.rawValue == m.rawValue }) else { return }
        journal("clic automatique (test) sur l'interrupteur « \(m.titre) »")
        inter.basculer()
    }

    private static func interrupteurs(dans vue: NSView) -> [Interrupteur] {
        vue.subviews.flatMap { ($0 as? Interrupteur).map { [$0] } ?? interrupteurs(dans: $0) }
    }
}

// MARK: - Interrupteur

/// Interrupteur aux couleurs de Dédale : piste cyan allumé, grise éteint, pastille blanche qui
/// glisse. Dessiné en calques, il garde sa couleur même quand l'app n'est pas au premier plan
/// (un NSSwitch y devient gris dans les deux positions).
final class Interrupteur: NSControl {
    private(set) var allume: Bool
    private let piste = CALayer()
    private let pastille = CALayer()
    private static let taille = NSSize(width: 38, height: 22)

    init(allume: Bool) {
        self.allume = allume
        super.init(frame: NSRect(origin: .zero, size: Self.taille))
        wantsLayer = true
        translatesAutoresizingMaskIntoConstraints = false
        widthAnchor.constraint(equalToConstant: Self.taille.width).isActive = true
        heightAnchor.constraint(equalToConstant: Self.taille.height).isActive = true
        piste.frame = CGRect(origin: .zero, size: Self.taille)
        piste.cornerRadius = Self.taille.height / 2
        pastille.frame = CGRect(x: 2, y: 2, width: 18, height: 18)
        pastille.cornerRadius = 9
        pastille.backgroundColor = NSColor.white.cgColor
        pastille.shadowColor = NSColor.black.cgColor
        pastille.shadowOpacity = 0.18
        pastille.shadowRadius = 1.5
        pastille.shadowOffset = CGSize(width: 0, height: -0.5)
        layer?.addSublayer(piste)
        piste.addSublayer(pastille)
        setAccessibilityRole(.checkBox)
        appliquer(anime: false)
    }

    required init?(coder: NSCoder) { fatalError("non utilisé") }

    override var intrinsicContentSize: NSSize { Self.taille }
    override func resetCursorRects() { addCursorRect(bounds, cursor: .pointingHand) }
    override func mouseDown(with event: NSEvent) { basculer() }
    override func accessibilityValue() -> Any? { allume ? 1 : 0 }
    override func accessibilityPerformPress() -> Bool { basculer(); return true }

    func basculer() {
        allume.toggle()
        appliquer(anime: true)
        sendAction(action, to: target)
    }

    private func appliquer(anime: Bool) {
        CATransaction.begin()
        CATransaction.setDisableActions(!anime)
        CATransaction.setAnimationDuration(0.2)
        CATransaction.setAnimationTimingFunction(CAMediaTimingFunction(controlPoints: 0.32, 0.72, 0, 1))
        piste.backgroundColor = (allume ? Teinte.cyan : NSColor(hex: 0xD5D9E0)).cgColor
        pastille.frame.origin.x = allume ? Self.taille.width - 20 : 2
        CATransaction.commit()
    }
}
