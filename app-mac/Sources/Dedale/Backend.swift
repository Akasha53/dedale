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
    /// `extra` complète `details` (quatre yeux). `fin(true)` si le backend l'a reçu.
    func envoyerChoix(_ a: Avertissement, choix: String, sessionId: String? = nil,
                      extra: [String: Any] = [:], fin: @escaping (Bool) -> Void) {
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
        if let g = a.geste { details["geste"] = g }
        if let m = a.mail { details["mail_id"] = Avertissement.identifiantSur(m.id) }
        details.merge(extra) { _, nouveau in nouveau }
        envoyer(type: "avertissement", sessionId: sessionId ?? a.sessionId, details: details) { ok in
            if ok { journal("événement envoyé au backend (choix=\(choix), session=\(sessionId ?? a.sessionId))") }
            fin(ok)
        }
    }

    /// Signalement d'un mail suspect par le salarié (section « app Mac » de CONTRATS.md).
    /// Le texte libre ne passe que par des champs que le backend neutralise (`message`,
    /// `cible`) ou désarme (`document_source`).
    func envoyerSignalement(_ m: MailResume, complet: MailComplet?, verdict: VerdictMail?,
                            fin: @escaping (Bool) -> Void) {
        let id = Avertissement.identifiantSur(m.id)
        var details: [String: Any] = [
            "origine": "app-mac",
            "mail_id": id,
            "message": "Mail signalé par le salarié : « \(m.objet) »",
            "verdict_analyseur": verdict.map { $0.statut ?? ($0.frauduleux ? "frauduleux" : "inconnu") } ?? "inconnu",
        ]
        if !m.expediteur.isEmpty { details["cible"] = m.expediteur }
        var doc: [String: Any] = [
            "type": "mail",
            "id": id,
            "titre": m.objet,
            "origine": "externe",
            "corps": complet?.corps ?? "",
        ]
        if !m.expediteur.isEmpty { doc["expediteur"] = m.expediteur }
        if let dest = complet?.destinataire, !dest.isEmpty { doc["destinataire"] = dest }
        if let date = m.date { doc["date"] = date }
        details["document_source"] = doc
        envoyer(type: "signalement", sessionId: "poste-mac-signalement-\(id)", details: details) { ok in
            journal(ok ? "signalement envoyé (mail \(id))" : "signalement non remonté (mail \(id))")
            fin(ok)
        }
    }

    /// Événement libre sur la surface `poste`. `fin` est appelé sur le fil principal.
    func envoyer(type: String, sessionId: String, details: [String: Any], fin: @escaping (Bool) -> Void) {
        let corps: [String: Any] = [
            "horodatage": horloge.string(from: Date()),
            "source": "humain",
            "surface": "poste",
            "type": type,
            "session_id": sessionId,
            "leurre_id": NSNull(),
            "ip": "127.0.0.1",
            "user_agent": "dedale-mac/0.2",
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
            if !ok {
                journal("backend injoignable, événement \(type) non remonté (\(erreur?.localizedDescription ?? "HTTP \(code)"))")
            }
            DispatchQueue.main.async { fin(ok) }
        }.resume()
    }

    /// Décisions déjà prises sur l'incident ouvert pour cette session (`GET /api/incidents`).
    /// `fin(nil)` si le backend ne répond pas ou si l'incident n'existe pas encore.
    func decisions(session sid: String, fin: @escaping ([String]?) -> Void) {
        session.dataTask(with: base.appendingPathComponent("api/incidents")) { donnees, reponse, erreur in
            var actions: [String]?
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            if erreur == nil, (200..<300).contains(code), let donnees,
               let json = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any],
               let liste = json["incidents"] as? [[String: Any]],
               let inc = liste.first(where: { ($0["session_id"] as? String) == sid }) {
                actions = (inc["decisions"] as? [[String: Any]] ?? []).compactMap { $0["action"] as? String }
            }
            DispatchQueue.main.async { fin(actions) }
        }.resume()
    }
}
