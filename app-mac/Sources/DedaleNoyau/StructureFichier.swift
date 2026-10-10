import CryptoKit
import Foundation

/// Ce que la structure d'un fichier dit de lui, sans en lire le texte : un programme
/// Mach-O ou un script, des macros dans un document Office, une archive chiffrée.
///
/// Seuls l'en-tête du fichier et la table des matières d'une archive ZIP sont lus. Rien de
/// ce qui est lu ne sort du poste : la règle n'en tire que des booléens.
public struct StructureFichier: Equatable, Sendable {
    /// Dossier présenté comme un fichier (`.app`, `.pkg` en paquet, `.workflow`…).
    public var paquet = false
    /// Binaire Mach-O ou exécutable Windows (`MZ`).
    public var binaire = false
    /// Commence par `#!` et porte le droit d'exécution.
    public var scriptExecutable = false
    /// Document Office avec un projet VBA (`vbaProject.bin`, `_VBA_PROJECT`).
    public var macros = false
    /// Archive ZIP dont au moins une entrée est chiffrée.
    public var archiveChiffree = false

    public init(paquet: Bool = false, binaire: Bool = false, scriptExecutable: Bool = false,
                macros: Bool = false, archiveChiffree: Bool = false) {
        self.paquet = paquet
        self.binaire = binaire
        self.scriptExecutable = scriptExecutable
        self.macros = macros
        self.archiveChiffree = archiveChiffree
    }

    static let extensionsPaquet: Set<String> = ["app", "pkg", "mpkg", "scptd", "workflow", "action", "prefpane", "kext"]

    /// Inspecte le fichier ou le paquet à `url`. Lectures bornées : 4 Ko d'en-tête, la fin
    /// du fichier pour l'annuaire ZIP, 2 Mo au plus pour un document Office ancien.
    public static func inspecter(_ url: URL) -> StructureFichier {
        var s = StructureFichier()
        var estDossier: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &estDossier) else { return s }
        if estDossier.boolValue {
            s.paquet = extensionsPaquet.contains(url.pathExtension.lowercased())
            return s
        }
        guard let h = try? FileHandle(forReadingFrom: url) else { return s }
        defer { try? h.close() }
        let tete = (try? h.read(upToCount: 4096)) ?? Data()
        let o = [UInt8](tete.prefix(8))

        if o.count >= 4 {
            let magiques: [[UInt8]] = [[0xFE, 0xED, 0xFA, 0xCE], [0xFE, 0xED, 0xFA, 0xCF],
                                       [0xCE, 0xFA, 0xED, 0xFE], [0xCF, 0xFA, 0xED, 0xFE],
                                       [0xCA, 0xFE, 0xBA, 0xBE]]
            if magiques.contains(Array(o.prefix(4))) { s.binaire = true }
        }
        if o.count >= 2, o[0] == 0x4D, o[1] == 0x5A { s.binaire = true }
        if o.count >= 2, o[0] == 0x23, o[1] == 0x21, FileManager.default.isExecutableFile(atPath: url.path) {
            s.scriptExecutable = true
        }
        // ZIP (docx, xlsx, pptx, jar… et l'archive elle-même).
        if o.count >= 4, o[0] == 0x50, o[1] == 0x4B, o[2] == 0x03, o[3] == 0x04 {
            let annuaire = AnnuaireZIP.lire(h, tete: tete)
            s.archiveChiffree = annuaire.chiffree
            s.macros = annuaire.noms.contains { $0.lowercased().hasSuffix("vbaproject.bin") }
        }
        // Document Office ancien (OLE) : le flux du projet VBA porte un nom UTF-16 connu.
        if o.count >= 8, o == [0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1] {
            try? h.seek(toOffset: 0)
            let debut = (try? h.read(upToCount: 2 << 20)) ?? Data()
            let marque = Data("_VBA_PROJECT".utf16.flatMap { [UInt8($0 & 0xFF), UInt8($0 >> 8)] })
            s.macros = debut.range(of: marque) != nil
        }
        return s
    }

    /// Empreinte SHA-256 en hexadécimal. Pour un paquet, l'empreinte couvre chaque fichier
    /// du dossier (chemin relatif puis contenu, dans l'ordre alphabétique).
    public static func empreinte(_ url: URL) -> String? {
        var hache = SHA256()
        var estDossier: ObjCBool = false
        guard FileManager.default.fileExists(atPath: url.path, isDirectory: &estDossier) else { return nil }
        if estDossier.boolValue {
            guard let parcours = FileManager.default.enumerator(at: url, includingPropertiesForKeys: [.isRegularFileKey])
            else { return nil }
            var fichiers: [(String, URL)] = []
            let base = url.standardizedFileURL.path
            for case let f as URL in parcours {
                guard (try? f.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true else { continue }
                let relatif = String(f.standardizedFileURL.path.dropFirst(base.count))
                fichiers.append((relatif, f))
            }
            for (relatif, f) in fichiers.sorted(by: { $0.0 < $1.0 }) {
                hache.update(data: Data(relatif.utf8))
                guard ajouter(f, a: &hache) else { return nil }
            }
        } else {
            guard ajouter(url, a: &hache) else { return nil }
        }
        return hache.finalize().map { String(format: "%02x", $0) }.joined()
    }

    private static func ajouter(_ url: URL, a hache: inout SHA256) -> Bool {
        guard let h = try? FileHandle(forReadingFrom: url) else { return false }
        defer { try? h.close() }
        while let morceau = try? h.read(upToCount: 1 << 20), !morceau.isEmpty {
            hache.update(data: morceau)
        }
        return true
    }
}

