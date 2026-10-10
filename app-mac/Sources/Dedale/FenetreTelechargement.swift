import AppKit
import DedaleNoyau

/// La pop-up d'un téléchargement à risque, sur la même carte blanche que celle des gestes à
/// risque : le fichier, d'où il vient, ce qu'il peut faire, puis « Garder » ou « Mettre de
/// côté ». Après le choix, une ligne dit ce qui s'est passé et la pop-up part seule.
final class FenetreTelechargement: NSObject {
    static let largeur: CGFloat = 400
    private static let interieur = largeur - 48

    /// Clics automatiques pour une démo filmée (`DEDALE_TELECHARGEMENT_AUTO`, par exemple
    /// `mettre_de_cote,garder`), un par pop-up, dans l'ordre d'arrivée.
    private static var clicsAuto: [String] = (ProcessInfo.processInfo.environment["DEDALE_TELECHARGEMENT_AUTO"] ?? "")
        .split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        .filter { ["mettre_de_cote", "garder"].contains($0) }

    let fichier: FichierSignale
    /// Appelé une fois, avec "mettre_de_cote" ou "garder".
    var surChoix: ((String) -> Void)?
    var surFermeture: (() -> Void)?

    private let racine = NSView()
    private let panneau: PanneauAlerte
    private let pile = NSStackView()
    private var boutonGarder: BoutonDedale!
    private var boutonCote: BoutonDedale!
    private var choixVues: [NSView] = []
    private let zoneFin = NSStackView()
    private var choisi = false
    private var fermee = false
    private var clavierActif = false

    init(_ f: FichierSignale) {
        fichier = f
        panneau = PanneauAlerte.carte(largeur: Self.largeur, racine: racine)
        super.init()
        construire()
    }

    // MARK: Construction

