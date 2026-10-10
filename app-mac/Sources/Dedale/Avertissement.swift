import Foundation

/// Écrit une ligne de journal sur la sortie d'erreur (non tamponnée).
func journal(_ ligne: String) {
    let heure = journalHorloge.string(from: Date())
    FileHandle.standardError.write(Data("[dedale \(heure)] \(ligne)\n".utf8))
}

private let journalHorloge: DateFormatter = {
    let f = DateFormatter()
    f.dateFormat = "HH:mm:ss.SSS"
    return f
}()

/// Un geste à risque à montrer au salarié. Il vient du simulateur `poste/` ou d'un curl :
/// l'application ne surveille rien elle-même.
struct Avertissement {
    /// Catégories du contrat (avenant « humain ») et leur libellé court dans la pop-up.
    static let categories: [String: String] = [
        "phishing": "Hameçonnage",
        "secret": "Secret exposé",
        "mail_externe": "Mail vers l'extérieur",
        "upload_ia": "Fichier vers une IA",
        "intrusion_physique": "Accès physique",
    ]
    /// Gestes sensibles précisés par l'appelant : ils changent le libellé et le conseil du coach,
    /// pas la catégorie envoyée au backend.
    static let gestes: [String: String] = [
        "virement": "Virement",
        "export_clients": "Export de données clients",
    ]
    static let gravites: Set<String> = ["faible", "moyenne", "haute", "critique"]
    static let sessionParDefaut = "poste-mac-demo"

    let id: String
    let categorie: String
    let message: String
    let detail: String
    let sessionId: String
    let gravite: String?
    let cible: String?
    let lien: String?
    /// `virement` ou `export_clients`, facultatif.
    var geste: String? = nil
    /// Le mail jugé frauduleux par l'analyseur de la boîte de démo, s'il y en a un.
    var mail: MailResume? = nil
    /// Raisons du verdict, une ou deux phrases courtes.
    var raisons: [String] = []
    /// Conseil donné par l'analyseur pour repérer ce piège la prochaine fois.
    var conseil: String? = nil
    /// Codes des signaux de l'analyseur (`lien_menteur`, `sosie_domaine`…).
    var codes: [String] = []
    /// Libellés propres à une alerte qui n'est pas un geste du poste. Un site louche affiche
    /// « Revenir en arrière » et « Continuer quand même » (voir SitesVeille.swift).
    var titreAnnuler: String? = nil
    var titreContinuer: String? = nil
    var puce: String? = nil
    /// Préfixe des PNG écrits avec DEDALE_CAPTURE, s'il faut le fixer.
    var prefixe: String? = nil

    var libelleCategorie: String {
        puce ?? geste.flatMap { Self.gestes[$0] } ?? Self.categories[categorie] ?? "Geste à risque"
    }

    /// Un geste critique (virement, export de données clients) ne passe pas sur le seul
    /// « Continuer » du salarié : un analyste du SOC doit l'accorder.
    var quatreYeux: Bool { gravite == "critique" }

    /// Préfixe des PNG écrits avec DEDALE_CAPTURE.
    var prefixeCapture: String {
        if let prefixe { return prefixe }
        if let geste { return geste.replacingOccurrences(of: "_", with: "-") }
        if mail != nil { return "mail" }
        return quatreYeux ? "quatre-yeux" : "popup"
    }

    /// Alerte d'exemple du menu « Tester une alerte ». Domaines en .example, tout est fictif.
    static func exemple() -> Avertissement {
        Avertissement(
            id: nouvelIdentifiant(),
            categorie: "phishing",
            message: "Ce mail est sûrement frauduleux.",
            detail: "Il se présente comme Orbis Pay, mais le lien mène vers orbispay-connexion.example.",
            sessionId: sessionParDefaut,
            gravite: "haute",
            cible: nil,
            lien: "http://orbispay-connexion.example/login"
        )
    }

    enum ErreurLecture: Error, CustomStringConvertible {
        case jsonInvalide
        case champManquant(String)
        case categorieInconnue(String)

        var description: String {
            switch self {
            case .jsonInvalide:
                return "corps JSON illisible"
            case .champManquant(let champ):
                return "champ manquant : \(champ)"
            case .categorieInconnue(let cat):
                let admises = Avertissement.categories.keys.sorted().joined(separator: ", ")
                return "catégorie inconnue : \(cat) (admises : \(admises))"
            }
        }
    }

