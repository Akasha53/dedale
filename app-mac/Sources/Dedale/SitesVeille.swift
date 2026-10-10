import AppKit

/// Veille des sites louches dans Safari et Chrome.
///
/// Quand l'un des deux est au premier plan, et seulement à ce moment-là, l'app lit l'adresse
/// de l'onglet actif environ chaque seconde (LecteurNavigateurs) et la passe au moteur commun
/// (MoteurSites, mêmes règles que l'extension Chrome). L'analyse reste sur le poste. Une
/// adresse louche ouvre la pop-up habituelle avec « Revenir en arrière » et « Continuer
/// quand même ». Rien ne part tant que le salarié n'a pas continué ; s'il continue, seuls le
/// domaine et la catégorie partent à la SOC, sous la forme de l'extension (CONTRATS.md,
/// contexte « navigation »). Jamais le contenu des pages, jamais l'historique.
///
/// Pas de doublon avec l'extension : dans Chrome, une adresse louche n'alerte qu'au second
/// relevé. Si l'onglet est passé entre-temps sur la page d'avertissement de l'extension,
/// c'est elle qui s'en occupe, y compris quand le salarié continue depuis cette page.
final class SitesVeille {
    /// Appelé à chaque « Revenir en arrière » : un piège évité de plus pour le compteur.
    var surEvite: (() -> Void)?

    private let moteur: MoteurSites?
    private let fichierRegles: URL?
    private let lecteur = LecteurNavigateurs()
    private let ligne = NSMenuItem(title: "Sites : démarrage…", action: nil, keyEquivalent: "")
    private let actif: Bool
    private var minuteur: Timer?
    private var observateur: NSObjectProtocol?
    private var fenetre: FenetreAlerte?

    /// Domaines où le salarié a choisi de continuer : plus d'alerte jusqu'à la fin de l'app.
    private var autorises: Set<String> = []
    /// Domaines dont l'extension s'est occupée (avertissement affiché dans cet onglet Chrome).
    private var traitesParExtension: Set<String> = []
    /// Onglets Chrome vus sur la page d'avertissement de l'extension, avec l'heure.
    private var ongletsExtension: [String: Date] = [:]
    /// Dernière page sans alerte vue dans chaque onglet : le retour arrière de Safari.
    private var pagesSures: [String: (adresse: String, date: Date)] = [:]
    /// Chrome : adresse louche vue une fois, en attente du second relevé.
    private var enAttente: [String: String] = [:]
    private var raccourcisVus: Set<String> = []
    private var alertes = 0
    private var dernier: String?

