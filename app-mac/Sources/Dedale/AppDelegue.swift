import AppKit

/// Application de barre de menus : une icône d'état (« Protégé »), le compteur de la semaine,
/// l'état de chaque module (SOC, mails, téléchargements, agents IA), le signalement d'un mail,
/// les fichiers mis de côté, le panneau de transparence et la file des pop-ups.
final class AppDelegue: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private static let fileMax = 10
    private static let mailsAuMenu = 8
    /// La remise en place automatique (test) ne joue qu'une fois.
    fileprivate static var remiseAutoFaite = false

    private var element: NSStatusItem!
    private let menu = NSMenu()
    private let ligneEtat = NSMenuItem(title: "Protégé", action: nil, keyEquivalent: "")
    private let ligneSoc = NSMenuItem(title: "Recherche de la SOC…", action: nil, keyEquivalent: "")
    private let ligneTelechargements = NSMenuItem(title: "Téléchargements : démarrage…", action: nil, keyEquivalent: "")
    private let ligneAgents = NSMenuItem(title: "Agents IA : analyse…", action: nil, keyEquivalent: "")
    private let entreeMisDeCote = NSMenuItem(title: "Mis de côté", action: nil, keyEquivalent: "")
    private let sousMenuMisDeCote = NSMenu()
    private let ligneBoite = NSMenuItem(title: "Recherche de la boîte de démo…", action: nil, keyEquivalent: "")
    private let ligneEcoute = NSMenuItem(title: "Alertes locales : démarrage…", action: nil, keyEquivalent: "")
    private let ligneCompteur = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    private let entreeSignaler = NSMenuItem(title: "Signaler un mail suspect…", action: nil, keyEquivalent: "")
    private let sousMenuSignaler = NSMenu()

    private let backend = Backend()
    private let messagerie = Messagerie()
    private lazy var flux = FluxVerdicts(base: messagerie.base)
    private let serveur = ServeurLocal()
    private let compteur = Compteur()
    private var file: [Avertissement] = []
    private var fenetre: FenetreAlerte?
    private var apercu: FenetreApercu?
    private var demande: DemandeQuatreYeux?
    private var socConnecte: Bool?
    private var ecouteOk = false
    private var minuteurs: [Timer] = []
    /// Sites louches dans Safari et Chrome (SitesVeille.swift).
    private let sites = SitesVeille()

    // Poste : téléchargements, agents IA, transparence
    private let surveillance = SurveillanceTelechargements()
    private let miseDeCote = MiseDeCote()
    private lazy var agentsPoste = AgentsDuPoste(backend: backend.base)
    private var fileTelechargements: [FichierSignale] = []
    private var fenetreTelechargement: FenetreTelechargement?
    private var transparence: FenetreTransparence?
    private var fenetreAgents: FenetreAgents?
    private var etatTelechargements: SurveillanceTelechargements.Etat = .arretee
    /// Après une remise en route du module Mails, les mails déjà là ne rejouent pas d'alerte.
    private var mailsAIgnorer = false

    // Boîte de démo
    private var boiteEnLigne: Bool?
    private var premierReleve = true
    private var releveEnCours = false
    /// Mails déjà montrés en alerte (ou déjà là au démarrage, voir DEDALE_MAILS_AU_DEMARRAGE).
    private var mailsVus: Set<String> = []
    private var verdicts: [String: VerdictMail] = [:]
    private var mailsRecents: [MailResume] = []
    private var mailsSignales: Set<String> = []
    private var signalementAutoFait = false
    private var captureMenuPrevue: DispatchWorkItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let id = Bundle.main.bundleIdentifier,
           NSRunningApplication.runningApplications(withBundleIdentifier: id).count > 1 {
            journal("Dédale tourne déjà, cette instance s'arrête")
            NSApp.terminate(nil)
            return
        }

        element = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        element.button?.toolTip = "Dédale"

        menu.autoenablesItems = false
        menu.delegate = self
        // La console n'a qu'un thème clair : le menu aussi, même en mode sombre.
        for m in [menu, sousMenuSignaler, sousMenuMisDeCote] { m.appearance = Apparence.claire }
        for ligne in [ligneEtat, ligneSoc, ligneBoite, ligneTelechargements, ligneEcoute, ligneCompteur] {
            ligne.isEnabled = false
        }
        for ligne in [ligneBoite, ligneTelechargements, ligneAgents] { ligne.image = Self.pastille(Teinte.gris) }
        ligneAgents.target = self
        ligneAgents.action = #selector(ouvrirAgents)
        // En tête : l'état d'ensemble et le compteur de la semaine.
        menu.addItem(ligneEtat)
        menu.addItem(ligneCompteur)
        menu.addItem(.separator())
        menu.addItem(ligneSoc)
        menu.addItem(ligneBoite)
        menu.addItem(ligneTelechargements)
        menu.addItem(ligneAgents)
        menu.addItem(ligneEcoute)
        menu.addItem(.separator())
        sousMenuSignaler.autoenablesItems = false
        entreeSignaler.submenu = sousMenuSignaler
        menu.addItem(entreeSignaler)
        sousMenuMisDeCote.autoenablesItems = false
        entreeMisDeCote.submenu = sousMenuMisDeCote
        menu.addItem(entreeMisDeCote)
        let regarde = NSMenuItem(title: "Ce que Dédale regarde sur ce poste…", action: #selector(ouvrirTransparence),
                                 keyEquivalent: "")
        regarde.target = self
        menu.addItem(regarde)
        let tester = NSMenuItem(title: "Tester une alerte", action: #selector(testerAlerte), keyEquivalent: "t")
        tester.target = self
        menu.addItem(tester)
        menu.addItem(.separator())
        let quitter = NSMenuItem(title: "Quitter", action: #selector(quitter), keyEquivalent: "q")
        quitter.target = self
        menu.addItem(quitter)
        element.menu = menu
        majCompteur()
        majSousMenu()
        majMisDeCote()
        majEtat()

        serveur.surAvertissement = { [weak self] a in
            self?.recevoir(a) ?? .erreur(503, "application pas prête")
        }
        serveur.surEtat = { [weak self] in self?.etat() ?? [:] }
        serveur.surEcoute = { [weak self] ok in
            guard let self else { return }
            self.ecouteOk = ok
            self.ligneEcoute.title = ok
                ? "Alertes locales sur le port \(ServeurLocal.port)"
                : "Port \(ServeurLocal.port) occupé, alertes locales coupées"
            self.prevoirCaptureMenu()
        }
        serveur.demarrer()

        sonder()
        releverBoite()
        minuteurs = [
            Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.sonder() },
            Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.releverBoite() },
        ]
        minuteurs.forEach { RunLoop.main.add($0, forMode: .common) }
        demarrerPoste()
        sites.surEvite = { [weak self] in self?.compteur.ajouter(); self?.majCompteur() }
        sites.demarrer(menu: menu, apres: ligneEcoute)
        journal("Dédale démarré, backend \(backend.base.absoluteString), boîte de démo \(messagerie.base.absoluteString), "
                + "poste \(IdentitePoste.identifiant)")
    }

    func menuWillOpen(_ menu: NSMenu) {
        sonder()
        majCompteur()
    }

    // MARK: SOC

    private func sonder() {
        backend.sonder { [weak self] ok in self?.majSoc(ok) }
    }

    private func majSoc(_ ok: Bool) {
        if socConnecte != ok { journal(ok ? "SOC connecté" : "SOC hors ligne") }
        let change = socConnecte != ok
        socConnecte = ok
        ligneSoc.title = ok ? "Connecté à la SOC" : "SOC hors ligne"
        ligneSoc.image = Self.pastille(ok ? Teinte.ok : Teinte.gris)
        majEtat()
        if change { prevoirCaptureMenu() }
    }

    /// Une seule icône dans la barre de menus, et en tête du menu l'état d'ensemble :
    /// « Protégé » quand tous les modules tournent et que la SOC répond. Couleurs de la
    /// console : vert quand tout est réglé, orange quand quelque chose attend une action.
    private func majEtat() {
        let actifs = ReglagesModules.partage.actifs.count
        let total = ModulePoste.allCases.count
        let titre: String
        let symbole: String
        let couleur: NSColor
        if actifs == 0 {
            (titre, symbole, couleur) = ("Protection en pause", "shield.slash", Teinte.gris)
        } else if actifs < total {
            (titre, symbole, couleur) = ("Protection partielle (\(actifs) modules sur \(total))", "exclamationmark.shield", Teinte.orange)
        } else if socConnecte == false {
            (titre, symbole, couleur) = ("Protégé, SOC hors ligne", "exclamationmark.shield", Teinte.orange)
        } else {
            (titre, symbole, couleur) = ("Protégé", "checkmark.shield", Teinte.ok)
        }
        ligneEtat.attributedTitle = NSAttributedString(string: titre, attributes: [
            .font: NSFont.systemFont(ofSize: Taille.bouton, weight: .semibold), .foregroundColor: Teinte.encre])
        ligneEtat.image = Gabarit.symbole(symbole + ".fill", taille: 13, couleurs: [couleur])
        // Le logo en gabarit dans la barre de menus ; le bouclier de l'état reste en repli.
        let image = Logo.barreDeMenus ?? NSImage(systemSymbolName: symbole, accessibilityDescription: "Dédale : \(titre)")
        image?.isTemplate = true
        element?.button?.image = image
        // Protection en pause : le logo s'estompe, comme un élément désactivé.
        element?.button?.appearsDisabled = actifs == 0
        element?.button?.toolTip = "Dédale : \(titre)"
    }

    private func etat() -> [String: Any] {
        [
            "application": "dedale-mac",
            "version": "0.2",
            "soc": socConnecte.map { $0 ? "connecte" : "hors_ligne" } ?? "inconnu",
            "boite_demo": boiteEnLigne.map { $0 ? "en_ligne" : "hors_ligne" } ?? "inconnu",
            "alerte_affichee": fenetre != nil,
            "en_file": file.count,
            "quatre_yeux_en_attente": demande != nil,
            "pieges_evites_semaine": compteur.cetteSemaine(),
            "sites": sites.etat(),
            "poste": IdentitePoste.identifiant,
            "modules": Dictionary(uniqueKeysWithValues: ModulePoste.allCases.map {
                ($0.rawValue, ReglagesModules.partage.actif($0))
            }),
            "telechargements": [
                "etat": "\(etatTelechargements)",
                "en_file": fileTelechargements.count,
                "pop_up_affichee": fenetreTelechargement != nil,
                "mis_de_cote": miseDeCote.entrees.count,
            ] as [String: Any],
            "agents_ia": [
                "source": agentsPoste.source.code,
                "serveurs": agentsPoste.resultat?.serveurs.count ?? 0,
                "risques": agentsPoste.resultat?.risques ?? 0,
                "envoye": agentsPoste.envoiOk ?? false,
            ] as [String: Any],
        ]
    }

    // MARK: Boîte de démo

    /// Relève les verdicts de l'analyseur toutes les 3 s. Chaque nouveau mail jugé frauduleux
    /// devient une alerte. Les mails déjà là au premier relevé ne sont pas rejoués, sauf avec
    /// DEDALE_MAILS_AU_DEMARRAGE=alerter.
    private func releverBoite() {
        guard !releveEnCours, ReglagesModules.partage.actif(.mails) else { return }
        releveEnCours = true
        messagerie.verdicts { [weak self] liste in
            guard let self else { return }
            guard let liste else {
                self.releveEnCours = false
                self.majBoite(enLigne: false)
                return
            }
            if self.premierReleve {
                self.premierReleve = false
                let fraudes = liste.filter(\.frauduleux)
                let rejouer = ProcessInfo.processInfo.environment["DEDALE_MAILS_AU_DEMARRAGE"] == "alerter"
                if !rejouer { self.mailsVus.formUnion(fraudes.map(\.mail.id)) }
                journal("boîte de démo : \(liste.count) verdict(s), \(fraudes.count) frauduleux, "
                        + (rejouer ? "rejoués" : "déjà là, pas d'alerte"))
                // Le flux ne s'ouvre qu'après ce premier relevé : il n'apporte que du neuf.
                self.flux.surVerdict = { [weak self] v in
                    guard ReglagesModules.partage.actif(.mails) else { return }
                    self?.traiter([v], source: "flux")
                }
                self.flux.demarrer()
            }
            if self.mailsAIgnorer {
                // Module Mails remis en route : ce qui est arrivé pendant la coupure ne rejoue rien.
                self.mailsAIgnorer = false
                self.mailsVus.formUnion(liste.filter(\.frauduleux).map(\.mail.id))
            }
            self.traiter(liste, source: "relevé")
            self.messagerie.mails { [weak self] mails in
                guard let self else { return }
                self.releveEnCours = false
                let recents = mails ?? liste.map(\.mail)
                self.majBoite(enLigne: true, mails: recents)
            }
        }
    }

    /// Chaque mail jugé frauduleux et pas encore montré devient une alerte (une seule fois).
    private func traiter(_ liste: [VerdictMail], source: String) {
        for v in liste { verdicts[v.mail.id] = v }
        for v in liste where v.frauduleux && !mailsVus.contains(v.mail.id) {
            if recevoir(.depuisVerdict(v)).code == 202 {
                mailsVus.insert(v.mail.id)
                journal("verdict frauduleux (\(source)) : mail \(v.mail.id)")
            }
        }
    }

    private func majBoite(enLigne: Bool, mails: [MailResume]? = nil) {
        if boiteEnLigne != enLigne { journal(enLigne ? "boîte de démo en ligne" : "boîte de démo hors ligne") }
        var change = boiteEnLigne != enLigne
        boiteEnLigne = enLigne
        if let mails {
            let tries = Self.trier(mails)
            change = change || tries != mailsRecents
            mailsRecents = tries
        }
        let n = mailsRecents.count
        ligneBoite.title = enLigne ? "Boîte de démo : \(n) mail\(n > 1 ? "s" : "")" : "Boîte de démo hors ligne"
        ligneBoite.image = Self.pastille(enLigne ? Teinte.ok : Teinte.gris)
        if change {
            majSousMenu()
            prevoirCaptureMenu()
        }
    }

    /// Plus récent d'abord quand chaque mail porte une date ISO, sinon l'ordre de la boîte.
    private static func trier(_ mails: [MailResume]) -> [MailResume] {
        guard mails.allSatisfy({ $0.date != nil }) else { return mails }
        return mails.enumerated().sorted { a, b in
            a.element.date! != b.element.date! ? a.element.date! > b.element.date! : a.offset < b.offset
        }.map(\.element)
    }

    // MARK: Signaler un mail suspect

    private func majSousMenu() {
        sousMenuSignaler.removeAllItems()
        guard ReglagesModules.partage.actif(.mails) else {
            let l = NSMenuItem(title: "Module Mails coupé", action: nil, keyEquivalent: "")
            l.isEnabled = false
            sousMenuSignaler.addItem(l)
            return
        }
        guard boiteEnLigne == true else {
            let l = NSMenuItem(title: boiteEnLigne == nil ? "Recherche de la boîte de démo…" : "Boîte de démo hors ligne",
                               action: nil, keyEquivalent: "")
            l.isEnabled = false
            sousMenuSignaler.addItem(l)
            return
        }
        let titre = NSMenuItem(title: "Derniers mails de la boîte de démo", action: nil, keyEquivalent: "")
        titre.isEnabled = false
        sousMenuSignaler.addItem(titre)
        if mailsRecents.isEmpty {
            let vide = NSMenuItem(title: "Aucun mail pour l'instant", action: nil, keyEquivalent: "")
            vide.isEnabled = false
            sousMenuSignaler.addItem(vide)
            return
        }
        for m in mailsRecents.prefix(Self.mailsAuMenu) {
            let item = NSMenuItem(title: m.objet, action: #selector(signaler(_:)), keyEquivalent: "")
            item.target = self
            item.representedObject = m.id
            item.state = mailsSignales.contains(m.id) ? .on : .off
            let objet = Messagerie.desarmerLigne(m.objet, max: 46)
            let titre = NSMutableAttributedString(string: objet, attributes: [
                .font: NSFont.menuFont(ofSize: Taille.libelle), .foregroundColor: Teinte.encre])
            if !m.adresse.isEmpty {
                titre.append(NSAttributedString(string: "   " + Messagerie.desarmerLigne(m.adresse, max: 40), attributes: [
                    .font: NSFont.menuFont(ofSize: Taille.puce - 1), .foregroundColor: Teinte.discret]))
            }
            item.attributedTitle = titre
            sousMenuSignaler.addItem(item)
        }
        signalementAutomatique()
    }

    @objc private func signaler(_ item: NSMenuItem) {
        guard let id = item.representedObject as? String,
              let m = mailsRecents.first(where: { $0.id == id }) else { return }
        journal("signalement demandé : mail \(id)")
        messagerie.mail(id) { [weak self] complet in
            guard let self else { return }
            self.backend.envoyerSignalement(m, complet: complet, verdict: self.verdicts[id]) { [weak self] ok in
                guard let self else { return }
                if ok {
                    self.mailsSignales.insert(id)
                    self.majSoc(true)
                    self.majSousMenu()
                    self.prevoirCaptureMenu()
                } else {
                    self.sonder()
                }
                Bulle(ok ? "Merci, la SOC est prévenue." : "La SOC est injoignable. Réessayez dans un moment.", ok: ok)
                    .montrer(capture: "signalement")
            }
        }
    }

    /// Test : DEDALE_SIGNALER_AUTO=<id du mail> (ou `premier`) déclenche une fois l'entrée du
    /// sous-menu, par le même chemin qu'un clic.
    private func signalementAutomatique() {
        guard !signalementAutoFait, let cible = ProcessInfo.processInfo.environment["DEDALE_SIGNALER_AUTO"],
              !cible.isEmpty else { return }
        guard let index = sousMenuSignaler.items.firstIndex(where: {
            guard let id = $0.representedObject as? String else { return false }
            return cible == "premier" || id == cible
        }) else { return }
        signalementAutoFait = true
        let delai = Double(ProcessInfo.processInfo.environment["DEDALE_CLIC_DELAI"] ?? "") ?? 2
        DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in
            guard let self, index < self.sousMenuSignaler.items.count else { return }
            journal("signalement automatique (test) : « \(self.sousMenuSignaler.items[index].title) »")
            self.sousMenuSignaler.performActionForItem(at: index)
        }
    }

    // MARK: Compteur

    private func majCompteur() {
        let n = compteur.cetteSemaine()
        ligneCompteur.attributedTitle = NSAttributedString(string: Compteur.libelle(n), attributes: [
            .font: NSFont.menuFont(ofSize: Taille.note), .foregroundColor: Teinte.discret])
        ligneCompteur.image = NSImage(systemSymbolName: "checkmark.shield", accessibilityDescription: nil)
        ligneCompteur.image?.isTemplate = true
    }

    // MARK: Alertes

    private func recevoir(_ a: Avertissement) -> ReponseHTTP {
        guard file.count < Self.fileMax else {
            return .erreur(429, "trop d'alertes en attente")
        }
        file.append(a)
        journal("alerte reçue : \(a.categorie) (session \(a.sessionId))")
        let enFile = fenetre != nil || fenetreTelechargement != nil
        afficherSuivante()
        return ReponseHTTP(code: 202, corps: [
            "statut": enFile ? "en_file" : "affichee",
            "id": a.id,
            "session_id": a.sessionId,
        ])
    }

    /// Une seule pop-up à la fois, alertes et téléchargements confondus : la suivante attend
    /// la fin de la précédente. Les alertes passent d'abord.
    private func afficherSuivante() {
        guard fenetre == nil, fenetreTelechargement == nil else { return }
        if !file.isEmpty {
            afficherAlerte()
        } else if !fileTelechargements.isEmpty {
            montrerTelechargement(fileTelechargements.removeFirst())
        }
    }

    private func afficherAlerte() {
        let a = file.removeFirst()
        let f = FenetreAlerte(a)
        f.surChoix = { [weak self, weak f] choix in
            guard let self, let f else { return }
            self.choix(choix, avertissement: a, fenetre: f)
        }
        f.surVoirMail = { [weak self, weak f] in
            guard let self, let m = a.mail else { return }
            self.ouvrirApercu(m, pres: f?.cadre)
        }
        f.surFermeture = { [weak self] in
            self?.fenetre = nil
            self?.afficherSuivante()
        }
        fenetre = f
        // Geste critique lancé sur le poste : Dédale vérifie d'abord, sans question au salarié.
        // La pop-up ne s'ouvre que s'il y a un signal de risque (QuatreYeux.swift).
        if DemandeQuatreYeux.verifieDAbord(a) {
            let d = DemandeQuatreYeux(a, backend: backend)
            demande = d
            d.verifier(fenetre: f) { [weak self] in self?.demande = nil }
            return
        }
        f.montrer()
    }

    private func choix(_ choix: String, avertissement a: Avertissement, fenetre f: FenetreAlerte) {
        if choix == "annuler" {
            // Bon réflexe : un piège évité de plus, et le coach tout de suite.
            compteur.ajouter()
            majCompteur()
            prevoirCaptureMenu()
            f.montrerCoach(Coach.fiche(pour: a))
            backend.envoyerChoix(a, choix: "annuler") { [weak self] ok in
                if ok { self?.majSoc(true) } else { self?.sonder() }
            }
        } else if a.quatreYeux {
            let d = DemandeQuatreYeux(a, backend: backend)
            demande = d
            f.montrerAttente(restant: d.total)
            d.lancer(tic: { [weak f] restant in
                f?.majAttente(restant: restant)
            }, fin: { [weak self, weak f] issue in
                guard let self else { return }
                self.demande = nil
                if issue == .injoignable { self.sonder() } else { self.majSoc(true) }
                f?.montrerIssue(issue)
            })
        } else {
            backend.envoyerChoix(a, choix: "continuer") { [weak self, weak f] remonte in
                if remonte { self?.majSoc(true) } else { self?.sonder() }
                f?.confirmer(remonte: remonte)
            }
        }
    }

    private func ouvrirApercu(_ m: MailResume, pres voisin: NSRect?) {
        apercu?.fermer()
        let p = FenetreApercu(m)
        p.surFermeture = { [weak self, weak p] in
            if self?.apercu === p { self?.apercu = nil }
        }
        apercu = p
        p.montrer(pres: voisin)
        messagerie.mail(m.id) { [weak p] complet in p?.afficher(complet) }
    }

    @objc private func testerAlerte() {
        _ = recevoir(.exemple())
    }

    @objc private func quitter() {
        NSApp.terminate(nil)
    }

    // MARK: Capture du menu (test)

    /// Avec DEDALE_CAPTURE, l'app écrit un rendu de son menu et du sous-menu « Signaler »
    /// à chaque changement d'état (menu.png, menu-signaler.png).
    private func prevoirCaptureMenu() {
        guard let dossier = Gabarit.dossierCapture else { return }
        captureMenuPrevue?.cancel()
        let travail = DispatchWorkItem { [weak self] in
            guard let self else { return }
            Capture.ecrireMenu(self.menu, vers: dossier.appendingPathComponent("menu.png"))
            Capture.ecrireMenu(self.sousMenuSignaler, vers: dossier.appendingPathComponent("menu-signaler.png"))
            if !self.entreeMisDeCote.isHidden {
                Capture.ecrireMenu(self.sousMenuMisDeCote, vers: dossier.appendingPathComponent("menu-mis-de-cote.png"))
            }
            journal("capture du menu écrite : \(dossier.path)/menu.png")
        }
        captureMenuPrevue = travail
        DispatchQueue.main.asyncAfter(deadline: .now() + 1, execute: travail)
    }

    private static func pastille(_ couleur: NSColor) -> NSImage {
        NSImage(size: NSSize(width: 8, height: 8), flipped: false) { r in
            couleur.setFill()
            NSBezierPath(ovalIn: r).fill()
            return true
        }
    }
}