    private func construire() {
        panneau.surEchap = { [weak self] in
            guard let self, self.clavierActif, !self.choisi else { return }
            self.choisir("mettre_de_cote")
        }
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
        ])

        let w = Self.interieur
        let v = fichier.verdict
        let entete = Gabarit.entete(titre: "Dédale", puce: "Téléchargement")
        let tuile = Self.tuileFichier(fichier, largeur: w)
        let message = Gabarit.paragraphe(v.message, taille: Taille.titre, graisse: .semibold, couleur: Teinte.encre, largeur: w)
        let detail = Gabarit.paragraphe(v.detail, taille: Taille.texte, couleur: Teinte.texte, largeur: w)
        detail.isHidden = v.detail.isEmpty

        boutonGarder = BoutonDedale(titre: "Garder", style: .risque, cible: self, action: #selector(garder))
        boutonCote = BoutonDedale(titre: "Mettre de côté", style: .protege, cible: self, action: #selector(mettreDeCote))
        let boutons = NSStackView(views: [boutonGarder, boutonCote])
        boutons.orientation = .horizontal
        boutons.distribution = .fillEqually
        boutons.spacing = 10
        let note = Gabarit.paragraphe("Dans les deux cas, l'équipe sécurité reçoit le type du fichier, son origine et votre choix. Jamais son contenu ni son nom.",
                                      taille: Taille.note, couleur: Teinte.discret, largeur: w)

        zoneFin.orientation = .vertical
        zoneFin.alignment = .leading
        zoneFin.isHidden = true

        for vue in [entete, tuile, message, detail, boutons, note, zoneFin] as [NSView] {
            pile.addArrangedSubview(vue)
            vue.widthAnchor.constraint(equalToConstant: w).isActive = true
        }
        pile.setCustomSpacing(16, after: entete)
        pile.setCustomSpacing(16, after: tuile)
        pile.setCustomSpacing(detail.isHidden ? 20 : 6, after: message)
        pile.setCustomSpacing(20, after: detail)
        choixVues = [boutons, note]
    }

    /// Le fichier dans un bloc gris pâle, comme les faits d'une carte de la console
    /// (`.inv-faits`) : l'icône du type, le nom et sa provenance.
    static func tuileFichier(_ f: FichierSignale, largeur: CGFloat) -> NSView {
        let coeur = NSView()
        coeur.wantsLayer = true
        coeur.layer?.backgroundColor = Teinte.puits.cgColor
        coeur.layer?.cornerRadius = Rayon.bloc

        let haute = f.verdict.gravite == "haute"
        let fondIcone = NSView()
        fondIcone.wantsLayer = true
        fondIcone.layer?.backgroundColor = (haute ? Teinte.rougeFond : Teinte.puce).cgColor
        fondIcone.layer?.cornerRadius = Rayon.tuile
        fondIcone.translatesAutoresizingMaskIntoConstraints = false
        let icone = Gabarit.icone(symbole(f.verdict.typeFichier), taille: 15,
                                  couleurs: [haute ? Teinte.rouge : Teinte.texte], cote: 20)
        fondIcone.addSubview(icone)
        NSLayoutConstraint.activate([
            fondIcone.widthAnchor.constraint(equalToConstant: 36),
            fondIcone.heightAnchor.constraint(equalToConstant: 36),
            icone.centerXAnchor.constraint(equalTo: fondIcone.centerXAnchor),
            icone.centerYAnchor.constraint(equalTo: fondIcone.centerYAnchor),
        ])

        let nom = Gabarit.etiquette(f.nom, taille: Taille.texte, graisse: .semibold, couleur: Teinte.encre)
        nom.lineBreakMode = .byTruncatingMiddle
        nom.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let sous = Gabarit.etiquette(sousTitre(f), taille: Taille.note, couleur: Teinte.discret)
        sous.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        let textes = NSStackView(views: [nom, sous])
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 2
        let ligne = NSStackView(views: [fondIcone, textes])
        ligne.orientation = .horizontal
        ligne.alignment = .centerY
        ligne.spacing = 12
        ligne.edgeInsets = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 14)
        ligne.translatesAutoresizingMaskIntoConstraints = false
        coeur.addSubview(ligne)
        NSLayoutConstraint.activate([
            ligne.leadingAnchor.constraint(equalTo: coeur.leadingAnchor),
            ligne.trailingAnchor.constraint(equalTo: coeur.trailingAnchor),
            ligne.topAnchor.constraint(equalTo: coeur.topAnchor),
            ligne.bottomAnchor.constraint(equalTo: coeur.bottomAnchor),
            textes.widthAnchor.constraint(lessThanOrEqualToConstant: largeur - 90),
        ])
        return coeur
    }

    static func symbole(_ type: String) -> String {
        switch type {
        case "application": return "macwindow"
        case "script": return "terminal"
        case "image_disque": return "externaldrive"
        case "installeur": return "shippingbox"
        case "raccourci": return "link"
        case "document_macros": return "doc.badge.gearshape"
        case "archive_chiffree": return "lock.doc"
        default: return "doc"
        }
    }

    static func sousTitre(_ f: FichierSignale) -> String {
        var morceaux: [String] = []
        switch f.provenance.canal {
        case .mail: morceaux.append(f.provenance.domaine.map { "Mail de \($0)" } ?? "Pièce jointe d'un mail")
        case .site: morceaux.append(f.provenance.domaine ?? "Site inconnu")
        case .messagerie: morceaux.append("Messagerie")
        case .airdrop: morceaux.append("AirDrop")
        case .inconnue: morceaux.append("Provenance inconnue")
        case .locale: morceaux.append("Créé sur ce Mac")
        }
        if let t = f.taille { morceaux.append(taille(t)) }
        return morceaux.joined(separator: " · ")
    }

    /// « 798 octets », « 12 ko », « 1,4 Mo » (l'app n'a pas de traduction système à suivre).
    static func taille(_ octets: Int64) -> String {
        if octets < 1000 { return "\(octets) octet\(octets > 1 ? "s" : "")" }
        let f = NumberFormatter()
        f.locale = Locale(identifier: "fr_FR")
        f.maximumFractionDigits = 1
        let (valeur, unite): (Double, String) = octets < 1_000_000 ? (Double(octets) / 1000, "ko")
            : octets < 1_000_000_000 ? (Double(octets) / 1_000_000, "Mo") : (Double(octets) / 1_000_000_000, "Go")
        return "\(f.string(from: NSNumber(value: valeur)) ?? "\(Int(valeur))") \(unite)"
    }

    // MARK: Affichage

    func montrer() {
        ajusterTaille(garderLeHaut: false)
        panneau.alphaValue = 0
        panneau.makeKeyAndOrderFront(nil)
        panneau.makeFirstResponder(boutonCote)
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = Courbe.fluide
            panneau.animator().alphaValue = 1
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [weak self] in
            guard let self, !self.choisi else { return }
            self.clavierActif = true
            self.boutonCote.keyEquivalent = "\r"
        }
        journal("pop-up téléchargement affichée : \(fichier.verdict.typeFichier)")
        Gabarit.capturer(racine, nom: prefixe)
        if !Self.clicsAuto.isEmpty {
            let etape = Self.clicsAuto.removeFirst()
            let delai = Double(ProcessInfo.processInfo.environment["DEDALE_CLIC_DELAI"] ?? "") ?? 2
            DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in
                guard let self, !self.choisi else { return }
                journal("clic automatique (test) sur « \(etape == "garder" ? "Garder" : "Mettre de côté") »")
                (etape == "garder" ? self.boutonGarder : self.boutonCote)?.performClick(nil)
            }
        }
    }

    private var prefixe: String { "telechargement-" + fichier.verdict.typeFichier.replacingOccurrences(of: "_", with: "-") }

    @objc private func garder() { choisir("garder") }
    @objc private func mettreDeCote() { choisir("mettre_de_cote") }

    private func choisir(_ choix: String) {
        guard !choisi else { return }
        choisi = true
        boutonGarder.isEnabled = false
        boutonCote.isEnabled = false
        boutonCote.keyEquivalent = ""
        journal("choix du salarié (téléchargement) : \(choix)")
        surChoix?(choix)
    }

    /// Issue du choix : ce qui s'est passé sur le Mac et ce qui est parti à la SOC. Mis de côté
    /// en vert (réglé), déplacement impossible en orange (une action attend), gardé en rouge.
    func montrerIssue(choix: String, deplace: Bool, remonte: Bool) {
        let titre: String
        let texte: String
        let symbole: String
        let couleur: NSColor
        if choix == "mettre_de_cote" {
            symbole = deplace ? "checkmark.circle.fill" : "exclamationmark.circle.fill"
            couleur = deplace ? Teinte.ok : Teinte.orange
            titre = deplace ? "Mis de côté." : "Impossible de le déplacer."
            texte = deplace
                ? "Il est dans « \(SurveillanceTelechargements.nomMisDeCote) ». Le menu Dédale peut le remettre à sa place."
                : "Le fichier n'a pas bougé. Ne l'ouvrez pas et prévenez l'équipe sécurité."
        } else {
            symbole = "exclamationmark.triangle.fill"
            couleur = Teinte.rouge
            titre = "Gardé."
            texte = remonte ? "L'équipe sécurité est prévenue." : "La SOC est injoignable, rien n'a été signalé."
        }
        let textes = NSStackView(views: [
            Gabarit.etiquette(titre, taille: Taille.titreCarte, graisse: .semibold, couleur: Teinte.encre),
            Gabarit.paragraphe(texte, taille: Taille.libelle, couleur: Teinte.texte, largeur: Self.interieur - 28),
        ])
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 2
        let ligne = NSStackView(views: [Gabarit.icone(symbole, taille: 16, couleurs: [Teinte.fond, couleur]), textes])
        ligne.orientation = .horizontal
        ligne.alignment = .top
        ligne.spacing = 8
        choixVues.forEach { $0.isHidden = true }
        zoneFin.addArrangedSubview(ligne)
        ligne.widthAnchor.constraint(equalToConstant: Self.interieur).isActive = true
        zoneFin.isHidden = false
        ajusterTaille(garderLeHaut: true)
        Gabarit.capturer(racine, nom: prefixe + (choix == "garder" ? "-garde" : "-mis-de-cote"))
        DispatchQueue.main.asyncAfter(deadline: .now() + (choix == "garder" ? 2.6 : 4)) { [weak self] in self?.fermer() }
    }

    func fermer() {
        guard !fermee else { return }
        fermee = true
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            ctx.timingFunction = Courbe.fluide
            panneau.animator().alphaValue = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [self] in
            panneau.orderOut(nil)
            surFermeture?()
        }
    }

    private func ajusterTaille(garderLeHaut: Bool) {
        racine.layoutSubtreeIfNeeded()
        let taille = NSSize(width: Self.largeur, height: ceil(racine.fittingSize.height))
        var cadre = panneau.frame
        if garderLeHaut {
            cadre.origin.y = cadre.maxY - taille.height
        } else {
            let ecran = Ecran.zone
            cadre.origin.x = ecran.midX - taille.width / 2
            cadre.origin.y = ecran.minY + ecran.height * 0.62 - taille.height / 2
        }
        cadre.size = taille
        // Jamais hors de la zone visible : ni sous la barre de menus, ni sous le Dock.
        cadre = Ecran.borner(cadre)
        panneau.setFrame(cadre, display: true)
        panneau.invalidateShadow()
    }
}
