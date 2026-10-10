import Foundation

/// Client du backend Dédale (console SOC, port 8700). Chaque appel est borné à quelques
/// secondes et un échec ne fait que renvoyer `false` : l'application ne tombe jamais si
/// le backend est absent (contrat, « Si le backend ne répond pas »).
final class Backend {
    let base: URL
    private let session: URLSession
    private let horloge: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = .current
        return f
    }()

    init() {
        let brut = ProcessInfo.processInfo.environment["DEDALE_BACKEND"] ?? "http://127.0.0.1:8700"
        base = URL(string: brut) ?? URL(string: "http://127.0.0.1:8700")!
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 2
        conf.timeoutIntervalForResource = 3
        conf.waitsForConnectivity = false
        session = URLSession(configuration: conf)
    }

    /// Sonde `GET /api/mesures`. `fin` est appelé sur le fil principal.
    func sonder(_ fin: @escaping (Bool) -> Void) {
        let url = base.appendingPathComponent("api/mesures")
        session.dataTask(with: url) { _, reponse, erreur in
            let ok = erreur == nil && (200..<300).contains((reponse as? HTTPURLResponse)?.statusCode ?? 0)
            DispatchQueue.main.async { fin(ok) }
        }.resume()
    }

    /// Envoie l'événement `avertissement` portant le choix du salarié (avenant « humain »).
    /// `fin(true)` si le backend l'a reçu.
    func envoyerChoix(_ a: Avertissement, choix: String, fin: @escaping (Bool) -> Void) {
        // `message` = texte exact de la pop-up. Le backend le neutralise avant stockage,
        // comme `cible` et `lien` ; on n'invente pas d'autre champ de texte libre.
        let texte = a.detail.isEmpty ? a.message : "\(a.message) \(a.detail)"
        var details: [String: Any] = [
            "categorie": a.categorie,
            "choix": choix,
            "message": texte,
            "origine": "app-mac",
        ]
        if let g = a.gravite { details["gravite"] = g }
        if let c = a.cible { details["cible"] = c }
        if let l = a.lien { details["lien"] = l }

        let corps: [String: Any] = [
            "horodatage": horloge.string(from: Date()),
            "source": "humain",
            "surface": "poste",
            "type": "avertissement",
            "session_id": a.sessionId,
            "leurre_id": NSNull(),
            "ip": "127.0.0.1",
            "user_agent": "dedale-mac/0.1",
            "methode": NSNull(),
            "chemin": NSNull(),
            "outil": NSNull(),
            "details": details,
        ]
        guard let donnees = try? JSONSerialization.data(withJSONObject: corps) else {
            DispatchQueue.main.async { fin(false) }
            return
        }
        var requete = URLRequest(url: base.appendingPathComponent("api/evenements"))
        requete.httpMethod = "POST"
        requete.setValue("application/json", forHTTPHeaderField: "Content-Type")
        requete.httpBody = donnees
        session.dataTask(with: requete) { _, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            let ok = erreur == nil && (200..<300).contains(code)
            if ok {
                journal("événement envoyé au backend (choix=\(choix), session=\(a.sessionId))")
            } else {
                journal("backend injoignable, événement non remonté (\(erreur?.localizedDescription ?? "HTTP \(code)"))")
            }
            DispatchQueue.main.async { fin(ok) }
        }.resume()
    }
}