// MARK: - Poste : téléchargements, agents IA, transparence


extension AppDelegue {
    fileprivate func demarrerPoste() {
        surveillance.surSignalement = { [weak self] f in self?.recevoirTelechargement(f) }
        surveillance.surEtat = { [weak self] e in
            self?.etatTelechargements = e
            self?.majTelechargements()
        }
        agentsPoste.surMaj = { [weak self] in self?.majAgents() }
        NotificationCenter.default.addObserver(forName: ReglagesModules.changement, object: nil, queue: .main) {
            [weak self] note in self?.appliquerModules(change: note.object as? ModulePoste)
        }
        appliquerModules(change: nil)
        ouvertureAutomatique()
    }

    /// Met chaque module en route ou à l'arrêt selon son interrupteur.
    fileprivate func appliquerModules(change: ModulePoste?) {
        let r = ReglagesModules.partage
        if change == nil || change == .telechargements {
            if r.actif(.telechargements) { surveillance.demarrer() } else {
                surveillance.arreter()
                fileTelechargements.removeAll()
            }
        }
        if change == nil || change == .agents {
            if r.actif(.agents) { agentsPoste.demarrer() } else { agentsPoste.arreter() }
        }
        if change == .mails {
            if r.actif(.mails) {
                mailsAIgnorer = true
                releverBoite()
            }
            ligneBoite.title = r.actif(.mails) ? "Boîte de démo : relevé…" : "Mails : coupé"
            ligneBoite.image = Self.pastille(Teinte.gris)
            majSousMenu()
        }
        majTelechargements()
        majAgents()
        majEtat()
        transparence?.rafraichir()
        prevoirCaptureMenu()
    }

