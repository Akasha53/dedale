import AppKit

// MARK: - Briques des panneaux du poste

enum Coque {
    /// Carte blanche au bord fin et aux coins de 18 points, comme une carte d'agent dans la
    /// console (`.inv-carte`) : une seule enveloppe, sans ombre. `contenu` la remplit avec
    /// `marge` points autour.
    static func creer(_ contenu: NSView, marge: NSEdgeInsets = NSEdgeInsets(top: 16, left: 18, bottom: 16, right: 18),
                      rayon: CGFloat = Rayon.carte) -> NSView {
        let carte = NSView()
        carte.wantsLayer = true
        carte.layer?.backgroundColor = Teinte.fond.cgColor
        carte.layer?.cornerRadius = rayon
        carte.layer?.borderWidth = 1
        carte.layer?.borderColor = Teinte.bord.cgColor
        contenu.translatesAutoresizingMaskIntoConstraints = false
        carte.addSubview(contenu)
        NSLayoutConstraint.activate([
            contenu.leadingAnchor.constraint(equalTo: carte.leadingAnchor, constant: marge.left),
            contenu.trailingAnchor.constraint(equalTo: carte.trailingAnchor, constant: -marge.right),
            contenu.topAnchor.constraint(equalTo: carte.topAnchor, constant: marge.top),
            contenu.bottomAnchor.constraint(equalTo: carte.bottomAnchor, constant: -marge.bottom),
        ])
        return carte
    }

    /// Pilule de texte, comme les puces de la console : neutre (gris pâle), risque (rouge
    /// pâle, comme « Droits en trop ») ou accent (gris plus marqué, texte noir).
    enum Ton { case neutre, risque, accent }

    static func pilule(_ texte: String, ton: Ton = .neutre, symbole: String? = nil) -> NSView {
        let fond = FondPilule()
        fond.wantsLayer = true
        let (bg, encre): (NSColor, NSColor)
        switch ton {
        case .neutre: (bg, encre) = (Teinte.puce, Teinte.texte)
        case .risque: (bg, encre) = (Teinte.rougeFond, Teinte.rouge)
        case .accent: (bg, encre) = (Teinte.actif, Teinte.encre)
        }
        fond.layer?.backgroundColor = bg.cgColor
        var vues: [NSView] = []
        if let symbole { vues.append(Gabarit.icone(symbole, taille: 9, couleurs: [encre], cote: 11)) }
        vues.append(Gabarit.etiquette(texte, taille: Taille.puce, couleur: encre))
        let pile = NSStackView(views: vues)
        pile.orientation = .horizontal
        pile.spacing = 4
        pile.edgeInsets = NSEdgeInsets(top: 2, left: 9, bottom: 2, right: 9)
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

    /// Petit libellé au-dessus d'un texte : casse normale, gris, comme les libellés de la
    /// console (`.ag-lib`, `.inv-faits dt`).
    static func surtitre(_ texte: String) -> NSTextField {
        Gabarit.etiquette(texte, taille: Taille.pastille, graisse: .medium, couleur: Teinte.discret)
    }

    /// Bouton de fermeture discret, en haut à droite d'un panneau.
    static func boutonFermer(cible: AnyObject, action: Selector) -> NSButton {
        BoutonIcone(symbole: "xmark", cible: cible, action: action)
    }
}

/// Fenêtre d'un panneau du poste : carte blanche de la console, au centre de la zone visible
/// de l'écran, fermée par Échap ou par son bouton. L'en-tête et le pied restent fixes ; le corps
/// défile quand le panneau dépasserait 85 % de la hauteur visible.
class FenetrePanneau: NSObject {
    /// Part de la hauteur visible de l'écran que le panneau peut prendre.
    static let partEcran: CGFloat = 0.85

    let racine = NSView()
    let panneau: PanneauAlerte
    let largeur: CGFloat
    var surFermeture: (() -> Void)?

    private var colonne: NSStackView?
    private var corps: NSView?
    private var defile: NSScrollView?
    private var hauteurDefile: NSLayoutConstraint?
    private var filets: [NSView] = []
    private var positionAGarder: NSPoint?

