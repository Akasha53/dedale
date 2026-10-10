import Foundation

/// Règles du module Téléchargements : faut-il prévenir le salarié avant qu'il ouvre ce
/// fichier ? La règle ne regarde que le nom, la provenance et la structure (voir
/// `StructureFichier`), jamais le texte du fichier.
///
/// Ce qui déclenche une pop-up :
/// - une double extension (`facture.pdf.app`) ou un nom qui se retourne à l'écran
///   (caractère de contrôle bidirectionnel), quelle que soit la provenance ;
/// - une application, un script, une image disque, un installeur ou un raccourci venu d'un
///   mail, d'une messagerie, d'AirDrop ou d'un site absent des domaines connus ;
/// - un document Office avec macros, ou une archive protégée par mot de passe, venus de
///   l'extérieur.
public struct RegleTelechargement: Sendable {
    public enum Motif: String, CaseIterable, Sendable {
        case nomTrompeur = "nom_trompeur"
        case doubleExtension = "double_extension"
        case application
        case installeur
        case script
        case imageDisque = "image_disque"
        case raccourci
        case macros
        case archiveChiffree = "archive_chiffree"
    }

    public struct Verdict: Equatable, Sendable {
        /// Vrai si la pop-up doit s'afficher.
        public var alerte: Bool
        /// Motifs relevés, du plus grave au moins grave.
        public var motifs: [Motif]
        /// Type du fichier envoyé à la SOC : `application`, `script`, `image_disque`,
        /// `installeur`, `raccourci`, `document_macros`, `archive_chiffree`, `document`.
        public var typeFichier: String
        /// `haute` pour ce qui lance un programme, `moyenne` pour macros et archive chiffrée.
        public var gravite: String
        /// Phrase principale de la pop-up.
        public var message: String
        /// Explication courte du motif principal et du canal.
        public var detail: String
    }

    /// Domaines dont un programme peut venir sans pop-up (sous-domaines compris).
    public var domainesConnus: [String]

    public static let domainesConnusParDefaut = ["orbispay.example", "apple.com", "microsoft.com", "mozilla.org", "google.com"]

    public init(domainesConnus: [String] = RegleTelechargement.domainesConnusParDefaut) {
        self.domainesConnus = domainesConnus
    }

    static let familles: [String: Motif] = {
        var f: [String: Motif] = [:]
        for e in ["app", "exe", "msi", "com", "scr", "bin", "run", "appimage", "apk", "prefpane", "kext"] { f[e] = .application }
        for e in ["pkg", "mpkg"] { f[e] = .installeur }
        for e in ["command", "sh", "zsh", "bash", "csh", "ksh", "tool", "py", "pl", "rb", "js", "jse", "vbs", "vbe",
                  "wsf", "ps1", "bat", "cmd", "scpt", "scptd", "applescript", "terminal", "workflow", "action", "jar"] {
            f[e] = .script
        }
        for e in ["dmg", "iso", "img", "vhd", "vhdx", "sparseimage", "sparsebundle", "toast"] { f[e] = .imageDisque }
        for e in ["webloc", "inetloc", "fileloc", "url", "lnk", "desktop", "afploc", "ftploc"] { f[e] = .raccourci }
        return f
    }()

    static let extensionsMacros: Set<String> = ["docm", "dotm", "xlsm", "xltm", "xlam", "xlsb", "pptm", "potm", "ppam", "ppsm", "sldm"]

    /// Extensions qu'un salarié prend pour un document : devant une extension de programme,
    /// elles font une double extension.
    static let extensionsDocument: Set<String> = [
        "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "rtf", "txt", "csv", "pages",
        "numbers", "key", "jpg", "jpeg", "png", "gif", "heic", "tif", "tiff", "bmp", "svg", "mp3", "mp4", "mov",
        "avi", "wav", "m4a", "zip", "rar", "7z", "html", "htm", "eml", "msg", "ics", "vcf",
    ]

    /// Caractères qui retournent l'affichage d'un nom (`facture‮fdp.app` s'affiche
    /// « facture.ppa.pdf »).
    static let bidi: Set<UInt32> = [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F]