    fileprivate func majTelechargements() {
        let titre: String
        let teinte: NSColor
        if !ReglagesModules.partage.actif(.telechargements) {
            (titre, teinte) = ("Téléchargements : coupé", Teinte.gris)
        } else {
            switch etatTelechargements {
            case .active: (titre, teinte) = ("Téléchargements surveillés", Teinte.ok)
            case .accesRefuse: (titre, teinte) = ("Téléchargements : accès à autoriser", Teinte.orange)
            case .dossierAbsent: (titre, teinte) = ("Téléchargements : dossier introuvable", Teinte.orange)
            case .arretee: (titre, teinte) = ("Téléchargements : démarrage…", Teinte.gris)
            }
        }
        ligneTelechargements.title = titre
        ligneTelechargements.image = Self.pastille(teinte)
        transparence?.rafraichir()
        prevoirCaptureMenu()
    }

    fileprivate func majAgents() {
        if !ReglagesModules.partage.actif(.agents) {
            ligneAgents.title = "Agents IA : coupé"
            ligneAgents.image = Self.pastille(Teinte.gris)
            ligneAgents.isEnabled = false
        } else if let r = agentsPoste.resultat {
            let n = r.serveurs.count
            ligneAgents.title = "Agents IA : \(n) serveur\(n > 1 ? "s" : "") dont \(r.risques) à risque"
            ligneAgents.image = Self.pastille(r.risques > 0 ? Teinte.rouge : Teinte.ok)
            ligneAgents.isEnabled = true
        } else {
            if case .aucune = agentsPoste.source {
                ligneAgents.title = "Agents IA : aucune configuration lue"
            } else {
                ligneAgents.title = "Agents IA : analyse…"
            }
            ligneAgents.image = Self.pastille(Teinte.gris)
            ligneAgents.isEnabled = false
        }
        fenetreAgents?.rafraichir(agentsPoste)
        transparence?.rafraichir()
        prevoirCaptureMenu()
    }

