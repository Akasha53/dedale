import Darwin
import Foundation
import Network

struct ReponseHTTP {
    let code: Int
    let corps: [String: Any]

    static func erreur(_ code: Int, _ texte: String) -> ReponseHTTP {
        ReponseHTTP(code: code, corps: ["erreur": texte])
    }
}

/// Requête HTTP/1.1 minimale : une ligne de requête, des en-têtes, un corps à Content-Length.
struct Requete {
    static let tailleMax = 64 * 1024

    let methode: String
    let chemin: String
    let entetes: [String: String]
    let corps: Data

    enum Lecture {
        case incomplete
        case invalide
        case complete(Requete)
    }

    static func lire(_ d: Data) -> Lecture {
        guard let fin = d.range(of: Data("\r\n\r\n".utf8)) else { return .incomplete }
        guard let tete = String(data: d.subdata(in: d.startIndex..<fin.lowerBound), encoding: .utf8) else {
            return .invalide
        }
        var lignes = tete.components(separatedBy: "\r\n")
        let premiere = lignes.removeFirst().split(separator: " ")
        guard premiere.count >= 2 else { return .invalide }

        var entetes: [String: String] = [:]
        for ligne in lignes {
            guard let i = ligne.firstIndex(of: ":") else { continue }
            let nom = ligne[..<i].trimmingCharacters(in: .whitespaces).lowercased()
            entetes[nom] = ligne[ligne.index(after: i)...].trimmingCharacters(in: .whitespaces)
        }
        guard let longueur = Int(entetes["content-length"] ?? "0"), longueur >= 0, longueur <= tailleMax else {
            return .invalide
        }
        let debut = fin.upperBound
        guard d.endIndex - debut >= longueur else { return .incomplete }

        var chemin = String(premiere[1])
        if let q = chemin.firstIndex(of: "?") { chemin = String(chemin[..<q]) }
        return .complete(Requete(
            methode: String(premiere[0]).uppercased(),
            chemin: chemin,
            entetes: entetes,
            corps: d.subdata(in: debut..<(debut + longueur))
        ))
    }
}

/// Petit serveur HTTP sur 127.0.0.1:8712, pour la démo seulement. Il reçoit les gestes
/// envoyés par le simulateur `poste/` (ou un curl) et ne lit rien d'autre sur le Mac.
final class ServeurLocal {
    /// 8712 par défaut ; `DEDALE_PORT_LOCAL` en choisit un autre (tests isolés).
    static let port: UInt16 = UInt16(ProcessInfo.processInfo.environment["DEDALE_PORT_LOCAL"] ?? "") ?? 8712

    /// Appelé sur le fil principal à chaque `POST /avertir` valide.
    var surAvertissement: ((Avertissement) -> ReponseHTTP)?
    /// Appelé sur le fil principal pour `GET /etat`.
    var surEtat: (() -> [String: Any])?
    /// Appelé sur le fil principal : `true` quand l'écoute est prête, `false` si elle échoue.
    var surEcoute: ((Bool) -> Void)?

    private let file = DispatchQueue(label: "dedale.serveur")
    private var ecoute: NWListener?

    func demarrer() {
        if Self.portOccupe(Self.port) {
            journal("port \(Self.port) déjà pris par un autre programme, alertes locales coupées")
            signalerEcoute(false)
            return
        }
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        params.requiredLocalEndpoint = .hostPort(host: "127.0.0.1", port: NWEndpoint.Port(rawValue: Self.port)!)
        let ecoute: NWListener
        do {
            ecoute = try NWListener(using: params)
        } catch {
            journal("écoute impossible : \(error)")
            signalerEcoute(false)
            return
        }
        ecoute.stateUpdateHandler = { [weak self] etat in
            switch etat {
            case .ready:
                journal("écoute sur 127.0.0.1:\(Self.port)")
                self?.signalerEcoute(true)
            case .failed(let e):
                journal("écoute en échec : \(e)")
                self?.signalerEcoute(false)
                ecoute.cancel()
            default:
                break
            }
        }
        ecoute.newConnectionHandler = { [weak self] connexion in self?.accueillir(connexion) }
        ecoute.start(queue: file)
        self.ecoute = ecoute
    }

    private func signalerEcoute(_ ok: Bool) {
        DispatchQueue.main.async { self.surEcoute?(ok) }
    }