/// Lecture de la table des matières d'une archive ZIP : noms des entrées et chiffrement
/// (bit 0 des drapeaux). Le contenu compressé n'est jamais lu.
enum AnnuaireZIP {
    struct Resultat {
        var noms: [String] = []
        var chiffree = false
    }

    static func lire(_ h: FileHandle, tete: Data) -> Resultat {
        var r = Resultat()
        guard let taille = try? h.seekToEnd(), taille >= 22 else { return r }
        let fin = min(taille, 65_557)
        try? h.seek(toOffset: taille - fin)
        guard let queue = try? h.read(upToCount: Int(fin)) else { return r }
        let q = [UInt8](queue)
        // Fin de l'annuaire central : signature 0x06054b50, cherchée depuis la fin.
        var i = q.count - 22
        while i >= 0 {
            if q[i] == 0x50, q[i + 1] == 0x4B, q[i + 2] == 0x05, q[i + 3] == 0x06 { break }
            i -= 1
        }
        guard i >= 0 else { return lireEnTetesLocaux(tete) }
        let entrees = Int(lire16(q, i + 10))
        let tailleAnnuaire = UInt64(lire32(q, i + 12))
        let debutAnnuaire = UInt64(lire32(q, i + 16))
        guard tailleAnnuaire <= 8 << 20, debutAnnuaire + tailleAnnuaire <= taille else { return r }
        try? h.seek(toOffset: debutAnnuaire)
        guard let brut = try? h.read(upToCount: Int(tailleAnnuaire)) else { return r }
        let a = [UInt8](brut)
        var p = 0
        for _ in 0..<min(entrees, 20_000) {
            guard p + 46 <= a.count, a[p] == 0x50, a[p + 1] == 0x4B, a[p + 2] == 0x01, a[p + 3] == 0x02 else { break }
            let drapeaux = lire16(a, p + 8)
            let lNom = Int(lire16(a, p + 28)), lExtra = Int(lire16(a, p + 30)), lCom = Int(lire16(a, p + 32))
            guard p + 46 + lNom <= a.count else { break }
            if drapeaux & 1 == 1 { r.chiffree = true }
            r.noms.append(String(decoding: a[(p + 46)..<(p + 46 + lNom)], as: UTF8.self))
            p += 46 + lNom + lExtra + lCom
        }
        return r
    }

    /// Repli sans annuaire central lisible : premier en-tête local seulement.
    static func lireEnTetesLocaux(_ tete: Data) -> Resultat {
        var r = Resultat()
        let t = [UInt8](tete)
        guard t.count >= 30 else { return r }
        r.chiffree = lire16(t, 6) & 1 == 1
        let lNom = Int(lire16(t, 26))
        if 30 + lNom <= t.count { r.noms.append(String(decoding: t[30..<(30 + lNom)], as: UTF8.self)) }
        return r
    }

    static func lire16(_ o: [UInt8], _ i: Int) -> UInt16 { UInt16(o[i]) | UInt16(o[i + 1]) << 8 }
    static func lire32(_ o: [UInt8], _ i: Int) -> UInt32 {
        UInt32(o[i]) | UInt32(o[i + 1]) << 8 | UInt32(o[i + 2]) << 16 | UInt32(o[i + 3]) << 24
    }
}
