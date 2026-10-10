import AppKit

/// Application de barre de menus : icône discrète, état du SOC, file des alertes.
final class AppDelegue: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private static let fileMax = 10

    private var element: NSStatusItem!
    private let menu = NSMenu()
    private let ligneSoc = NSMenuItem(title: "Recherche du SOC…", action: nil, keyEquivalent: "")
    private let ligneEcoute = NSMenuItem(title: "Alertes locales : démarrage…", action: nil, keyEquivalent: "")

    private let backend = Backend()
    private let serveur = ServeurLocal()
    private var file: [Avertissement] = []
    private var fenetre: FenetreAlerte?
    private var socConnecte: Bool?
    private var ecouteOk = false
    private var minuteur: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if let id = Bundle.main.bundleIdentifier,
           NSRunningApplication.runningApplications(withBundleIdentifier: id).count > 1 {
            journal("Dédale tourne déjà, cette instance s'arrête")
            NSApp.terminate(nil)
            return
        }

        element = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        element.button?.toolTip = "Dédale"
        majIcone()

        menu.autoenablesItems = false
        menu.delegate = self
        ligneSoc.isEnabled = false
        ligneEcoute.isEnabled = false
        menu.addItem(ligneSoc)
        menu.addItem(ligneEcoute)
        menu.addItem(.separator())
        let tester = NSMenuItem(title: "Tester une alerte", action: #selector(testerAlerte), keyEquivalent: "t")
        tester.target = self
        menu.addItem(tester)
        menu.addItem(.separator())
        let quitter = NSMenuItem(title: "Quitter", action: #selector(quitter), keyEquivalent: "q")
        quitter.target = self
        menu.addItem(quitter)
        element.menu = menu

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
        }
        serveur.demarrer()

        sonder()
        minuteur = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in self?.sonder() }
        journal("Dédale démarré, backend \(backend.base.absoluteString)")
    }

    func menuWillOpen(_ menu: NSMenu) { sonder() }

    // MARK: SOC

    private func sonder() {
        backend.sonder { [weak self] ok in self?.majSoc(ok) }
    }

    private func majSoc(_ ok: Bool) {
        if socConnecte != ok { journal(ok ? "SOC connecté" : "SOC hors ligne") }
        socConnecte = ok
        ligneSoc.title = ok ? "Connecté au SOC" : "Hors ligne"
        ligneSoc.image = Self.pastille(ok ? Teinte.cyan : NSColor(hex: 0x9AA1AE))
        majIcone()
    }

    private func majIcone() {
        let symbole = socConnecte == false ? "shield.slash" : "shield.lefthalf.filled"
        let image = NSImage(systemSymbolName: symbole, accessibilityDescription: "Dédale")
        image?.isTemplate = true
        element.button?.image = image
    }

    private func etat() -> [String: Any] {
        [
            "application": "dedale-mac",
            "version": "0.1",
            "soc": socConnecte.map { $0 ? "connecte" : "hors_ligne" } ?? "inconnu",
            "alerte_affichee": fenetre != nil,
            "en_file": file.count,
        ]
    }

    // MARK: Alertes

    private func recevoir(_ a: Avertissement) -> ReponseHTTP {
        guard file.count < Self.fileMax else {
            return .erreur(429, "trop d'alertes en attente")
        }
        file.append(a)
        journal("alerte reçue : \(a.categorie) (session \(a.sessionId))")
        let enFile = fenetre != nil
        afficherSuivante()
        return ReponseHTTP(code: 202, corps: [
            "statut": enFile ? "en_file" : "affichee",
            "id": a.id,
            "session_id": a.sessionId,
        ])
    }

    /// Une seule pop-up à la fois : la suivante attend le choix de la précédente.
    private func afficherSuivante() {
        guard fenetre == nil, !file.isEmpty else { return }
        let a = file.removeFirst()
        let f = FenetreAlerte(a)
        f.surChoix = { [weak self, weak f] choix in
            guard let self else { return }
            self.backend.envoyerChoix(a, choix: choix) { remonte in
                if remonte { self.majSoc(true) } else { self.sonder() }
                f?.confirmer(choix: choix, remonte: remonte)
            }
        }
        f.surFermeture = { [weak self] in
            self?.fenetre = nil
            self?.afficherSuivante()
        }
        fenetre = f
        f.montrer()
    }

    @objc private func testerAlerte() {
        _ = recevoir(.exemple())
    }

    @objc private func quitter() {
        NSApp.terminate(nil)
    }

    private static func pastille(_ couleur: NSColor) -> NSImage {
        NSImage(size: NSSize(width: 8, height: 8), flipped: false) { r in
            couleur.setFill()
            NSBezierPath(ovalIn: r).fill()
            return true
        }
    }
}