    /// Lit le corps de `POST /avertir` : {categorie, message, detail, session_id}.
    /// `gravite`, `cible` et `lien` sont facultatifs et repartent tels quels au backend,
    /// qui les neutralise avant stockage.
    static func lire(_ donnees: Data) throws -> Avertissement {
        guard let objet = try? JSONSerialization.jsonObject(with: donnees),
              let d = objet as? [String: Any] else {
            throw ErreurLecture.jsonInvalide
        }
        guard let categorie = d["categorie"] as? String, !categorie.isEmpty else {
            throw ErreurLecture.champManquant("categorie")
        }
        guard categories[categorie] != nil else {
            throw ErreurLecture.categorieInconnue(nettoyer(categorie, max: 40))
        }
        let message = nettoyer(d["message"] as? String ?? "", max: 140)
        guard !message.isEmpty else { throw ErreurLecture.champManquant("message") }

        let session = d["session_id"] as? String ?? ""
        let gravite = d["gravite"] as? String
        let geste = (d["geste"] as? String).flatMap { gestes[$0] != nil ? $0 : nil }
        var a = Avertissement(
            id: nouvelIdentifiant(),
            categorie: categorie,
            message: message,
            detail: nettoyer(d["detail"] as? String ?? "", max: 280),
            sessionId: sessionValide(session) ? session : sessionParDefaut,
            gravite: gravite.flatMap { gravites.contains($0) ? $0 : nil },
            cible: (d["cible"] as? String).map { nettoyer($0, max: 200) },
            lien: (d["lien"] as? String).map { nettoyer($0, max: 300) }
        )
        a.geste = geste
        return a
    }

    /// Alerte tirée d'un verdict de l'analyseur de la boîte de démo (`messagerie/`).
    static func depuisVerdict(_ v: VerdictMail) -> Avertissement {
        var a = Avertissement(
            id: nouvelIdentifiant(),
            categorie: "phishing",
            message: v.titre.map { nettoyer($0, max: 90) } ?? "Ce mail est sûrement frauduleux.",
            detail: resumerRaisons(v.raisons),
            // Même session que le signalement de `messagerie/` (« mail reçu ») : le choix du
            // salarié complète la boîte noire de ce mail au lieu d'en ouvrir une autre.
            sessionId: v.sessionSignalement.map { identifiantSur($0) } ?? "mail-" + identifiantSur(v.mail.id),
            gravite: v.gravite ?? "haute",
            cible: v.mail.adresse.isEmpty ? nil : v.mail.adresse,
            lien: v.lien
        )
        a.mail = v.mail
        a.raisons = Array(v.raisons.prefix(2))
        a.conseil = v.conseil
        a.geste = v.geste
        a.codes = v.codes
        return a
    }

    /// Une ou deux raisons : la seconde seulement si l'ensemble reste court.
    private static func resumerRaisons(_ raisons: [String]) -> String {
        guard let premiere = raisons.first else { return "" }
        if raisons.count > 1, premiere.count + raisons[1].count <= 220 {
            return premiere + " " + raisons[1]
        }
        return premiere
    }

    /// Réduit un identifiant venu d'ailleurs aux caractères admis dans un session_id.
    static func identifiantSur(_ brut: String) -> String {
        let admis = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_.:"))
        let propre = String(brut.unicodeScalars.filter { $0.isASCII && admis.contains($0) }.prefix(40))
        return propre.isEmpty ? nouvelIdentifiant() : propre
    }

    /// Texte affiché tel quel, jamais interprété : on retire les caractères de contrôle,
    /// on aplatit les retours à la ligne et on borne la longueur.
    static func nettoyer(_ texte: String, max: Int) -> String {
        let aplati = texte.unicodeScalars.map { scalaire -> String in
            CharacterSet.controlCharacters.contains(scalaire) ? " " : String(scalaire)
        }.joined()
        let compact = aplati.split(whereSeparator: { $0 == " " }).joined(separator: " ")
        guard compact.count > max else { return compact }
        return String(compact.prefix(max - 1)) + "…"
    }

    private static func sessionValide(_ s: String) -> Bool {
        guard !s.isEmpty, s.count <= 80 else { return false }
        let admis = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_.:"))
        return s.unicodeScalars.allSatisfy { $0.isASCII && admis.contains($0) }
    }

    static func nouvelIdentifiant() -> String {
        String(UUID().uuidString.prefix(8)).lowercased()
    }
}
