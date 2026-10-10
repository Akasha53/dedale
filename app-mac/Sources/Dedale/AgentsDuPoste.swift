import DedaleNoyau
import Foundation

/// Module « Agents IA » : inventaire des serveurs MCP configurés sur le poste, envoyé à la
/// SOC (`POST /api/agents/poste`, voir CONTRATS.md).
///
/// D'où vient la configuration lue :
/// - `DEDALE_DEMO_AGENTS_DIR` : un dossier factice qui reproduit l'arborescence d'un dossier
///   personnel (démo, tests, captures) ;
/// - sinon la configuration factice rangée dans l'app (`Contents/Resources/agents-factices`) ;
/// - la vraie configuration du Mac seulement avec `DEDALE_AGENTS_REEL=1`. Aucun bouton de
///   l'app ne l'active : rien de réel ne peut s'afficher par un clic pendant une démo.
final class AgentsDuPoste {
    enum Source {
        case demo(URL)
        case reel(URL)
        case aucune

        var libelle: String {
            switch self {
            case .demo: return "Configuration factice (démo)"
            case .reel: return "Configuration réelle de ce Mac"
            case .aucune: return "Aucune configuration lue"
            }
        }

        var code: String {
            switch self {
            case .reel: return "reel"
            default: return "demo"
            }
        }
    }

    let source: Source
    private let backend: URL
    private let session: URLSession
    private let file = DispatchQueue(label: "dedale.agents")
    private var minuteur: Timer?

    private(set) var resultat: InventaireAgents.Resultat?
    private(set) var dernierEnvoi: Date?
    private(set) var envoiOk: Bool?
    /// Appelé sur le fil principal après chaque analyse et chaque envoi.
    var surMaj: (() -> Void)?

    init(backend: URL) {
        self.backend = backend
        let env = ProcessInfo.processInfo.environment
        if let d = env["DEDALE_DEMO_AGENTS_DIR"], !d.isEmpty {
            source = .demo(URL(fileURLWithPath: (d as NSString).expandingTildeInPath, isDirectory: true))
        } else if env["DEDALE_AGENTS_REEL"] == "1" {
            source = .reel(FileManager.default.homeDirectoryForCurrentUser)
        } else if let r = Bundle.main.resourceURL?.appendingPathComponent("agents-factices"),
                  FileManager.default.fileExists(atPath: r.path) {
            source = .demo(r)
        } else {
            source = .aucune
        }
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 3
        conf.timeoutIntervalForResource = 4
        session = URLSession(configuration: conf)
    }

    func demarrer() {
        analyser()
        minuteur?.invalidate()
        // La configuration change rarement : une nouvelle analyse toutes les 5 minutes.
        let t = Timer.scheduledTimer(withTimeInterval: 300, repeats: true) { [weak self] _ in self?.analyser() }
        RunLoop.main.add(t, forMode: .common)
        minuteur = t
    }

    func arreter() {
        minuteur?.invalidate()
        minuteur = nil
    }

    /// Lit la configuration, puis envoie l'inventaire à la SOC.
    func analyser() {
        let racine: URL
        switch source {
        case .demo(let u), .reel(let u): racine = u
        case .aucune:
            journal("agents IA : aucune configuration à lire (scan réel désactivé)")
            return
        }
        file.async { [weak self] in
            guard let self else { return }
            let r = InventaireAgents.analyser(racine: racine)
            journal("agents IA (\(self.source.code)) : \(r.serveurs.count) serveur(s) MCP dans \(r.clients.count) client(s), "
                    + "\(r.risques) avec des droits risqués")
            DispatchQueue.main.async {
                self.resultat = r
                self.surMaj?()
                self.envoyer(r)
            }
        }
    }

    private func envoyer(_ r: InventaireAgents.Resultat) {
        let corps = InventaireAgents.charge(r, poste: IdentitePoste.identifiant, source: source.code,
                                            horodatage: Self.horloge.string(from: Date()))
        guard let donnees = try? JSONSerialization.data(withJSONObject: corps) else { return }
        var requete = URLRequest(url: backend.appendingPathComponent("api/agents/poste"))
        requete.httpMethod = "POST"
        requete.setValue("application/json", forHTTPHeaderField: "Content-Type")
        requete.httpBody = donnees
        Backend.signer(&requete)
        session.dataTask(with: requete) { [weak self] _, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            let ok = erreur == nil && (200..<300).contains(code)
            journal(ok ? "agents IA : inventaire envoyé à la SOC"
                       : "agents IA : inventaire non remonté (\(erreur?.localizedDescription ?? "HTTP \(code)"))")
            DispatchQueue.main.async {
                guard let self else { return }
                self.envoiOk = ok
                if ok { self.dernierEnvoi = Date() }
                self.surMaj?()
            }
        }.resume()
    }

    static let horloge: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = .current
        return f
    }()

    static let libellesTypes = ["fichiers": "Fichiers", "shell": "Shell", "mail": "Mail", "navigateur": "Navigateur",
                                "reseau": "Réseau", "autre": "Autre"]
    static let libellesDroits = ["shell": "Shell", "mail": "Mails", "disque_entier": "Tout le disque"]
}