    init(largeur: CGFloat) {
        self.largeur = largeur
        panneau = PanneauAlerte.carte(largeur: largeur, racine: racine)
        super.init()
        panneau.surEchap = { [weak self] in self?.fermer() }
    }

    /// Pose l'en-tête (fixe), le corps (qui défile s'il le faut) et le pied (fixe). Les trois
    /// font `largeur - 56` points de large ; les marges sont posées ici.
    func poser(tete: NSView, corps: NSStackView, pied: NSView) {
        positionAGarder = defile?.contentView.bounds.origin
        colonne?.removeFromSuperview()

        let haut = NSStackView(views: [tete])
        haut.edgeInsets = NSEdgeInsets(top: 24, left: 28, bottom: 16, right: 28)
        let bas = NSStackView(views: [pied])
        bas.edgeInsets = NSEdgeInsets(top: 14, left: 28, bottom: 22, right: 28)
        corps.edgeInsets = NSEdgeInsets(top: 2, left: 28, bottom: 4, right: 28)

        let doc = VueRetournee()
        doc.translatesAutoresizingMaskIntoConstraints = false
        corps.translatesAutoresizingMaskIntoConstraints = false
        doc.addSubview(corps)
        let defile = NSScrollView()
        defile.drawsBackground = false
        defile.borderType = .noBorder
        defile.hasVerticalScroller = true
        defile.autohidesScrollers = true
        defile.scrollerStyle = .overlay
        defile.documentView = doc
        defile.translatesAutoresizingMaskIntoConstraints = false
        let hauteur = defile.heightAnchor.constraint(equalToConstant: 100)
        NSLayoutConstraint.activate([
            corps.leadingAnchor.constraint(equalTo: doc.leadingAnchor),
            corps.trailingAnchor.constraint(equalTo: doc.trailingAnchor),
            corps.topAnchor.constraint(equalTo: doc.topAnchor),
            corps.bottomAnchor.constraint(equalTo: doc.bottomAnchor),
            doc.leadingAnchor.constraint(equalTo: defile.contentView.leadingAnchor),
            doc.trailingAnchor.constraint(equalTo: defile.contentView.trailingAnchor),
            doc.topAnchor.constraint(equalTo: defile.contentView.topAnchor),
            hauteur,
        ])

        // Filets fins au-dessus et au-dessous du corps, visibles seulement quand il défile.
        let filets = (0..<2).map { _ -> NSView in
            let f = NSView()
            f.wantsLayer = true
            f.layer?.backgroundColor = Teinte.bord.cgColor
            f.heightAnchor.constraint(equalToConstant: 1).isActive = true
            return f
        }
        let colonne = NSStackView(views: [haut, filets[0], defile, filets[1], bas])
        colonne.orientation = .vertical
        colonne.alignment = .leading
        colonne.spacing = 0
        colonne.translatesAutoresizingMaskIntoConstraints = false
        racine.addSubview(colonne)
        NSLayoutConstraint.activate([
            colonne.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            colonne.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
            colonne.topAnchor.constraint(equalTo: racine.topAnchor),
            colonne.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
        ])
        for v in [haut, filets[0], defile, filets[1], bas] as [NSView] {
            v.widthAnchor.constraint(equalToConstant: largeur).isActive = true
        }
        self.colonne = colonne
        self.corps = corps
        self.defile = defile
        self.hauteurDefile = hauteur
        self.filets = filets
    }

    func montrer(capture: String) {
        ajuster(centrer: !panneau.isVisible)
        if !panneau.isVisible {
            panneau.alphaValue = 0
            panneau.makeKeyAndOrderFront(nil)
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.22
                ctx.timingFunction = Courbe.fluide
                panneau.animator().alphaValue = 1
            }
        }
        Gabarit.capturer(racine, nom: capture, delai: 0.8)
    }

