import AppKit

/// Petite fenêtre « Voir le mail » : le mail en texte brut, désarmé. Aucun HTML n'est rendu,
/// aucune image ni pièce jointe ne se charge, les liens sont réécrits (`hxxps://`, `[.]`) et
/// ne sont pas cliquables.
final class FenetreApercu: NSObject {
    static let largeur: CGFloat = 460
    private static let interieur = largeur - 48

    var surFermeture: (() -> Void)?

    private let racine = NSView()
    private let panneau: PanneauAlerte
    private let pile = NSStackView()
    private let zone = NSStackView()
    private let resume: MailResume
    private var fermee = false

    init(_ m: MailResume) {
        resume = m
        panneau = PanneauAlerte.carte(largeur: Self.largeur, racine: racine)
        super.init()
        panneau.surEchap = { [weak self] in self?.fermer() }

        pile.orientation = .vertical
        pile.alignment = .leading
        pile.spacing = 10
        pile.edgeInsets = NSEdgeInsets(top: 20, left: 24, bottom: 20, right: 24)
        pile.translatesAutoresizingMaskIntoConstraints = false
        racine.addSubview(pile)
        NSLayoutConstraint.activate([
            pile.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            pile.trailingAnchor.constraint(equalTo: racine.trailingAnchor),
            pile.topAnchor.constraint(equalTo: racine.topAnchor),
            pile.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
        ])
        zone.orientation = .vertical
        zone.alignment = .leading
        zone.spacing = 6

        let fermer = BoutonDedale(titre: "Fermer", style: .neutre, cible: self, action: #selector(clicFermer))
        fermer.widthAnchor.constraint(equalToConstant: 110).isActive = true
        let bas = NSStackView(views: [Gabarit.ressort(), fermer])
        bas.orientation = .horizontal

        for v in [Gabarit.entete(titre: "Aperçu du mail", puce: "Désarmé"), zone, bas] as [NSView] {
            pile.addArrangedSubview(v)
            v.widthAnchor.constraint(equalToConstant: Self.interieur).isActive = true
        }
        pile.setCustomSpacing(14, after: pile.arrangedSubviews[0])
        pile.setCustomSpacing(16, after: zone)
        remplir(mail: nil, message: "Chargement du mail…")
    }

    /// Affiche le panneau à côté de `voisin` (la pop-up), sinon au centre de l'écran.
    func montrer(pres voisin: NSRect?) {
        ajuster()
        var cadre = panneau.frame
        let ecran = Ecran.zone
        if let v = voisin {
            cadre.origin.x = v.maxX + 16 + cadre.width <= ecran.maxX ? v.maxX + 16 : max(ecran.minX, v.minX - 16 - cadre.width)
            cadre.origin.y = max(ecran.minY, v.maxY - cadre.height)
        } else {
            cadre.origin.x = ecran.midX - cadre.width / 2
            cadre.origin.y = ecran.midY - cadre.height / 2
        }
        panneau.setFrameOrigin(Ecran.borner(cadre).origin)
        panneau.makeKeyAndOrderFront(nil)
        journal("aperçu du mail \(resume.id) ouvert")
    }

    /// Remplit l'aperçu avec le mail chargé, ou un message si la boîte ne répond pas.
    func afficher(_ mail: MailComplet?) {
        remplir(mail: mail, message: mail == nil ? "La boîte de démo ne répond pas. Aperçu indisponible." : nil)
        ajuster(garderLeHaut: true)
        Gabarit.capturer(racine, nom: "apercu-mail")
        // Test : avec DEDALE_CLIC_AUTO, l'aperçu se referme seul.
        if ProcessInfo.processInfo.environment["DEDALE_CLIC_AUTO"] != nil {
            let delai = Double(ProcessInfo.processInfo.environment["DEDALE_CLIC_DELAI"] ?? "") ?? 2
            DispatchQueue.main.asyncAfter(deadline: .now() + delai * 2) { [weak self] in self?.fermer() }
        }
    }

    private func remplir(mail: MailComplet?, message: String?) {
        zone.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let w = Self.interieur
        let r = mail?.resume ?? resume
        var vues: [NSView] = [
            Gabarit.paragraphe(Messagerie.desarmerLigne(r.objet, max: 140), taille: Taille.titreCarte, graisse: .semibold,
                               couleur: Teinte.encre, largeur: w),
        ]
        var meta = ["De : " + (r.expediteur.isEmpty ? "inconnu" : Messagerie.desarmerLigne(r.expediteur))]
        if let dest = mail?.destinataire, !dest.isEmpty { meta.append("À : " + Messagerie.desarmerLigne(dest)) }
        if let date = r.date { meta.append("Reçu : " + Self.dateLisible(date)) }
        vues.append(Gabarit.paragraphe(meta.joined(separator: "\n"), taille: Taille.libelle, couleur: Teinte.discret, largeur: w))

        let bandeau = NSStackView(views: [
            Gabarit.icone("link", taille: 11, couleurs: [Teinte.texte], cote: 14),
            Gabarit.etiquette("Liens désactivés et réécrits. Rien ne se charge.", taille: Taille.note, couleur: Teinte.texte),
        ])
        bandeau.orientation = .horizontal
        bandeau.alignment = .centerY
        bandeau.spacing = 6
        bandeau.edgeInsets = NSEdgeInsets(top: 7, left: 12, bottom: 7, right: 14)
        bandeau.wantsLayer = true
        bandeau.layer?.backgroundColor = Teinte.puits.cgColor
        bandeau.layer?.cornerRadius = Rayon.petit
        vues.append(bandeau)

        if let message {
            vues.append(Gabarit.paragraphe(message, taille: Taille.texte, couleur: Teinte.texte, largeur: w))
        } else if let mail {
            vues.append(corps(Self.texteDuMail(mail), largeur: w))
        }
        for (i, v) in vues.enumerated() {
            zone.addArrangedSubview(v)
            if i == 2 {
                zone.setCustomSpacing(12, after: v)
            } else {
                v.widthAnchor.constraint(equalToConstant: w).isActive = true
            }
        }
        zone.setCustomSpacing(10, after: vues[1])
    }

    /// « 10 oct. à 19:55 » pour une date ISO, sinon la date telle quelle.
    static func dateLisible(_ brut: String) -> String {
        let lecteur = ISO8601DateFormatter()
        lecteur.formatOptions = [.withInternetDateTime]
        var date = lecteur.date(from: brut)
        if date == nil {
            lecteur.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            date = lecteur.date(from: brut)
        }
        guard let date else { return brut }
        let f = DateFormatter()
        f.locale = Locale(identifier: "fr_FR")
        f.dateFormat = "d MMM 'à' HH:mm"
        return f.string(from: date)
    }

    /// Le corps désarmé, puis ce qui ne se voit pas à l'écran : où mènent vraiment les liens,
    /// les pièces jointes (jamais ouvertes) et le texte caché relevé par l'analyseur.
    static func texteDuMail(_ mail: MailComplet) -> NSAttributedString {
        let normal: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: Taille.texte),
                                                     .foregroundColor: Teinte.texte]
        let titre: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: Taille.libelle, weight: .semibold),
                                                    .foregroundColor: Teinte.encre]
        let alerte: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: Taille.libelle),
                                                     .foregroundColor: Teinte.rouge]
        let note: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: Taille.libelle),
                                                   .foregroundColor: Teinte.texte]
        let sortie = NSMutableAttributedString(string: Messagerie.desarmer(mail.corps).isEmpty
                                               ? "(mail vide)" : Messagerie.desarmer(mail.corps), attributes: normal)
        func section(_ nom: String, _ lignes: [(String, Bool)]) {
            guard !lignes.isEmpty else { return }
            sortie.append(NSAttributedString(string: "\n\n" + nom, attributes: titre))
            for (ligne, rouge) in lignes {
                sortie.append(NSAttributedString(string: "\n" + ligne, attributes: rouge ? alerte : note))
            }
        }
        section("Liens du mail", mail.liens.prefix(5).map { l in
            let dest = Messagerie.desarmerLigne(l.destination, max: 90)
            let affiche = Messagerie.desarmerLigne(l.texte, max: 50)
            if l.suspect { return ("Lien trompeur : « \(affiche) » mène à \(dest)", true) }
            return (affiche.isEmpty ? dest : "« \(affiche) » mène à \(dest)", false)
        })
        section("Pièces jointes, non ouvertes", mail.pieces.prefix(5).map { (Messagerie.desarmerLigne($0, max: 80), false) })
        section("Texte caché dans le mail, invisible à l'écran",
                mail.cache.prefix(3).map { (Messagerie.desarmer($0, max: 600), true) })
        return sortie
    }

    /// Le corps, en texte brut dans une zone qui défile au-delà de 280 points.
    private func corps(_ texte: NSAttributedString, largeur: CGFloat) -> NSView {
        let vue = NSTextView(frame: NSRect(x: 0, y: 0, width: largeur, height: 10))
        vue.isEditable = false
        vue.isSelectable = true
        vue.isRichText = false
        vue.importsGraphics = false
        vue.isAutomaticLinkDetectionEnabled = false
        vue.isAutomaticDataDetectionEnabled = false
        vue.drawsBackground = false
        vue.textContainerInset = .zero
        vue.textContainer?.lineFragmentPadding = 0
        vue.textContainer?.widthTracksTextView = true
        vue.textStorage?.setAttributedString(texte)
        vue.isVerticallyResizable = true
        vue.layoutManager?.ensureLayout(for: vue.textContainer!)
        let hauteurTexte = ceil(vue.layoutManager?.usedRect(for: vue.textContainer!).height ?? 100)
        vue.frame.size.height = hauteurTexte

        let defile = NSScrollView()
        defile.drawsBackground = false
        defile.hasVerticalScroller = hauteurTexte > 280
        defile.autohidesScrollers = true
        defile.borderType = .noBorder
        defile.documentView = vue
        defile.translatesAutoresizingMaskIntoConstraints = false
        defile.heightAnchor.constraint(equalToConstant: min(hauteurTexte, 280)).isActive = true
        return defile
    }

    private func ajuster(garderLeHaut: Bool = false) {
        racine.layoutSubtreeIfNeeded()
        var cadre = panneau.frame
        let hauteur = ceil(racine.fittingSize.height)
        if garderLeHaut { cadre.origin.y = cadre.maxY - hauteur }
        cadre.size = NSSize(width: Self.largeur, height: hauteur)
        panneau.setFrame(Ecran.borner(cadre), display: true)
        panneau.invalidateShadow()
    }

    @objc private func clicFermer() { fermer() }

    func fermer() {
        guard !fermee else { return }
        fermee = true
        panneau.orderOut(nil)
        surFermeture?()
    }
}

