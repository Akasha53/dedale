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

    private static let groupe = #"(\d{1,3}(?:[ \x{00A0}\x{202F}.]\d{3})+|\d{1,12})"#

    public static func volume(dans texte: String) -> Int? {
        nombre(dans: texte, motif: groupe + #"\s*(?:fiches|clients|lignes|contacts|enregistrements)"#)
    }

    public static func montant(dans texte: String) -> Int? {
        nombre(dans: texte, motif: groupe + #"(?:,\d{1,2})?\s*(?:€|euros?\b|eur\b)"#)
    }

    private static func nombre(dans texte: String, motif: String) -> Int? {
        guard let re = try? NSRegularExpression(pattern: motif, options: [.caseInsensitive]),
              let m = re.firstMatch(in: texte, range: NSRange(texte.startIndex..., in: texte)),
              let r = Range(m.range(at: 1), in: texte) else { return nil }
        let chiffres = texte[r].filter(\.isNumber)
        guard chiffres.count <= 12, let n = Int(chiffres) else { return nil }
        return n
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