    // MARK: - Connexions

    private final class Tampon { var donnees = Data() }

    private func accueillir(_ c: NWConnection) {
        c.start(queue: file)
        // Une connexion lente ou muette est coupée au bout de 5 s.
        file.asyncAfter(deadline: .now() + 5) { c.cancel() }
        recevoir(c, Tampon())
    }

    private func recevoir(_ c: NWConnection, _ t: Tampon) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 16 * 1024) { [weak self] data, _, termine, erreur in
            guard let self else { c.cancel(); return }
            if let data { t.donnees.append(data) }
            if t.donnees.count > Requete.tailleMax + 8 * 1024 {
                self.repondre(c, .erreur(413, "requête trop grosse"))
                return
            }
            switch Requete.lire(t.donnees) {
            case .incomplete:
                if termine || erreur != nil { c.cancel() } else { self.recevoir(c, t) }
            case .invalide:
                self.repondre(c, .erreur(400, "requête HTTP illisible"))
            case .complete(let r):
                self.traiter(r, c)
            }
        }
    }

    private func traiter(_ r: Requete, _ c: NWConnection) {
        // Seul un outil local (simulateur, curl) parle à ce port. Une page web ne doit pas
        // pouvoir afficher une fausse alerte : on refuse tout hôte inattendu (DNS rebinding)
        // et toute requête qui porte les en-têtes d'un navigateur.
        let hote = (r.entetes["host"] ?? "").lowercased()
        guard ["127.0.0.1:\(Self.port)", "localhost:\(Self.port)", "127.0.0.1", "localhost"].contains(hote) else {
            repondre(c, .erreur(403, "hôte refusé"))
            return
        }
        if r.entetes["origin"] != nil || r.entetes["sec-fetch-site"] != nil || r.entetes["sec-fetch-mode"] != nil {
            repondre(c, .erreur(403, "requête de navigateur refusée"))
            return
        }

        switch (r.methode, r.chemin) {
        case ("GET", "/etat"):
            DispatchQueue.main.async {
                let etat = self.surEtat?() ?? [:]
                self.file.async { self.repondre(c, ReponseHTTP(code: 200, corps: etat)) }
            }
        case ("POST", "/avertir"):
            let a: Avertissement
            do {
                a = try Avertissement.lire(r.corps)
            } catch {
                repondre(c, .erreur(400, "\(error)"))
                return
            }
            DispatchQueue.main.async {
                let rep = self.surAvertissement?(a) ?? .erreur(503, "application pas prête")
                self.file.async { self.repondre(c, rep) }
            }
        case (_, "/etat"), (_, "/avertir"):
            repondre(c, .erreur(405, "méthode non prise en charge"))
        default:
            repondre(c, .erreur(404, "chemin inconnu (POST /avertir, GET /etat)"))
        }
    }

    private func repondre(_ c: NWConnection, _ rep: ReponseHTTP) {
        let corps = (try? JSONSerialization.data(withJSONObject: rep.corps, options: [.sortedKeys, .withoutEscapingSlashes]))
            ?? Data("{}".utf8)
        let raisons = [200: "OK", 202: "Accepted", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
                       405: "Method Not Allowed", 413: "Payload Too Large", 429: "Too Many Requests",
                       503: "Service Unavailable"]
        let tete = "HTTP/1.1 \(rep.code) \(raisons[rep.code] ?? "OK")\r\n"
            + "Content-Type: application/json; charset=utf-8\r\n"
            + "Content-Length: \(corps.count)\r\n"
            + "Connection: close\r\n\r\n"
        c.send(content: Data(tete.utf8) + corps, completion: .contentProcessed { _ in c.cancel() })
    }

    /// Vrai si quelque chose écoute déjà sur 127.0.0.1:port (une autre instance, un autre outil).
    private static func portOccupe(_ port: UInt16) -> Bool {
        let s = socket(AF_INET, SOCK_STREAM, 0)
        guard s >= 0 else { return false }
        defer { close(s) }
        var adresse = sockaddr_in()
        adresse.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        adresse.sin_family = sa_family_t(AF_INET)
        adresse.sin_port = port.bigEndian
        adresse.sin_addr.s_addr = inet_addr("127.0.0.1")
        let resultat = withUnsafePointer(to: &adresse) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                connect(s, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return resultat == 0
    }
}