    private let backend: URL
    private let session: URLSession
    private let sessionId: String
    private let horloge: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = .current
        return f
    }()

    init() {
        let env = ProcessInfo.processInfo.environment
        actif = env["DEDALE_SITES"] != "off"
        if let (regles, url) = ReglesSites.charger() {
            moteur = MoteurSites(regles)
            fichierRegles = url
        } else {
            moteur = nil
            fichierRegles = nil
        }
        let brut = env["DEDALE_BACKEND"] ?? "http://127.0.0.1:8700"
        backend = URL(string: brut) ?? URL(string: "http://127.0.0.1:8700")!
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 3
        conf.timeoutIntervalForResource = 3
        conf.waitsForConnectivity = false
        session = URLSession(configuration: conf)
        sessionId = Self.identifiantNavigateur()
    }

    /// Insère la ligne d'état sous `apres` dans le menu et lance la veille.
    func demarrer(menu: NSMenu, apres: NSMenuItem) {
        ligne.isEnabled = false
        let index = menu.index(of: apres)
        menu.insertItem(ligne, at: index >= 0 ? index + 1 : menu.numberOfItems)
        guard actif else {
            majLigne("Sites : veille coupée (DEDALE_SITES=off)", couleur: Teinte.gris)
            return
        }
        guard moteur != nil else {
            majLigne("Sites : règles introuvables", couleur: Teinte.gris)
            journal("sites : partage/regles-sites.json introuvable, veille des sites coupée")
            return
        }
        journal("sites : règles lues dans \(fichierRegles?.path ?? "?"), session \(sessionId)")
        majLigne(nil, couleur: Teinte.cyan)
        observateur = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.didActivateApplicationNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.premierPlanChange() }
        premierPlanChange()
    }

    func etat() -> [String: Any] {
        var permissions: [String: String] = [:]
        for n in Navigateur.allCases { permissions[n.nom.lowercased()] = lecteur.permission(n).rawValue }
        return [
            "actif": actif && moteur != nil,
            "lecture_en_cours": minuteur != nil,
            "autorisations": permissions,
            "alertes": alertes,
            "dernier_site_louche": dernier ?? NSNull(),
            "alerte_affichee": fenetre != nil,
        ]
    }

    // MARK: Premier plan

    private var navigateurDevant: Navigateur? {
        NSWorkspace.shared.frontmostApplication?.bundleIdentifier.flatMap { Navigateur(rawValue: $0) }
    }

    /// La lecture ne tourne que pendant qu'un navigateur surveillé est au premier plan.
    private func premierPlanChange() {
        if navigateurDevant != nil {
            guard minuteur == nil else { return }
            let m = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.tic() }
            RunLoop.main.add(m, forMode: .common)
            minuteur = m
            tic()
        } else {
            minuteur?.invalidate()
            minuteur = nil
        }
    }

    private func tic() {
        guard let n = navigateurDevant else {
            premierPlanChange()
            return
        }
        guard fenetre == nil else { return }
        switch lecteur.permission(n) {
        case .accordee:
            break
        case .enCours:
            return
        case .inconnue, .refusee:
            lecteur.verifierPermission(n) { [weak self] p in
                guard let self else { return }
                if p == .refusee {
                    self.majLigne("Sites : autorisez Dédale pour \(n.nom) (Réglages Système, Automatisation)",
                                  couleur: Teinte.rouge)
                } else if p == .accordee {
                    self.majLigne(nil, couleur: Teinte.cyan)
                }
            }
            return
        }
        guard let onglet = lecteur.lire(n) else { return }
        examiner(onglet)
    }

    // MARK: Analyse

    private func examiner(_ o: OngletLu) {
        guard let moteur else { return }
        let adresse = o.adresse
        if o.navigateur == .chrome, adresse.hasPrefix("chrome-extension://"), adresse.contains("/avertissement.html") {
            ongletsExtension[o.cle] = Date()
            enAttente[o.cle] = nil
            return
        }
        let minuscules = adresse.lowercased()
        guard minuscules.hasPrefix("http://") || minuscules.hasPrefix("https://") else { return }
        let r = moteur.analyser(adresse)

        if r.verdict == "raccourci" {
            if raccourcisVus.insert(o.cle + " " + r.domaine).inserted {
                journal("sites : lien raccourci \(r.domaine), adresse d'arrivée examinée après la redirection")
                Bulle("Lien raccourci (\(r.affiche)) : Dédale vérifiera l'adresse d'arrivée.", ok: true)
                    .montrer(capture: "site-raccourci")
            }
            return
        }
        guard r.verdict == "louche" else {
            pagesSures[o.cle] = (adresse, Date())
            enAttente[o.cle] = nil
            return
        }
        if autorises.contains(r.domaine) || traitesParExtension.contains(r.domaine) { return }

        if o.navigateur == .chrome {
            if let vu = ongletsExtension[o.cle], Date().timeIntervalSince(vu) < 600 {
                // L'extension a averti dans cet onglet : le salarié a continué depuis sa page.
                traitesParExtension.insert(r.domaine)
                journal("sites : \(r.domaine) déjà traité par l'extension Chrome, pas de seconde alerte")
                return
            }
            // Laisser un relevé à l'extension : si elle est installée, l'onglet passe sur sa page.
            if enAttente[o.cle] != r.domaine {
                enAttente[o.cle] = r.domaine
                return
            }
        }
        enAttente[o.cle] = nil
        alerter(o, r, moteur)
    }

    private func alerter(_ o: OngletLu, _ r: AnalyseSite, _ moteur: MoteurSites) {
        alertes += 1
        dernier = r.domaine
        let (titre, suite) = moteur.titres(r)
        var a = Avertissement(
            id: Avertissement.nouvelIdentifiant(),
            categorie: "phishing",
            message: titre,
            detail: Avertissement.nettoyer("\(suite) \(r.explication ?? "")", max: 280),
            sessionId: sessionId,
            gravite: nil,
            cible: r.domaine,
            lien: nil
        )
        a.raisons = r.explication.map { [$0] } ?? []
        a.conseil = moteur.conseil(r)
        a.titreAnnuler = "Revenir en arrière"
        a.titreContinuer = "Continuer quand même"
        a.puce = r.marque != nil ? "Faux site" : "Site louche"
        a.prefixe = "site-\(r.categorie ?? "louche")".replacingOccurrences(of: "_", with: "-")
        journal("sites : \(o.navigateur.nom), \(r.domaine) louche (\(r.raison ?? "?"))")

        let f = FenetreAlerte(a)
        f.surChoix = { [weak self, weak f] choix in
            guard let self, let f else { return }
            if choix == "annuler" {
                // Rien ne part : le retour arrière reste sur le poste.
                self.revenir(o, domaine: r.domaine)
                self.surEvite?()
                f.montrerCoach(Coach.fiche(pour: a))
            } else {
                self.autorises.insert(r.domaine)
                self.signaler(r.domaine) { [weak f] ok in f?.confirmer(remonte: ok) }
            }
        }
        f.surFermeture = { [weak self] in self?.fenetre = nil }
        fenetre = f
        f.montrer()
    }

    private func revenir(_ o: OngletLu, domaine: String) {
        let sure = pagesSures[o.cle].flatMap { Date().timeIntervalSince($0.date) < 900 ? $0.adresse : nil }
        journal("sites : retour arrière dans \(o.navigateur.nom)" + (sure == nil && o.navigateur == .safari ? " (fermeture de l'onglet)" : ""))
        lecteur.revenir(o, pageSure: sure) { [weak self] actuelle in
            guard let self, let moteur = self.moteur else { return false }
            return moteur.analyser(actuelle).domaine == domaine
        }
    }

    // MARK: SOC

    /// Même événement que l'extension (CONTRATS.md, « Extension Chrome ») : le domaine, la
    /// catégorie, le choix et le contexte, rien d'autre.
    private func signaler(_ domaine: String, fin: @escaping (Bool) -> Void) {
        let corps: [String: Any] = [
            "horodatage": horloge.string(from: Date()),
            "source": "humain",
            "surface": "poste",
            "type": "avertissement",
            "session_id": sessionId,
            "user_agent": "dedale-mac/0.2",
            "details": ["categorie": "phishing", "choix": "continuer", "contexte": "navigation", "cible": domaine],
        ]
        guard let donnees = try? JSONSerialization.data(withJSONObject: corps) else {
            fin(false)
            return
        }
        var requete = URLRequest(url: backend.appendingPathComponent("api/evenements"))
        requete.httpMethod = "POST"
        requete.setValue("application/json", forHTTPHeaderField: "Content-Type")
        requete.httpBody = donnees
        session.dataTask(with: requete) { _, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            let ok = erreur == nil && (200..<300).contains(code)
            journal(ok ? "sites : SOC prévenue (\(domaine), session \(self.sessionId))"
                       : "sites : SOC injoignable, \(domaine) non signalé")
            DispatchQueue.main.async { fin(ok) }
        }.resume()
    }

    // MARK: Divers

    private func majLigne(_ texte: String?, couleur: NSColor) {
        let navigateurs = Navigateur.allCases.filter {
            NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0.rawValue) != nil
        }.map(\.nom)
        ligne.title = texte ?? "Sites surveillés dans \(navigateurs.isEmpty ? "Safari et Chrome" : navigateurs.joined(separator: " et "))"
        ligne.image = NSImage(size: NSSize(width: 8, height: 8), flipped: false) { rect in
            couleur.setFill()
            NSBezierPath(ovalIn: rect).fill()
            return true
        }
    }

    /// `navigateur-` et 8 caractères tirés au hasard une fois, comme l'extension : les
    /// passages outre de ce Mac s'ajoutent au même incident.
    private static func identifiantNavigateur() -> String {
        let dossier: URL
        if let brut = ProcessInfo.processInfo.environment["DEDALE_ETAT"], !brut.isEmpty {
            dossier = URL(fileURLWithPath: brut)
        } else {
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? URL(fileURLWithPath: NSTemporaryDirectory())
            dossier = support.appendingPathComponent("Dedale")
        }
        let fichier = dossier.appendingPathComponent("sites-session.txt")
        if let lu = try? String(contentsOf: fichier, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
           lu.hasPrefix("navigateur-"), lu.count == 19 {
            return lu
        }
        let nouveau = "navigateur-" + String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(8)).lowercased()
        try? FileManager.default.createDirectory(at: dossier, withIntermediateDirectories: true)
        try? nouveau.write(to: fichier, atomically: true, encoding: .utf8)
        return nouveau
    }
}