    // MARK: Téléchargements

    fileprivate func recevoirTelechargement(_ f: FichierSignale) {
        guard ReglagesModules.partage.actif(.telechargements) else { return }
        guard fileTelechargements.count < Self.fileMax else {
            journal("téléchargement à risque ignoré : file pleine")
            return
        }
        fileTelechargements.append(f)
        afficherSuivante()
    }

    fileprivate func montrerTelechargement(_ f: FichierSignale) {
        let w = FenetreTelechargement(f)
        w.surChoix = { [weak self, weak w] choix in
            guard let self else { return }
            var deplace = false
            if choix == "mettre_de_cote" {
                do {
                    _ = try self.miseDeCote.mettreDeCote(f)
                    deplace = true
                    self.compteur.ajouter()
                    self.majCompteur()
                    self.majMisDeCote()
                    self.remiseAutomatique()
                } catch {
                    journal("mise de côté impossible : \(error.localizedDescription)")
                }
            }
            self.backend.envoyerTelechargement(f, choix: choix) { [weak self, weak w] ok in
                if ok { self?.majSoc(true) } else { self?.sonder() }
                w?.montrerIssue(choix: choix, deplace: deplace, remonte: ok)
            }
        }
        w.surFermeture = { [weak self] in
            self?.fenetreTelechargement = nil
            self?.afficherSuivante()
        }
        fenetreTelechargement = w
        w.montrer()
    }

