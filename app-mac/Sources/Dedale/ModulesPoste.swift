import Foundation

/// Les modules de Dédale sur le poste, ce que chacun lit et ce qu'il envoie à la SOC. Ces
/// textes s'affichent tels quels dans le panneau « Ce que Dédale regarde sur ce poste » :
/// ils décrivent ce que fait le code, et la section « Vie privée » de la landing les reprend.
enum ModulePoste: String, CaseIterable {
    case mails, sites, telechargements, agents

    var titre: String {
        switch self {
        case .mails: return "Mails"
        case .sites: return "Sites"
        case .telechargements: return "Téléchargements"
        case .agents: return "Agents IA"
        }
    }

    var symbole: String {
        switch self {
        case .mails: return "envelope"
        case .sites: return "globe"
        case .telechargements: return "arrow.down.circle"
        case .agents: return "cpu"
        }
    }

    var lit: String {
        switch self {
        case .mails:
            return "Le verdict du serveur de messagerie sur chaque mail reçu : expéditeur, objet, raisons. Jamais la messagerie du Mac."
        case .sites:
            return "L'adresse des pages ouvertes, pour repérer un site sosie. Jamais leur contenu ni vos formulaires."
        case .telechargements:
            return "Les nouveaux fichiers du dossier Téléchargements : leur nom, la provenance notée par macOS et leur structure (macros, chiffrement)."
        case .agents:
            return "Les fichiers de configuration MCP des assistants connus (Claude, Cursor, VS Code, Windsurf…) : le nom de chaque serveur et sa commande de lancement."
        }
    }

    var envoie: String {
        switch self {
        case .mails:
            return "Le type d'alerte et votre choix, que vous annuliez ou continuiez. La copie désarmée d'un mail vient du serveur de messagerie, pas de ce poste."
        case .sites:
            return "Le nom du site sosie, si vous passez outre l'avertissement."
        case .telechargements:
            return "Le type du fichier, son domaine d'origine, son empreinte SHA-256 et votre choix, quel qu'il soit. Jamais son contenu ni son nom."
        case .agents:
            return "Le nom de chaque serveur, son type et ses droits risqués. Jamais les jetons, les clés ni les variables d'environnement."
        }
    }

    /// Ce que l'app ne lit jamais, écrit noir sur blanc dans le panneau.
    static let jamais = ["Le presse-papiers", "Les frappes au clavier", "Les captures d'écran",
                         "Le contenu des pages", "L'historique de navigation"]
}

/// Dossier de l'état local de l'app (compteur, réglages, journal des fichiers mis de côté).
/// `DEDALE_ETAT` le déplace, pour les tests.
enum DossierEtat {
    static var url: URL {
        if let brut = ProcessInfo.processInfo.environment["DEDALE_ETAT"], !brut.isEmpty {
            return URL(fileURLWithPath: brut)
        }
        let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory())
        return support.appendingPathComponent("Dedale")
    }

    /// Écriture atomique d'un objet JSON dans le dossier d'état.
    static func ecrire(_ objet: Any, nom: String) {
        let fichier = url.appendingPathComponent(nom)
        do {
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            let donnees = try JSONSerialization.data(withJSONObject: objet, options: [.prettyPrinted, .sortedKeys])
            try donnees.write(to: fichier, options: .atomic)
        } catch {
            journal("état non enregistré (\(nom)) : \(error.localizedDescription)")
        }
    }

    static func lire(_ nom: String) -> Any? {
        guard let donnees = try? Data(contentsOf: url.appendingPathComponent(nom)) else { return nil }
        return try? JSONSerialization.jsonObject(with: donnees)
    }
}

/// Interrupteur de chaque module, gardé sur le Mac (`modules.json`). Un module coupé ne lit
/// plus rien et n'envoie plus rien. Chaque changement poste `ReglagesModules.changement`,
/// avec le module en `object` : un module branché ailleurs dans l'app (Sites) s'y abonne.
final class ReglagesModules {
    static let partage = ReglagesModules()
    static let changement = Notification.Name("dedale.modules.changement")
    private static let fichier = "modules.json"

    private var etats: [String: Bool]

    private init() {
        etats = (DossierEtat.lire(Self.fichier) as? [String: Bool]) ?? [:]
        // DEDALE_MODULES_COUPES=sites,agents : modules coupés au lancement (tests, démo).
        for nom in (ProcessInfo.processInfo.environment["DEDALE_MODULES_COUPES"] ?? "").split(separator: ",") {
            let n = nom.trimmingCharacters(in: .whitespaces)
            if ModulePoste(rawValue: n) != nil { etats[n] = false }
        }
    }

    func actif(_ m: ModulePoste) -> Bool { etats[m.rawValue] ?? true }

    func regler(_ m: ModulePoste, actif: Bool) {
        guard self.actif(m) != actif else { return }
        etats[m.rawValue] = actif
        DossierEtat.ecrire(etats, nom: Self.fichier)
        journal("module \(m.rawValue) \(actif ? "activé" : "coupé")")
        NotificationCenter.default.post(name: Self.changement, object: m)
    }

    var actifs: [ModulePoste] { ModulePoste.allCases.filter(actif) }
}

/// Identifiant du poste envoyé à la SOC : `poste-mac-` et 8 caractères tirés au hasard au
/// premier lancement. Ni le nom du Mac, ni celui de l'utilisateur.
enum IdentitePoste {
    static let identifiant: String = {
        if let brut = DossierEtat.lire("poste.json") as? [String: String], let id = brut["poste"],
           id.hasPrefix("poste-mac-") {
            return id
        }
        let id = "poste-mac-" + String(UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(8)).lowercased()
        DossierEtat.ecrire(["poste": id], nom: "poste.json")
        return id
    }()
}
