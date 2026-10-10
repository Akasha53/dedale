import Foundation

/// Compte les pièges évités (chaque « Annuler ») et dit combien depuis lundi. Rien ne sort du
/// poste : les dates sont dans un petit fichier JSON local, celles de plus de 60 jours partent.
/// `DEDALE_ETAT` choisit le dossier (utile pour les tests).
final class Compteur {
    private let fichier: URL
    private var dates: [Date] = []

    init() {
        let dossier: URL
        if let brut = ProcessInfo.processInfo.environment["DEDALE_ETAT"], !brut.isEmpty {
            dossier = URL(fileURLWithPath: brut)
        } else {
            let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
                ?? URL(fileURLWithPath: NSTemporaryDirectory())
            dossier = support.appendingPathComponent("Dedale")
        }
        fichier = dossier.appendingPathComponent("pieges-evites.json")
        if let donnees = try? Data(contentsOf: fichier),
           let secondes = try? JSONDecoder().decode([Double].self, from: donnees) {
            dates = secondes.map { Date(timeIntervalSince1970: $0) }
        }
    }

    func ajouter(_ date: Date = Date()) {
        let limite = date.addingTimeInterval(-60 * 24 * 3600)
        dates = dates.filter { $0 > limite } + [date]
        do {
            try FileManager.default.createDirectory(at: fichier.deletingLastPathComponent(), withIntermediateDirectories: true)
            let donnees = try JSONEncoder().encode(dates.map { $0.timeIntervalSince1970 })
            try donnees.write(to: fichier, options: .atomic)
        } catch {
            journal("compteur non enregistré : \(error.localizedDescription)")
        }
    }

    /// Pièges évités depuis lundi 0 h (semaine française).
    func cetteSemaine(_ maintenant: Date = Date()) -> Int {
        var calendrier = Calendar(identifier: .gregorian)
        calendrier.firstWeekday = 2
        calendrier.minimumDaysInFirstWeek = 4
        guard let semaine = calendrier.dateInterval(of: .weekOfYear, for: maintenant) else { return 0 }
        return dates.filter { semaine.contains($0) }.count
    }

    static func libelle(_ n: Int) -> String {
        switch n {
        case 0: return "Aucun piège évité cette semaine"
        case 1: return "1 piège évité cette semaine"
        default: return "\(n) pièges évités cette semaine"
        }
    }
}