    /// Taille le panneau : au plus 85 % de la hauteur visible, le corps défile au-delà.
    /// Centré dans la zone visible à l'ouverture, puis le haut reste en place.
    func ajuster(centrer: Bool) {
        guard let corps, let defile, let hauteurDefile, let colonne else { return }
        racine.layoutSubtreeIfNeeded()
        let visible = Ecran.visible
        let besoin = ceil(corps.fittingSize.height)
        let fixe = colonne.arrangedSubviews.filter { $0 !== defile }.reduce(CGFloat(0)) { $0 + $1.fittingSize.height }
        let plafond = min(floor(visible.height * Self.partEcran), Ecran.zone.height)
        let hauteur = max(80, min(besoin, plafond - fixe))
        let defilant = besoin > hauteur
        hauteurDefile.constant = hauteur
        filets.forEach { $0.alphaValue = defilant ? 1 : 0 }
        racine.layoutSubtreeIfNeeded()
        if let p = positionAGarder {
            defile.contentView.scroll(to: NSPoint(x: 0, y: min(p.y, max(0, besoin - hauteur))))
            defile.reflectScrolledClipView(defile.contentView)
            positionAGarder = nil
        }

        let taille = NSSize(width: largeur, height: ceil(racine.fittingSize.height))
        var cadre = panneau.frame
        if centrer {
            let zone = Ecran.zone
            cadre.origin.x = zone.midX - taille.width / 2
            cadre.origin.y = zone.midY - taille.height / 2
        } else {
            cadre.origin.y = cadre.maxY - taille.height
        }
        cadre.size = taille
        cadre = Ecran.borner(cadre)
        panneau.setFrame(cadre, display: true)
        panneau.invalidateShadow()
        journal("panneau : \(Int(taille.width))×\(Int(taille.height)) points sur une zone visible de "
                + "\(Int(visible.width))×\(Int(visible.height)), corps \(Int(besoin)) points"
                + (defilant ? ", défile" : ", sans défilement"))
    }

