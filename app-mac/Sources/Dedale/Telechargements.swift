import CoreServices
import DedaleNoyau
import Foundation

/// Un nouveau fichier de Téléchargements que la règle juge à risque.
struct FichierSignale {
    let id: String
    let url: URL
    /// Nom affichable : sans caractères de contrôle ni bidirectionnels.
    let nom: String
    let taille: Int64?
    let provenance: Provenance
    let verdict: RegleTelechargement.Verdict
    let empreinte: String?
}

/// Surveille le dossier Téléchargements (FSEvents). Les fichiers présents au démarrage sont
/// ignorés ; chaque nouveau fichier est jugé quand sa taille ne bouge plus (un téléchargement
/// en cours porte `.download`, `.crdownload` ou `.part` et attend la fin). Seul le premier
/// niveau du dossier est regardé, sans le sous-dossier « Dédale - mis de côté ».
final class SurveillanceTelechargements {
    enum Etat: Equatable { case arretee, active, accesRefuse, dossierAbsent }

    static let nomMisDeCote = "Dédale - mis de côté"
    static let suffixesEnCours = [".download", ".crdownload", ".part", ".partial", ".opdownload", ".tmp"]

    let dossier: URL
    let regle: RegleTelechargement
    /// Appelé sur le fil principal pour chaque fichier à risque.
    var surSignalement: ((FichierSignale) -> Void)?
    /// Appelé sur le fil principal quand l'état change.
    var surEtat: ((Etat) -> Void)?

    private(set) var etat: Etat = .arretee
    private let file = DispatchQueue(label: "dedale.telechargements")
    private var flux: FSEventStreamRef?
    private var connus: Set<String> = []
    private var aIgnorer: Set<String> = []
    private var enAttente: [String: (signature: String, depuis: Date)] = [:]
    private var relevePrevu = false
    private var secours: DispatchSourceTimer?
    /// Vrai entre demarrer() et arreter() : un dossier illisible est retenté toutes les 10 s.
    private var voulue = false