    fileprivate func majMisDeCote() {
        sousMenuMisDeCote.removeAllItems()
        let entrees = miseDeCote.entrees
        entreeMisDeCote.isHidden = entrees.isEmpty
        entreeMisDeCote.title = "Fichiers mis de côté (\(entrees.count))"
        for e in entrees.reversed().prefix(10) {
            let item = NSMenuItem(title: "Remettre « \(e.nom) » à sa place", action: #selector(remettre(_:)),
                                  keyEquivalent: "")
            item.target = self
            item.representedObject = e.id
            sousMenuMisDeCote.addItem(item)
        }
        if let premier = entrees.first {
            sousMenuMisDeCote.addItem(.separator())
            let voir = NSMenuItem(title: "Afficher le dossier dans le Finder", action: #selector(afficherMisDeCote(_:)),
                                  keyEquivalent: "")
            voir.target = self
            voir.representedObject = premier.actuel
            sousMenuMisDeCote.addItem(voir)
        }
        prevoirCaptureMenu()
    }

    @objc fileprivate func remettre(_ item: NSMenuItem) {
        guard let id = item.representedObject as? String,
              let e = miseDeCote.entrees.first(where: { $0.id == id }) else { return }
        surveillance.ignorerProchaineApparition(MiseDeCote.libre(e.origine).lastPathComponent)
        do {
            try miseDeCote.remettre(id)
            journal("fichier remis à sa place (\(id))")
            Bulle("« \(e.nom) » est de retour dans Téléchargements.", ok: true).montrer(capture: "remis-en-place")
        } catch {
            journal("remise en place impossible : \(error.localizedDescription)")
            Bulle("Impossible de remettre le fichier à sa place.", ok: false).montrer()
        }
        majMisDeCote()
    }