    @objc func fermer() {
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = Courbe.fluide
            panneau.animator().alphaValue = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [self] in
            panneau.orderOut(nil)
            surFermeture?()
        }
    }

    /// En-tête : marque, titre, sous-titre, bouton de fermeture.
    func entete(titre: String, sousTitre: String) -> NSView {
        // Largeur utile moins la marque (28), le bouton (28) et trois espaces de 12.
        let largeurTexte = largeur - 56 - 28 - 28 - 36 - 2
        let sous = Gabarit.paragraphe(sousTitre, taille: Taille.libelle, couleur: Teinte.discret, largeur: largeurTexte)
        sous.widthAnchor.constraint(equalToConstant: largeurTexte).isActive = true
        let textes = NSStackView(views: [
            Gabarit.etiquette(titre, taille: Taille.titrePanneau, graisse: .semibold, couleur: Teinte.encre), sous,
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

    /// Large de 880 points quand l'écran le permet : les quatre modules tiennent alors en deux
    /// colonnes et le panneau défile à peine, même sur un écran de 13 pouces.
    init() { super.init(largeur: min(880, max(560, Ecran.zone.width))) }

    private var deuxColonnes: Bool { largeur >= 760 }

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
        let tete = entete(titre: "Ce que Dédale regarde sur ce poste",
                          sousTitre: "Chaque module se coupe ici. Coupé, il ne lit et n'envoie plus rien.")
        tete.widthAnchor.constraint(equalToConstant: w).isActive = true

        let corps = NSStackView()
        corps.orientation = .vertical
        corps.alignment = .leading
        corps.spacing = 12
        let modules = ModulePoste.allCases
        if deuxColonnes {
            // Deux cartes par rangée, de même hauteur.
            let lc = floor((w - 12) / 2)
            for i in stride(from: 0, to: modules.count, by: 2) {
                let cartes = modules[i..<min(i + 2, modules.count)].map { carteModule($0, largeur: lc) }
                let rangee = NSStackView(views: cartes)
                rangee.orientation = .horizontal
                rangee.alignment = .top
                rangee.spacing = 12
                for c in cartes { c.widthAnchor.constraint(equalToConstant: lc).isActive = true }
                if cartes.count == 2 { cartes[0].heightAnchor.constraint(equalTo: cartes[1].heightAnchor).isActive = true }
                corps.addArrangedSubview(rangee)
                rangee.widthAnchor.constraint(equalToConstant: w).isActive = true
            }
        } else {
            for m in modules {
                let carte = carteModule(m, largeur: w)
                corps.addArrangedSubview(carte)
                carte.widthAnchor.constraint(equalToConstant: w).isActive = true
            }
        }
        if let derniere = corps.arrangedSubviews.last { corps.setCustomSpacing(16, after: derniere) }
        let jamais = carteJamais(largeur: w)
        corps.addArrangedSubview(jamais)
        jamais.widthAnchor.constraint(equalToConstant: w).isActive = true

        let bouton = BoutonDedale(titre: "Fermer", style: .neutre, cible: self, action: #selector(fermer))
        bouton.widthAnchor.constraint(equalToConstant: 96).isActive = true
        let pied = NSStackView(views: [Gabarit.etiquette(piedDePage, taille: Taille.note, couleur: Teinte.discret),
                                       Gabarit.ressort(), bouton])
        pied.orientation = .horizontal
        pied.alignment = .centerY
        pied.widthAnchor.constraint(equalToConstant: w).isActive = true
        poser(tete: tete, corps: corps, pied: pied)
    }

    private func carteModule(_ m: ModulePoste, largeur w: CGFloat) -> NSView {
        let actif = ReglagesModules.partage.actif(m)
        let interieur = w - 36  // marges de la carte : 18 + 18

        let tuile = NSView()
        tuile.wantsLayer = true
        tuile.layer?.cornerRadius = Rayon.tuile
        tuile.layer?.backgroundColor = Teinte.puce.cgColor
        tuile.translatesAutoresizingMaskIntoConstraints = false
        let icone = Gabarit.icone(m.symbole, taille: 14, couleurs: [actif ? Teinte.encre : Teinte.gris])
        tuile.addSubview(icone)
        NSLayoutConstraint.activate([
            tuile.widthAnchor.constraint(equalToConstant: 32), tuile.heightAnchor.constraint(equalToConstant: 32),
            icone.centerXAnchor.constraint(equalTo: tuile.centerXAnchor),
            icone.centerYAnchor.constraint(equalTo: tuile.centerYAnchor),
        ])
        let titre = Gabarit.etiquette(m.titre, taille: Taille.titreCarte, graisse: .semibold, couleur: Teinte.encre)
        // Coupé : orange, comme ce qui attend une décision dans la console.
        let etat = Gabarit.etiquette(actif ? (etatModule?(m) ?? "Actif") : "Coupé", taille: Taille.note,
                                     couleur: actif ? Teinte.discret : Teinte.orange)
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
                                        Gabarit.paragraphe(texte, taille: Taille.libelle, couleur: actif ? Teinte.texte : Teinte.discret,
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
            Gabarit.etiquette("Ce que Dédale ne lit jamais", taille: Taille.titreCarte, graisse: .semibold, couleur: Teinte.encre),
        ])
        titre.orientation = .horizontal
        titre.spacing = 6
        let pilules = ModulePoste.jamais.map { Coque.pilule($0, symbole: "nosign") }
        let rangees = Coque.rangees(pilules, largeur: w - 36)
        let note = Gabarit.paragraphe("L'app ne demande aucune autorisation d'enregistrer l'écran ou de suivre le clavier.",
                                      taille: Taille.note, couleur: Teinte.discret, largeur: w - 36)
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

/// Interrupteur aux couleurs de la console : piste noire allumé, gris clair éteint, pastille
/// blanche qui glisse. Dessiné en calques, il garde sa couleur même quand l'app n'est pas au premier plan
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
        pastille.backgroundColor = Teinte.fond.cgColor
        pastille.shadowColor = Teinte.encre.cgColor
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
        CATransaction.setAnimationTimingFunction(Courbe.fluide)
        piste.backgroundColor = (allume ? Teinte.encre : Teinte.eteint).cgColor
        pastille.frame.origin.x = allume ? Self.taille.width - 20 : 2
        CATransaction.commit()
    }
}