    init() {
        let env = ProcessInfo.processInfo.environment
        if let brut = env["DEDALE_TELECHARGEMENTS"], !brut.isEmpty {
            dossier = URL(fileURLWithPath: (brut as NSString).expandingTildeInPath, isDirectory: true)
        } else {
            dossier = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
                ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Downloads")
        }
        var connus = RegleTelechargement.domainesConnusParDefaut
        connus += (env["DEDALE_DOMAINES_CONNUS"] ?? "").split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces).lowercased() }.filter { !$0.isEmpty }
        regle = RegleTelechargement(domainesConnus: connus)
    }

    /// Le dossier affiché dans le menu (`~/Downloads` plutôt que le chemin complet).
    var dossierAffiche: String {
        (dossier.path as NSString).abbreviatingWithTildeInPath
    }

    func demarrer() {
        file.async { [self] in
            voulue = true
            guard flux == nil else { return }
            connus = []
            enAttente = [:]
            guard releve(initial: true) else {
                file.asyncAfter(deadline: .now() + 10) { [weak self] in
                    guard let self, self.voulue, self.flux == nil else { return }
                    self.demarrer()
                }
                return
            }
            var contexte = FSEventStreamContext(version: 0, info: Unmanaged.passUnretained(self).toOpaque(),
                                                retain: nil, release: nil, copyDescription: nil)
            let rappel: FSEventStreamCallback = { _, info, _, _, _, _ in
                guard let info else { return }
                Unmanaged<SurveillanceTelechargements>.fromOpaque(info).takeUnretainedValue().prevoirReleve(0.2)
            }
            let drapeaux = UInt32(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagNoDefer
                                  | kFSEventStreamCreateFlagWatchRoot)
            guard let f = FSEventStreamCreate(kCFAllocatorDefault, rappel, &contexte, [dossier.path] as CFArray,
                                              FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 0.3, drapeaux) else {
                journal("téléchargements : FSEvents indisponible, relevé toutes les 5 s seulement")
                return
            }
            FSEventStreamSetDispatchQueue(f, file)
            FSEventStreamStart(f)
            flux = f
            // Filet de sécurité si un événement se perd : un relevé toutes les 10 s.
            let t = DispatchSource.makeTimerSource(queue: file)
            t.schedule(deadline: .now() + 10, repeating: 10)
            t.setEventHandler { [weak self] in self?.prevoirReleve(0) }
            t.resume()
            secours = t
            journal("téléchargements : surveillance de \(dossierAffiche) (\(connus.count) fichier(s) déjà là, ignorés)")
        }
    }

    func arreter() {
        file.async { [self] in
            voulue = false
            if let f = flux {
                FSEventStreamStop(f)
                FSEventStreamInvalidate(f)
                FSEventStreamRelease(f)
            }
            flux = nil
            secours?.cancel()
            secours = nil
            changerEtat(.arretee)
        }
    }

    /// Le fichier `nom` va réapparaître (remis à sa place) : il ne doit pas déclencher d'alerte.
    func ignorerProchaineApparition(_ nom: String) {
        file.async { [self] in aIgnorer.insert(nom) }
    }

    // MARK: Relevé

    private func prevoirReleve(_ delai: Double) {
        file.async { [self] in
            guard !relevePrevu, flux != nil else { return }
            relevePrevu = true
            file.asyncAfter(deadline: .now() + delai) { [self] in
                relevePrevu = false
                _ = releve(initial: false)
            }
        }
    }

    /// Liste le premier niveau du dossier. Au premier relevé, tout ce qui est là devient connu.
    @discardableResult
    private func releve(initial: Bool) -> Bool {
        let cles: [URLResourceKey] = [.isDirectoryKey, .isPackageKey, .isSymbolicLinkKey, .fileSizeKey,
                                       .contentModificationDateKey]
        let entrees: [URL]
        do {
            entrees = try FileManager.default.contentsOfDirectory(at: dossier, includingPropertiesForKeys: cles,
                                                                  options: [.skipsHiddenFiles])
        } catch let e as NSError {
            let refuse = e.domain == NSCocoaErrorDomain && e.code == NSFileReadNoPermissionError
            changerEtat(refuse ? .accesRefuse : .dossierAbsent)
            if initial { journal("téléchargements : \(dossierAffiche) illisible (\(refuse ? "accès refusé" : "absent"))") }
            return false
        }
        changerEtat(.active)
        let presents = Set(entrees.map(\.lastPathComponent))
        connus.formIntersection(presents)
        enAttente = enAttente.filter { presents.contains($0.key) }
        var encoreEnAttente = false

        for url in entrees {
            let nom = url.lastPathComponent
            guard !connus.contains(nom), nom != Self.nomMisDeCote,
                  !Self.suffixesEnCours.contains(where: { nom.lowercased().hasSuffix($0) }) else { continue }
            let v = try? url.resourceValues(forKeys: Set(cles))
            if v?.isSymbolicLink == true { connus.insert(nom); continue }
            // Un dossier ordinaire n'est pas un téléchargement ; un paquet (.app) en est un.
            if v?.isDirectory == true, v?.isPackage != true,
               !["app", "pkg", "mpkg", "scptd", "workflow", "action"].contains(url.pathExtension.lowercased()) {
                connus.insert(nom)
                continue
            }
            if initial {
                connus.insert(nom)
                continue
            }
            if aIgnorer.remove(nom) != nil {
                connus.insert(nom)
                continue
            }
            // Stable : même taille et même date de modification pendant au moins 0,8 s.
            let signature = "\(v?.fileSize ?? -1)|\(v?.contentModificationDate?.timeIntervalSince1970 ?? 0)"
            if let avant = enAttente[nom], avant.signature == signature, Date().timeIntervalSince(avant.depuis) >= 0.8 {
                enAttente[nom] = nil
                connus.insert(nom)
                juger(url, taille: v?.fileSize.map(Int64.init))
            } else {
                if enAttente[nom]?.signature != signature { enAttente[nom] = (signature, Date()) }
                encoreEnAttente = true
            }
        }
        if encoreEnAttente {
            relevePrevu = true
            file.asyncAfter(deadline: .now() + 1) { [self] in
                relevePrevu = false
                _ = releve(initial: false)
            }
        }
        return true
    }

    private func juger(_ url: URL, taille: Int64?) {
        let provenance = Provenance.lire(quarantaine: Self.attribut(url, "com.apple.quarantine"),
                                         ouVient: Self.ouVient(url))
        let structure = StructureFichier.inspecter(url)
        let verdict = regle.analyser(nom: url.lastPathComponent, provenance: provenance, structure: structure)
        guard verdict.alerte else {
            journal("téléchargement sans risque relevé (\(verdict.typeFichier), \(provenance.canal.rawValue))")
            return
        }
        let signale = FichierSignale(id: Avertissement.nouvelIdentifiant(), url: url,
                                     nom: Self.nomAffichable(url.lastPathComponent), taille: taille,
                                     provenance: provenance, verdict: verdict,
                                     empreinte: StructureFichier.empreinte(url))
        journal("téléchargement à risque : \(verdict.typeFichier), motifs \(verdict.motifs.map(\.rawValue).joined(separator: ","))")
        DispatchQueue.main.async { [weak self] in self?.surSignalement?(signale) }
    }

    private func changerEtat(_ nouvel: Etat) {
        guard etat != nouvel else { return }
        etat = nouvel
        DispatchQueue.main.async { [weak self] in self?.surEtat?(nouvel) }
    }

    // MARK: Attributs étendus

    /// Valeur texte d'un attribut étendu, ou nil s'il est absent.
    static func attribut(_ url: URL, _ nom: String) -> String? {
        donneesAttribut(url, nom).flatMap { String(data: $0, encoding: .utf8) }
    }

    static func donneesAttribut(_ url: URL, _ nom: String) -> Data? {
        url.withUnsafeFileSystemRepresentation { chemin -> Data? in
            guard let chemin else { return nil }
            let taille = getxattr(chemin, nom, nil, 0, 0, XATTR_NOFOLLOW)
            guard taille > 0, taille < 1 << 20 else { return nil }
            var tampon = Data(count: taille)
            let lu = tampon.withUnsafeMutableBytes { getxattr(chemin, nom, $0.baseAddress, taille, 0, XATTR_NOFOLLOW) }
            return lu > 0 ? tampon.prefix(lu) : nil
        }
    }

    /// `kMDItemWhereFroms` : liste d'origines, en plist binaire. Seul le domaine en sera gardé.
    static func ouVient(_ url: URL) -> [String] {
        guard let d = donneesAttribut(url, "com.apple.metadata:kMDItemWhereFroms"),
              let liste = try? PropertyListSerialization.propertyList(from: d, format: nil) as? [Any] else { return [] }
        return liste.compactMap { $0 as? String }
    }

    static func nomAffichable(_ nom: String) -> String {
        let interdits: Set<UInt32> = [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0x200E, 0x200F]
        let propre = nom.unicodeScalars.map { s -> String in
            if interdits.contains(s.value) { return "⟨⟩" }
            return CharacterSet.controlCharacters.contains(s) ? " " : String(s)
        }.joined()
        return Avertissement.nettoyer(propre, max: 90)
    }
}