    @objc fileprivate func afficherMisDeCote(_ item: NSMenuItem) {
        guard let url = item.representedObject as? URL else { return }
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }

    /// Test : DEDALE_REMETTRE_AUTO=<secondes> remet le dernier fichier mis de côté à sa place,
    /// par le même chemin qu'un clic dans le sous-menu.
    fileprivate func remiseAutomatique() {
        guard !Self.remiseAutoFaite, let brut = ProcessInfo.processInfo.environment["DEDALE_REMETTRE_AUTO"],
              let delai = Double(brut) else { return }
        Self.remiseAutoFaite = true
        DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in
            guard let self, let i = self.sousMenuMisDeCote.items.firstIndex(where: { $0.action == #selector(self.remettre(_:)) })
            else { return }
            journal("remise en place automatique (test)")
            self.sousMenuMisDeCote.performActionForItem(at: i)
        }
    }

    // MARK: Panneaux

    @objc fileprivate func ouvrirTransparence() {
        let t = transparence ?? FenetreTransparence()
        t.etatModule = { [weak self] m in self?.etatModule(m) ?? "" }
        let hote = backend.base.host.map { h in backend.base.port.map { "\(h):\($0)" } ?? h } ?? backend.base.absoluteString
        t.piedDePage = "Poste \(IdentitePoste.identifiant) · SOC \(hote)"
        t.surFermeture = { [weak self] in self?.transparence = nil }
        transparence = t
        t.afficher()
    }

    @objc fileprivate func ouvrirAgents() {
        let f = fenetreAgents ?? FenetreAgents()
        f.surFermeture = { [weak self] in self?.fenetreAgents = nil }
        fenetreAgents = f
        f.afficher(agentsPoste)
    }

    fileprivate func etatModule(_ m: ModulePoste) -> String {
        switch m {
        case .mails:
            guard let enLigne = boiteEnLigne else { return "Recherche de la boîte de démo…" }
            return enLigne ? "Boîte de démo : \(mailsRecents.count) mail\(mailsRecents.count > 1 ? "s" : "")"
                           : "Boîte de démo hors ligne"
        case .sites:
            return "Avertit avant un site sosie"
        case .telechargements:
            switch etatTelechargements {
            case .active: return "\(surveillance.dossierAffiche) surveillé"
            case .accesRefuse: return "Accès à \(surveillance.dossierAffiche) à autoriser"
            case .dossierAbsent: return "\(surveillance.dossierAffiche) introuvable"
            case .arretee: return "Démarrage…"
            }
        case .agents:
            let n = agentsPoste.resultat?.serveurs.count
            return agentsPoste.source.libelle + (n.map { " · \($0) serveur\($0 > 1 ? "s" : "")" } ?? "")
        }
    }

    /// Test et captures : DEDALE_OUVRIR=transparence,agents ouvre ces panneaux l'un après
    /// l'autre au lancement, quatre secondes chacun. DEDALE_BASCULER_AUTO=<module> bascule en
    /// plus l'interrupteur de ce module dans le panneau de transparence.
    fileprivate func ouvertureAutomatique() {
        let panneaux = (ProcessInfo.processInfo.environment["DEDALE_OUVRIR"] ?? "").split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
        for (i, nom) in panneaux.enumerated() {
            let debut = 3.0 + Double(i) * 5
            DispatchQueue.main.asyncAfter(deadline: .now() + debut) { [weak self] in
                guard let self else { return }
                journal("ouverture automatique (test) : \(nom)")
                if nom == "transparence" {
                    self.ouvrirTransparence()
                    // DEDALE_BASCULER_AUTO=agents : bascule ce module par son interrupteur.
                    if let brut = ProcessInfo.processInfo.environment["DEDALE_BASCULER_AUTO"],
                       let m = ModulePoste(rawValue: brut) {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { self.transparence?.basculerParClic(m) }
                    }
                }
                if nom == "agents" { self.ouvrirAgents() }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + debut + 4) { [weak self] in
                if nom == "transparence" { self?.transparence?.fermer() }
                if nom == "agents" { self?.fenetreAgents?.fermer() }
            }
        }
    }
}
