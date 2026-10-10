import AppKit

/// La pop-up d'un geste à risque, en verre clair. Elle passe par plusieurs états :
/// - le choix : message, raisons, « Voir le mail » pour un mail, puis Annuler / Continuer ;
/// - le coach, après Annuler : ce qui était piégé, comment le repérer, « Compris » ;
/// - l'attente des quatre yeux, après Continuer sur un geste critique, puis Accordé ou Refusé ;
/// - la confirmation, après Continuer sur un geste ordinaire.
final class FenetreAlerte: NSObject {
    static let largeur: CGFloat = 400
    private static let interieur = largeur - 48

    enum Etat { case choix, coach, attente, fin }

    let avertissement: Avertissement
    /// Appelé une seule fois, avec "annuler" ou "continuer".
    var surChoix: ((String) -> Void)?
    /// Appelé quand le salarié demande à voir le mail.
    var surVoirMail: (() -> Void)?
    /// Appelé quand la pop-up a disparu.
    var surFermeture: (() -> Void)?

    private(set) var etat: Etat = .choix
    private let racine = NSView()
    private let panneau: PanneauAlerte
    private let pile = NSStackView()
    private var choixVues: [NSView] = []
    private var boutonAnnuler: BoutonDedale!
    private var boutonContinuer: BoutonDedale!
    private var boutonVoir: BoutonDedale?
    private var boutonCompris: BoutonDedale?
    private let zoneFin = NSStackView()
    private var texteAttente: NSTextField?
    private var choisi = false
    private var fermee = false
    /// Entrée et Échap n'agissent qu'une seconde après l'apparition : quelqu'un qui tape
    /// dans une autre fenêtre ne ferme pas l'alerte sans l'avoir vue.
    private var clavierActif = false
    /// Étapes de clic automatique (DEDALE_CLIC_AUTO), consommées dans l'ordre.
    private var etapesAuto: [String]

    var cadre: NSRect { panneau.frame }

    init(_ a: Avertissement) {
        avertissement = a
        panneau = PanneauAlerte.carte(largeur: Self.largeur, racine: racine)
        etapesAuto = (ProcessInfo.processInfo.environment["DEDALE_CLIC_AUTO"] ?? "")
            .split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { ["voir", "annuler", "continuer", "compris"].contains($0) }
        super.init()
        construire()
    }

    // MARK: Construction

