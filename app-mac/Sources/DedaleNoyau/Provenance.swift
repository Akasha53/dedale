import Foundation

/// D'où vient un fichier, tel que macOS l'a noté au téléchargement.
///
/// Deux attributs étendus suffisent, posés par le navigateur ou la messagerie :
/// - `com.apple.quarantine` : « drapeaux;date en hexadécimal;application;identifiant » ;
/// - `com.apple.metadata:kMDItemWhereFroms` : la liste des adresses d'origine (URL du
///   fichier, page qui le proposait, ou expéditeur du mail).
///
/// On n'en garde que le nom de domaine. Le chemin, les paramètres et l'objet d'un mail ne
/// sont jamais retenus : un lien de téléchargement porte souvent un jeton.
public struct Provenance: Equatable, Sendable {
    public enum Canal: String, Sendable {
        /// Pièce jointe d'un mail (Mail, Outlook…).
        case mail
        /// Téléchargé depuis un site.
        case site
        /// Reçu par une messagerie instantanée (Messages, Slack, Teams…).
        case messagerie
        /// Reçu par AirDrop.
        case airdrop
        /// Mis en quarantaine par macOS sans origine lisible.
        case inconnue
        /// Pas d'attribut de quarantaine : le fichier a été créé sur ce Mac.
        case locale
    }

    public var canal: Canal
    /// Nom de domaine seul (`factures-orbis.example`), en minuscules, sans `www.`.
    public var domaine: String?
    /// Application qui a écrit le fichier, telle que la quarantaine la nomme (`Safari`, `Mail`).
    public var application: String?

    public init(canal: Canal, domaine: String? = nil, application: String? = nil) {
        self.canal = canal
        self.domaine = domaine
        self.application = application
    }

    /// Le fichier vient-il de l'extérieur (attribut de quarantaine présent) ?
    public var venueDeLExterieur: Bool { canal != .locale }

    static let applicationsMail = ["mail", "outlook", "spark", "airmail", "thunderbird", "mimestream", "canary"]
    static let applicationsMessagerie = ["messages", "slack", "teams", "whatsapp", "telegram", "signal", "discord"]

    /// Provenance à partir des deux attributs. `quarantaine` vaut nil quand l'attribut est absent.
    public static func lire(quarantaine: String?, ouVient: [String]) -> Provenance {
        guard let quarantaine else {
            // Sans quarantaine, une liste d'origine seule (copie depuis un autre disque) ne
            // suffit pas à dire que le fichier vient d'internet.
            return Provenance(canal: .locale)
        }
        let champs = quarantaine.split(separator: ";", omittingEmptySubsequences: false).map(String.init)
        let application = champs.count > 2 ? nettoyerApplication(champs[2]) : nil
        let appBas = application?.lowercased() ?? ""

        var domaineURL: String?
        var domaineAdresse: String?
        var traceMail = false
        for brut in ouVient {
            let s = brut.trimmingCharacters(in: .whitespacesAndNewlines)
            if s.lowercased().hasPrefix("message:") || s.lowercased().hasPrefix("mailto:") {
                traceMail = true
                continue
            }
            if domaineURL == nil, let d = domaine(deURL: s) {
                domaineURL = d
                continue
            }
            if domaineAdresse == nil, let d = domaine(deAdresse: s) {
                domaineAdresse = d
                traceMail = true
            }
        }

        let canal: Canal
        if applicationsMail.contains(where: { appBas.contains($0) }) || (traceMail && domaineURL == nil) {
            canal = .mail
        } else if appBas.contains("sharingd") || appBas.contains("airdrop") {
            canal = .airdrop
        } else if applicationsMessagerie.contains(where: { appBas.contains($0) }) {
            canal = .messagerie
        } else if domaineURL != nil {
            canal = .site
        } else {
            canal = .inconnue
        }
        let domaine = canal == .mail ? (domaineAdresse ?? domaineURL) : (domaineURL ?? domaineAdresse)
        return Provenance(canal: canal, domaine: domaine, application: application)
    }

    /// Hôte d'une URL http(s) ou ftp, sans identifiants, port, chemin ni paramètres.
    public static func domaine(deURL s: String) -> String? {
        guard let url = URLComponents(string: s),
              let schema = url.scheme?.lowercased(), ["http", "https", "ftp"].contains(schema),
              let hote = url.host, !hote.isEmpty else { return nil }
        return normaliser(hote)
    }

    /// Domaine d'une adresse mail, seule ou sous la forme « Nom <adresse@domaine> ».
    public static func domaine(deAdresse s: String) -> String? {
        var adresse = s
        if let ouvre = s.lastIndex(of: "<"), let ferme = s.lastIndex(of: ">"), ouvre < ferme {
            adresse = String(s[s.index(after: ouvre)..<ferme])
        }
        adresse = adresse.trimmingCharacters(in: .whitespaces)
        guard !adresse.contains(" "), let arobase = adresse.lastIndex(of: "@") else { return nil }
        let d = String(adresse[adresse.index(after: arobase)...])
        guard d.contains("."), !d.contains("/") else { return nil }
        return normaliser(d)
    }

    static func normaliser(_ hote: String) -> String? {
        var h = hote.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: ". "))
        if h.hasPrefix("www.") { h.removeFirst(4) }
        let admis = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyz0123456789.-")
        guard !h.isEmpty, h.count <= 253, h.unicodeScalars.allSatisfy({ admis.contains($0) }) else { return nil }
        return h
    }

    private static func nettoyerApplication(_ s: String) -> String? {
        let propre = s.unicodeScalars.filter { !CharacterSet.controlCharacters.contains($0) }
        let texte = String(String.UnicodeScalarView(propre)).trimmingCharacters(in: .whitespaces)
        return texte.isEmpty ? nil : String(texte.prefix(60))
    }

    /// Le domaine est-il l'un des domaines connus (ou l'un de leurs sous-domaines) ?
    public static func estConnu(_ domaine: String?, parmi connus: [String]) -> Bool {
        guard let d = domaine else { return false }
        return connus.contains { c in
            let c = c.lowercased()
            return d == c || d.hasSuffix("." + c)
        }
    }
}