/// Petite confirmation en haut à droite de l'écran, qui s'efface seule.
final class Bulle: NSObject {
    private let racine = NSView()
    private let panneau: PanneauAlerte

    init(_ texte: String, ok: Bool) {
        panneau = PanneauAlerte.carte(largeur: 300, racine: racine, rayon: Rayon.bulle)
        super.init()
        let ligne = NSStackView(views: [
            Gabarit.icone(ok ? "checkmark.circle.fill" : "exclamationmark.triangle.fill", taille: 15,
                          couleurs: [Teinte.fond, ok ? Teinte.ok : Teinte.orange]),
            Gabarit.paragraphe(texte, taille: Taille.texte, graisse: .medium, couleur: Teinte.encre, largeur: 300 - 64),
        ])
        ligne.orientation = .horizontal
        ligne.alignment = .centerY
        ligne.spacing = 8
        ligne.edgeInsets = NSEdgeInsets(top: 14, left: 16, bottom: 14, right: 16)
        ligne.translatesAutoresizingMaskIntoConstraints = false
        racine.addSubview(ligne)
        NSLayoutConstraint.activate([
            ligne.leadingAnchor.constraint(equalTo: racine.leadingAnchor),
            ligne.trailingAnchor.constraint(lessThanOrEqualTo: racine.trailingAnchor),
            ligne.topAnchor.constraint(equalTo: racine.topAnchor),
            ligne.bottomAnchor.constraint(equalTo: racine.bottomAnchor),
        ])
    }

    func montrer(capture: String? = nil) {
        racine.layoutSubtreeIfNeeded()
        let taille = NSSize(width: 300, height: ceil(racine.fittingSize.height))
        let ecran = Ecran.zone
        panneau.setFrame(Ecran.borner(NSRect(x: ecran.maxX - taille.width, y: ecran.maxY - taille.height,
                                             width: taille.width, height: taille.height)), display: true)
        panneau.alphaValue = 0
        panneau.orderFrontRegardless()
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = Courbe.fluide
            panneau.animator().alphaValue = 1
        }
        if let capture { Gabarit.capturer(racine, nom: capture, delai: 0.4, rayon: Rayon.bulle) }
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { [self] in
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = 0.25
                panneau.animator().alphaValue = 0
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { [self] in panneau.orderOut(nil) }
        }
    }
}