/// Mise de côté réversible : le fichier part dans « Dédale - mis de côté », à côté de son
/// dossier d'origine, et le journal local (`mis-de-cote.json`) garde de quoi le remettre.
/// Les chemins restent sur le Mac.
final class MiseDeCote {
    struct Entree {
        let id: String
        let nom: String
        let origine: URL
        let actuel: URL
        let date: Date
    }

    private static let fichier = "mis-de-cote.json"
    private(set) var entrees: [Entree] = []

    init() {
        let brut = DossierEtat.lire(Self.fichier) as? [[String: Any]] ?? []
        entrees = brut.compactMap { d in
            guard let id = d["id"] as? String, let nom = d["nom"] as? String,
                  let o = d["origine"] as? String, let a = d["actuel"] as? String,
                  let t = d["date"] as? Double else { return nil }
            let e = Entree(id: id, nom: nom, origine: URL(fileURLWithPath: o), actuel: URL(fileURLWithPath: a),
                           date: Date(timeIntervalSince1970: t))
            return FileManager.default.fileExists(atPath: e.actuel.path) ? e : nil
        }
    }

    func mettreDeCote(_ f: FichierSignale) throws -> Entree {
        let dossier = f.url.deletingLastPathComponent()
            .appendingPathComponent(SurveillanceTelechargements.nomMisDeCote, isDirectory: true)
        try FileManager.default.createDirectory(at: dossier, withIntermediateDirectories: true)
        let cible = Self.libre(dossier.appendingPathComponent(f.url.lastPathComponent))
        try FileManager.default.moveItem(at: f.url, to: cible)
        let e = Entree(id: f.id, nom: f.nom, origine: f.url, actuel: cible, date: Date())
        entrees.append(e)
        enregistrer()
        return e
    }

    /// Remet le fichier à sa place d'origine (avec « (2) » si le nom est repris entre-temps).
    @discardableResult
    func remettre(_ id: String) throws -> URL? {
        guard let i = entrees.firstIndex(where: { $0.id == id }) else { return nil }
        let e = entrees[i]
        let cible = Self.libre(e.origine)
        try FileManager.default.moveItem(at: e.actuel, to: cible)
        entrees.remove(at: i)
        enregistrer()
        return cible
    }

    private func enregistrer() {
        DossierEtat.ecrire(entrees.map {
            ["id": $0.id, "nom": $0.nom, "origine": $0.origine.path, "actuel": $0.actuel.path,
             "date": $0.date.timeIntervalSince1970] as [String: Any]
        }, nom: Self.fichier)
    }

    /// `url` si le nom est libre, sinon « nom (2).ext », « nom (3).ext »…
    static func libre(_ url: URL) -> URL {
        guard FileManager.default.fileExists(atPath: url.path) else { return url }
        let dossier = url.deletingLastPathComponent()
        let ext = url.pathExtension
        let base = url.deletingPathExtension().lastPathComponent
        for n in 2...999 {
            let nom = ext.isEmpty ? "\(base) (\(n))" : "\(base) (\(n)).\(ext)"
            let essai = dossier.appendingPathComponent(nom)
            if !FileManager.default.fileExists(atPath: essai.path) { return essai }
        }
        return dossier.appendingPathComponent(UUID().uuidString + "-" + url.lastPathComponent)
    }
}