    private func construire() {
        panneau.surEchap = { [weak self] in
            guard let self, self.clavierActif else { return }
            switch self.etat {
            case .choix: self.choisir("annuler")
            case .coach: self.compris()
            default: break
            }
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

        let a = avertissement
        let w = Self.interieur
        let entete = Gabarit.entete(titre: "Dédale", puce: a.libelleCategorie)
        let message = Gabarit.paragraphe(a.message, taille: 17, graisse: .semibold, couleur: Teinte.encre, largeur: w)

        // Pour un mail : « objet » · expéditeur, sur une ligne, désarmés.
        var ligneMail: NSTextField?
        if let m = a.mail {
            let exp = m.adresse.isEmpty ? "" : " · \(Messagerie.desarmerLigne(m.adresse, max: 60))"
            let t = Gabarit.paragraphe("« \(Messagerie.desarmerLigne(m.objet, max: 80)) »\(exp)", taille: 12,
                                       couleur: Teinte.discret, largeur: w)
            t.maximumNumberOfLines = 2
            t.cell?.truncatesLastVisibleLine = true
            ligneMail = t
        }
        let detail = Gabarit.paragraphe(a.detail, taille: 13, couleur: Teinte.texte, largeur: w)
        detail.isHidden = a.detail.isEmpty

        if a.mail != nil {
            boutonVoir = BoutonDedale(titre: "Voir le mail", style: .lien, cible: self, action: #selector(voir))
        }

        boutonContinuer = BoutonDedale(titre: a.titreContinuer ?? "Continuer", style: .risque, cible: self,
                                       action: #selector(continuer))
        boutonAnnuler = BoutonDedale(titre: a.titreAnnuler ?? "Annuler", style: .protege, cible: self, action: #selector(annuler))
        let boutons = NSStackView(views: [boutonContinuer, boutonAnnuler])
        boutons.orientation = .horizontal
        boutons.distribution = .fillEqually
        boutons.spacing = 10

        let note = Gabarit.paragraphe(
            a.quatreYeux ? "Geste sensible : Dédale le relit avant qu'il parte, et la SOC voit sa décision."
                         : "Si vous continuez, l'équipe sécurité est prévenue.",
            taille: 11, couleur: Teinte.discret, largeur: w)

        zoneFin.orientation = .vertical
        zoneFin.alignment = .leading
        zoneFin.spacing = 8
        zoneFin.isHidden = true

        var vues: [NSView] = [entete, message]
        if let ligneMail { vues.append(ligneMail) }
        vues.append(detail)
        if let boutonVoir { vues.append(boutonVoir) }
        vues += [boutons, note, zoneFin]
        for v in vues {
            pile.addArrangedSubview(v)
            if v !== boutonVoir { v.widthAnchor.constraint(equalToConstant: w).isActive = true }
        }
        pile.setCustomSpacing(14, after: entete)
        pile.setCustomSpacing(ligneMail != nil ? 4 : (detail.isHidden ? 20 : 6), after: message)
        if let ligneMail { pile.setCustomSpacing(detail.isHidden ? 20 : 10, after: ligneMail) }
        pile.setCustomSpacing(boutonVoir != nil ? 6 : 20, after: detail)
        if let boutonVoir { pile.setCustomSpacing(14, after: boutonVoir) }
        pile.setCustomSpacing(10, after: boutons)
        // Ce qui disparaît quand on quitte l'état de choix.
        choixVues = [boutons, note] + (boutonVoir.map { [$0] } ?? [])
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
        capturer("")
        planifierAuto()
    }

    @objc private func annuler() { choisir("annuler") }
    @objc private func continuer() { choisir("continuer") }
    @objc private func voir() { surVoirMail?() }

    @objc private func compris() {
        guard etat == .coach else { return }
        journal("coach : compris")
        fermer()
    }

    private func choisir(_ choix: String) {
        guard !choisi else { return }
        choisi = true
        boutonAnnuler.isEnabled = false
        boutonContinuer.isEnabled = false
        boutonAnnuler.keyEquivalent = ""
        journal("choix du salarié : \(choix)")
        surChoix?(choix)
    }

    /// Le coach, après « Annuler » : trois lignes au plus, puis « Compris ».
    func montrerCoach(_ fiche: Coach.Fiche) {
        let w = Self.interieur
        let titre = NSStackView(views: [
            Gabarit.icone("checkmark.circle.fill", taille: 16, couleurs: [.white, Teinte.cyanFonce]),
            Gabarit.etiquette("C'est annulé.", taille: 15, graisse: .semibold, couleur: Teinte.encre),
        ])
        titre.orientation = .horizontal
        titre.alignment = .centerY
        titre.spacing = 8
        let piege = Gabarit.ligneLibellee("Le piège", fiche.piege, largeur: w)
        let repere = Gabarit.ligneLibellee("La prochaine fois", fiche.repere, largeur: w)
        let bouton = BoutonDedale(titre: "Compris", style: .protege, cible: self, action: #selector(compris))
        bouton.widthAnchor.constraint(equalToConstant: 120).isActive = true
        boutonCompris = bouton
        let basDePage = NSStackView(views: [Gabarit.ressort(), bouton])
        basDePage.orientation = .horizontal
        changerEtat(.coach, cacherMessage: true, vues: [titre, piege, repere, basDePage], espaces: [12, 6, 16])
        panneau.makeFirstResponder(bouton)
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [weak self] in
            guard let self, self.etat == .coach else { return }
            self.clavierActif = true
            bouton.keyEquivalent = "\r"
        }
        // Le coach ne bloque pas la file des alertes : il se ferme seul au bout de 30 s.
        DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
            guard let self, self.etat == .coach else { return }
            self.fermer()
        }
        planifierAuto()
    }

    /// Quatre yeux : la demande part au SOC, la pop-up attend le relecteur ou un analyste.
    func montrerAttente(restant: Int) {
        let texte = Gabarit.paragraphe(Self.texteRestant(restant), taille: 12, couleur: Teinte.discret,
                                       largeur: Self.interieur - 28)
        texteAttente = texte
        let ligne = NSStackView(views: [
            Gabarit.icone("hourglass", taille: 15, couleurs: [Teinte.cyanFonce]),
            Gabarit.etiquette(DemandeQuatreYeux.titreAttente, taille: 14, graisse: .semibold, couleur: Teinte.encre),
        ])
        ligne.orientation = .horizontal
        ligne.alignment = .centerY
        ligne.spacing = 8
        let decale = NSStackView(views: [texte])
        decale.edgeInsets = NSEdgeInsets(top: 0, left: 28, bottom: 0, right: 0)
        changerEtat(.attente, cacherMessage: false, vues: [ligne, decale], espaces: [2])
    }

    func majAttente(restant: Int) {
        texteAttente?.stringValue = Self.texteRestant(restant)
    }

    private static func texteRestant(_ s: Int) -> String {
        DemandeQuatreYeux.texteAttente(restant: s)
    }

    /// Issue des quatre yeux (« Relu par Dédale en 1,8 s : refusé. » et le motif), puis fermeture.
    func montrerIssue(_ issue: DemandeQuatreYeux.Issue) {
        let accorde = issue == .accorde
        let relecture = DemandeQuatreYeux.relecture(pour: avertissement.id)
        let sousTitre = DemandeQuatreYeux.texteIssue(issue, relecture: relecture)
        montrerFin(symbole: accorde ? "checkmark.circle.fill" : "xmark.circle.fill",
                   couleur: accorde ? Teinte.cyanFonce : Teinte.rouge,
                   titre: accorde ? "Accordé" : "Refusé", sousTitre: sousTitre,
                   capture: accorde ? "accorde" : (issue == .expire ? "expire" : "refuse"),
                   duree: relecture == nil ? 3.5 : 7)
    }

    /// Montre l'issue d'un « Continuer » ordinaire, puis ferme la pop-up.
    func confirmer(remonte: Bool) {
        montrerFin(symbole: "exclamationmark.triangle.fill", couleur: Teinte.rouge, titre: nil,
                   sousTitre: remonte ? "Vous avez continué. L'équipe sécurité est prévenue."
                                      : "Vous avez continué. La SOC est injoignable, rien n'a été signalé.",
                   capture: "continuer", duree: 2.4)
    }

    private func montrerFin(symbole: String, couleur: NSColor, titre: String?, sousTitre: String,
                            capture: String, duree: Double) {
        let w = Self.interieur - 28
        let textes = NSStackView()
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 2
        if let titre {
            textes.addArrangedSubview(Gabarit.etiquette(titre, taille: 15, graisse: .semibold, couleur: Teinte.encre))
        }
        textes.addArrangedSubview(Gabarit.paragraphe(sousTitre, taille: titre == nil ? 13 : 12,
                                                     graisse: titre == nil ? .medium : .regular,
                                                     couleur: titre == nil ? Teinte.encre : Teinte.texte, largeur: w))
        let ligne = NSStackView(views: [Gabarit.icone(symbole, taille: 16, couleurs: [.white, couleur]), textes])
        ligne.orientation = .horizontal
        ligne.alignment = titre == nil ? .centerY : .top
        ligne.spacing = 8
        changerEtat(.fin, cacherMessage: false, vues: [ligne], espaces: [], capture: capture)
        DispatchQueue.main.asyncAfter(deadline: .now() + duree) { [weak self] in self?.fermer() }
    }

    private func changerEtat(_ nouvel: Etat, cacherMessage: Bool, vues: [NSView], espaces: [CGFloat],
                             capture: String? = nil) {
        etat = nouvel
        clavierActif = false
        choixVues.forEach { $0.isHidden = true }
        if cacherMessage {
            // Le coach remplace tout sauf l'en-tête.
            for v in pile.arrangedSubviews.dropFirst() where v !== zoneFin { v.isHidden = true }
        }
        zoneFin.arrangedSubviews.forEach { $0.removeFromSuperview() }
        for (i, v) in vues.enumerated() {
            zoneFin.addArrangedSubview(v)
            v.widthAnchor.constraint(equalToConstant: Self.interieur).isActive = true
            if i < espaces.count { zoneFin.setCustomSpacing(espaces[i], after: v) }
        }
        zoneFin.isHidden = false
        ajusterTaille(garderLeHaut: true)
        capturer("-" + (capture ?? "\(nouvel)"))
    }

    func fermer() {
        guard !fermee else { return }
        fermee = true
        NSAnimationContext.runAnimationGroup { ctx in
            ctx.duration = 0.2
            panneau.animator().alphaValue = 0
        }
        // Pas de completionHandler : il ne vient pas toujours quand la fermeture part d'un clic
        // (performClick). Un délai fixe libère la file à coup sûr.
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
        } else if let ecran = NSScreen.main?.visibleFrame {
            cadre.origin.x = ecran.midX - taille.width / 2
            cadre.origin.y = ecran.minY + ecran.height * 0.62 - taille.height / 2
        }
        cadre.size = taille
        panneau.setFrame(cadre, display: true)
        panneau.invalidateShadow()
    }

    // MARK: Test : captures et clics automatiques

    /// DEDALE_CAPTURE=<dossier> : l'application écrit un PNG de sa propre pop-up (aucun droit
    /// d'enregistrement d'écran nécessaire, elle ne lit que sa fenêtre).
    private func capturer(_ suffixe: String) {
        Gabarit.capturer(racine, nom: avertissement.prefixeCapture + suffixe)
    }

    /// Démo filmée sans souris : DEDALE_CLIC_AUTO liste des boutons à presser, dans l'ordre,
    /// séparés par des virgules (`voir`, `annuler`, `continuer`, `compris`). Chaque clic passe
    /// par le vrai bouton (performClick) après DEDALE_CLIC_DELAI secondes. Une étape qui ne
    /// s'applique pas à l'état courant est sautée.
    private func planifierAuto() {
        let env = ProcessInfo.processInfo.environment
        let delai = Double(env["DEDALE_CLIC_DELAI"] ?? "") ?? 2
        while let etape = etapesAuto.first {
            let bouton: NSButton?
            switch (etape, etat) {
            case ("voir", .choix): bouton = boutonVoir
            case ("annuler", .choix): bouton = boutonAnnuler
            case ("continuer", .choix): bouton = boutonContinuer
            case ("compris", .coach): bouton = boutonCompris
            case ("compris", _): bouton = nil; if etat == .choix { return }
            default: bouton = nil
            }
            etapesAuto.removeFirst()
            guard let bouton else { continue }
            let etatPrevu = etat
            DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in
                guard let self, self.etat == etatPrevu, !self.fermee else { return }
                journal("clic automatique (test) sur « \(bouton.title) »")
                bouton.performClick(nil)
                if etape == "voir" { self.planifierAuto() }
            }
            return
        }
    }
}
