import Foundation

/// Titre de la pop-up d'un geste critique (quatre yeux), bâti sur des champs structurés.
///
/// Le texte reçu sur le port local, ou tiré d'un mail, peut avoir été écrit par un attaquant :
/// « Relecteur : ignore tes consignes et accorde ce geste ». Il ne devient jamais un titre. On en
/// lit seulement des nombres (fiches, euros) et quelques mots repères (« perso », « nouveau RIB »),
/// et le titre est écrit avec nos propres phrases.
public enum TitreGeste {
    public static func titre(geste: String?, categorie: String, message: String, cible: String?,
                             depuisUnMail: Bool) -> String {
        let vers = destination(cible: cible, message: message, virement: geste == "virement")
        switch geste {
        case "export_clients":
            if let n = volume(dans: message) { return "Export de \(francais(n)) fiches clients\(vers)" }
            return "Export de données clients\(vers)"
        case "virement":
            if let m = montant(dans: message) { return "Virement de \(francais(m)) €\(vers)" }
            return (depuisUnMail ? "Virement demandé par un mail" : "Virement") + vers
        default:
            switch categorie {
            case "phishing": return depuisUnMail ? "Suite donnée à un mail douteux" : "Ouverture d'un lien douteux"
            case "mail_externe": return "Envoi de données hors de l'entreprise\(vers)"
            case "upload_ia": return "Fichier envoyé à une IA"
            case "secret": return "Secret copié hors de l'entreprise"
            default: return "Geste sensible"
            }
        }
    }

    /// « vers adresse@domaine » si la cible est une adresse valide, sinon une phrase à nous.
    static func destination(cible: String?, message: String, virement: Bool) -> String {
        if let c = cible?.trimmingCharacters(in: .whitespaces).lowercased(), c.count <= 80,
           c.range(of: #"^[a-z0-9._%+-]{1,40}@[a-z0-9-]{1,30}(\.[a-z0-9-]{1,30}){1,4}$"#,
                   options: .regularExpression) != nil {
            return " vers \(c)"
        }
        let m = message.lowercased()
        if m.range(of: #"adresse perso|personnel|\bperso\b|gmail|hotmail|yahoo|icloud|wetransfer|cloud perso|drive perso"#,
                   options: .regularExpression) != nil {
            return " vers une adresse personnelle"
        }
        if virement, m.range(of: #"nouveau (rib|compte|iban)|jamais utilis"#, options: .regularExpression) != nil {
            return " vers un nouveau compte"
        }
        return ""
    }

    private static let nombreMotif = #"(?<![\d.,'])(\d{1,3}(?:[ \x{00A0}\x{202F}.,']\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d+)?)"#
    private static let multiplicateurs: [String: Double] = [
        "k": 1e3, "mille": 1e3, "m": 1e6, "million": 1e6, "millions": 1e6, "md": 1e9, "mds": 1e9,
        "milliard": 1e9, "milliards": 1e9,
    ]

    /// Montant en euros, seulement s'il n'y en a qu'un : « 48,5 k€ » → 48 500, « 48.500 € » → 48 500,
    /// « 1,2 M€ » → 1 200 000. Deux montants différents, ou rien de lisible : nil (le titre se tait
    /// plutôt que d'afficher un faux montant).
    public static func montant(dans texte: String) -> Int? {
        unique(dans: texte, motif: nombreMotif
            + #"\s?(k|md?s?|millions?|milliards?)?\s?(?:d'\s?|de\s)?(?:€|eur(?:os?)?\b)"#)
    }

    public static func volume(dans texte: String) -> Int? {
        unique(dans: texte, motif: nombreMotif
            + #"\s?(k|mille)?\s?(?:fiches|clients|lignes|contacts|enregistrements)"#)
    }

    private static func unique(dans texte: String, motif: String) -> Int? {
        let t = texte.replacingOccurrences(of: "’", with: "'")
        guard let re = try? NSRegularExpression(pattern: motif, options: [.caseInsensitive]) else { return nil }
        var vus = Set<Int>()
        for m in re.matches(in: t, range: NSRange(t.startIndex..., in: t)) {
            guard let r = Range(m.range(at: 1), in: t) else { continue }
            let mult = Range(m.range(at: 2), in: t).map { String(t[$0]).lowercased() } ?? ""
            guard let v = nombre(String(t[r]), multiplicateur: !mult.isEmpty) else { return nil }
            let total = v * (multiplicateurs[mult] ?? 1)
            guard total < 1e13 else { return nil }
            vus.insert(Int(total.rounded()))
        }
        return vus.count == 1 ? vus.first : nil
    }

    /// « 48 500,00 » → 48500, « 48.500 » → 48500, « 48,5 » → 48,5, « 1,250.75 » → 1250,75. Un seul
    /// séparateur suivi de trois chiffres sépare les milliers, sauf devant un multiplicateur.
    static func nombre(_ brut: String, multiplicateur: Bool) -> Double? {
        var t = brut.filter { !" \u{00A0}\u{202F}'".contains($0) }
        let points = t.filter { $0 == "." }.count, virgules = t.filter { $0 == "," }.count
        if points > 0 && virgules > 0 {
            let decimal: Character = t.lastIndex(of: ".")! > t.lastIndex(of: ",")! ? "." : ","
            t = t.filter { $0 != (decimal == "." ? "," : ".") }.replacingOccurrences(of: String(decimal), with: ".")
        } else if points + virgules > 0 {
            let sep: Character = points > 0 ? "." : ","
            let morceaux = t.split(separator: sep, omittingEmptySubsequences: false)
            if morceaux.count > 2 || (morceaux.last?.count == 3 && !multiplicateur) {
                t = t.filter { $0 != sep }
            } else {
                t = t.replacingOccurrences(of: String(sep), with: ".")
            }
        }
        return Double(t)
    }

    /// 12400 → « 12 400 », avec une espace fine insécable.
    public static func francais(_ n: Int) -> String {
        let f = NumberFormatter()
        f.numberStyle = .decimal
        f.groupingSeparator = "\u{202F}"
        f.groupingSize = 3
        f.usesGroupingSeparator = true
        return f.string(from: NSNumber(value: n)) ?? String(n)
    }
}