    public func analyser(nom: String, provenance: Provenance, structure: StructureFichier) -> Verdict {
        let morceaux = nom.split(separator: ".", omittingEmptySubsequences: false).map {
            $0.trimmingCharacters(in: .whitespaces).lowercased()
        }
        let ext = morceaux.count > 1 ? morceaux.last ?? "" : ""
        let avant = morceaux.count > 2 ? morceaux[morceaux.count - 2] : ""

        var famille = RegleTelechargement.familles[ext]
        // Pas d'extension parlante, mais la structure dit « programme ».
        if famille == nil, structure.binaire { famille = .application }
        if famille == nil, structure.scriptExecutable { famille = .script }
        if famille == nil, structure.paquet { famille = .application }

        var motifs: [Motif] = []
        if nom.unicodeScalars.contains(where: { RegleTelechargement.bidi.contains($0.value) }) {
            motifs.append(.nomTrompeur)
        }
        if famille != nil, RegleTelechargement.extensionsDocument.contains(avant) {
            motifs.append(.doubleExtension)
        }

        let exterieur = provenance.venueDeLExterieur
        let origineRisquee: Bool
        switch provenance.canal {
        case .locale: origineRisquee = false
        case .site: origineRisquee = !Provenance.estConnu(provenance.domaine, parmi: domainesConnus)
        case .mail, .messagerie, .airdrop, .inconnue: origineRisquee = true
        }
        if let famille, origineRisquee || motifs.contains(.doubleExtension) || motifs.contains(.nomTrompeur) {
            motifs.append(famille)
        }
        let macros = structure.macros || RegleTelechargement.extensionsMacros.contains(ext)
        if macros, exterieur { motifs.append(.macros) }
        if structure.archiveChiffree, exterieur { motifs.append(.archiveChiffree) }

        let ordre = Motif.allCases
        motifs = Array(Set(motifs)).sorted { ordre.firstIndex(of: $0)! < ordre.firstIndex(of: $1)! }

        let typeFichier: String
        switch famille {
        case .application?: typeFichier = "application"
        case .installeur?: typeFichier = "installeur"
        case .script?: typeFichier = "script"
        case .imageDisque?: typeFichier = "image_disque"
        case .raccourci?: typeFichier = "raccourci"
        default:
            typeFichier = macros ? "document_macros" : (structure.archiveChiffree ? "archive_chiffree" : "document")
        }

        let lanceUnProgramme = motifs.contains { [.nomTrompeur, .doubleExtension, .application, .installeur, .script,
                                                  .imageDisque, .raccourci].contains($0) }
        let gravite = lanceUnProgramme ? "haute" : "moyenne"
        let message = Self.message(provenance: provenance, motifs: motifs, lanceUnProgramme: lanceUnProgramme)
        let detail = Self.detail(motifs: motifs, ext: ext, avant: avant, provenance: provenance,
                                 connu: Provenance.estConnu(provenance.domaine, parmi: domainesConnus))
        return Verdict(alerte: !motifs.isEmpty, motifs: motifs, typeFichier: typeFichier, gravite: gravite,
                       message: message, detail: detail)
    }

    /// « Ce fichier vient de <domaine> et peut lancer un programme. »
    static func message(provenance: Provenance, motifs: [Motif], lanceUnProgramme: Bool) -> String {
        let origine: String
        if let d = provenance.domaine {
            origine = "vient de \(d)"
        } else {
            switch provenance.canal {
            case .mail: origine = "vient d'un mail"
            case .messagerie: origine = "vient d'une messagerie"
            case .airdrop: origine = "vient d'AirDrop"
            case .locale: origine = "a été créé sur ce Mac"
            case .site, .inconnue: origine = "vient d'une source inconnue"
            }
        }
        if lanceUnProgramme { return "Ce fichier \(origine) et peut lancer un programme." }
        if motifs.contains(.macros) { return "Ce fichier \(origine) et contient des macros." }
        if motifs.contains(.archiveChiffree) { return "Ce fichier \(origine) et il est verrouillé par un mot de passe." }
        return "Ce fichier \(origine)."
    }

    static func detail(motifs: [Motif], ext: String, avant: String, provenance: Provenance, connu: Bool) -> String {
        let canal: String
        switch provenance.canal {
        case .mail: canal = "Reçu en pièce jointe d'un mail."
        case .messagerie: canal = "Reçu par une messagerie."
        case .airdrop: canal = "Reçu par AirDrop."
        case .site: canal = connu ? "" : "sAIfe ne connaît pas ce site."
        case .inconnue: canal = "macOS n'a pas noté d'où il vient."
        case .locale: canal = ""
        }
        let raison: String
        switch motifs.first {
        case .nomTrompeur?:
            raison = "Son nom contient un caractère invisible qui retourne l'affichage : l'extension réelle est « .\(ext) »."
        case .doubleExtension?:
            raison = "Son nom finit par « .\(avant).\(ext) » : il ressemble à un \(avant.uppercased()) mais s'ouvre comme un programme."
        case .application?: raison = "C'est une application : l'ouvrir lance un programme sur ce Mac."
        case .installeur?: raison = "C'est un installeur : il peut modifier tout le système."
        case .script?: raison = "C'est un script : l'ouvrir exécute des commandes sur ce Mac."
        case .imageDisque?: raison = "C'est une image disque, qui contient le plus souvent une application à installer."
        case .raccourci?: raison = "C'est un raccourci : il ouvre une adresse ou un programme sans le montrer."
        case .macros?: raison = "Les macros sont du code qui s'exécute si on les autorise à l'ouverture."
        case .archiveChiffree?: raison = "Personne ne peut vérifier ce que contient l'archive avant de l'ouvrir avec le mot de passe."
        case nil: raison = ""
        }
        return [raison, canal].filter { !$0.isEmpty }.joined(separator: " ")
    }
}
