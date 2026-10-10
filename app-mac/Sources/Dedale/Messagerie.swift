import Foundation

/// Un mail de la boîte de démo, réduit à ce que le menu et la pop-up affichent.
struct MailResume: Equatable {
    let id: String
    let objet: String
    let expediteur: String
    let date: String?

    /// L'adresse seule (ce qui trahit un faux), sans le nom affiché.
    var adresse: String {
        guard let debut = expediteur.lastIndex(of: "<"), let fin = expediteur.lastIndex(of: ">"), debut < fin else {
            return expediteur
        }
        return String(expediteur[expediteur.index(after: debut)..<fin])
    }
}

/// Verdict de l'analyseur de `messagerie/` sur un mail.
struct VerdictMail {
    let mail: MailResume
    let frauduleux: Bool
    /// Verdict brut de l'analyseur (`sur`, `suspect`, `frauduleux`), s'il est donné en texte.
    let statut: String?
    /// Titre court de l'alerte, s'il est fourni (sinon la pop-up dit « Ce mail est sûrement frauduleux. »).
    let titre: String?
    let raisons: [String]
    let gravite: String?
    let lien: String?
    let conseil: String?
    /// `virement` quand le mail réclame un paiement.
    let geste: String?
    /// Session où `messagerie/` a déjà signalé ce mail au backend (`mail-<id>`), s'il l'a fait.
    let sessionSignalement: String?
    /// Codes des signaux relevés par l'analyseur, du plus lourd au plus léger.
    let codes: [String]
}

/// Un mail complet, pour l'aperçu désarmé.
struct MailComplet {
    let resume: MailResume
    let destinataire: String
    let corps: String
    /// Texte caché dans le mail (blanc sur blanc, taille nulle…), déjà relevé par l'analyseur.
    let cache: [String]
    /// Liens du mail : texte affiché, vraie destination, et s'ils mentent.
    let liens: [LienMail]
    /// Noms des pièces jointes (jamais ouvertes).
    let pieces: [String]
}

struct LienMail {
    let texte: String
    let destination: String
    let suspect: Bool
}

/// Client de la boîte mail de démo (`messagerie/`, port 8715 par défaut). Comme pour le
/// backend, chaque appel est borné à quelques secondes et un échec renvoie `nil` : sans la
/// boîte, l'app tient et le menu affiche « boîte de démo hors ligne ».
///
/// La lecture est tolérante : le contrat de `messagerie/` s'écrit en même temps que cette app,
/// donc on accepte plusieurs noms pour chaque champ (objet ou sujet, raisons en texte ou en
/// objets…). Le texte reçu n'est jamais interprété : il est nettoyé puis affiché tel quel.
final class Messagerie {
    let base: URL
    private let session: URLSession

    init() {
        let brut = ProcessInfo.processInfo.environment["DEDALE_MESSAGERIE"] ?? "http://127.0.0.1:8715"
        base = URL(string: brut) ?? URL(string: "http://127.0.0.1:8715")!
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 2
        conf.timeoutIntervalForResource = 3
        conf.waitsForConnectivity = false
        conf.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: conf)
    }

    // MARK: Requêtes

    /// `GET /verdicts`. `nil` si la boîte ne répond pas. Appelé sur le fil principal.
    func verdicts(_ fin: @escaping ([VerdictMail]?) -> Void) {
        lireJSON("verdicts") { json in
            fin(json.map { Self.liste($0, cles: ["verdicts", "items", "resultats"]).compactMap(Self.lireVerdict) })
        }
    }

    /// `GET /mails` (les derniers mails de la boîte). `nil` si la route manque ou ne répond pas.
    func mails(_ fin: @escaping ([MailResume]?) -> Void) {
        lireJSON("mails") { json in
            fin(json.map { Self.liste($0, cles: ["mails", "items", "boite", "verdicts"]).compactMap(Self.lireResume) })
        }
    }

    /// `GET /mails/{id}`. `nil` si le mail est introuvable ou la boîte absente.
    func mail(_ id: String, _ fin: @escaping (MailComplet?) -> Void) {
        let propre = id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
        lireJSON("mails/\(propre)") { json in
            guard var d = json as? [String: Any] else { fin(nil); return }
            if let m = d["mail"] as? [String: Any] { d.merge(m) { actuel, _ in actuel } }
            guard let resume = Self.lireResume(d) else { fin(nil); return }
            let corps = Self.texte(d, ["corps_desarme", "apercu", "corps", "texte", "contenu", "body"]) ?? ""
            let cache = (d["texte_cache"] as? [[String: Any]] ?? []).compactMap { Self.texte($0, ["texte"]) }
            let liens = (d["liens"] as? [[String: Any]] ?? []).compactMap { l -> LienMail? in
                guard let dest = Self.texte(l, ["destination", "url", "href"]) else { return nil }
                return LienMail(texte: Self.texte(l, ["texte", "libelle"]) ?? "", destination: dest,
                                suspect: l["suspect"] as? Bool ?? false)
            }
            let pieces = (d["pieces_jointes"] as? [[String: Any]] ?? []).compactMap { Self.texte($0, ["nom"]) }
            fin(MailComplet(resume: resume,
                            destinataire: Self.adresse(d, ["destinataire", "a", "to"]) ?? "",
                            corps: corps, cache: cache, liens: liens, pieces: pieces))
        }
    }

    private func lireJSON(_ chemin: String, _ fin: @escaping (Any?) -> Void) {
        guard let url = URL(string: chemin, relativeTo: base.appendingPathComponent("/")) else {
            fin(nil)
            return
        }
        session.dataTask(with: url) { donnees, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            var json: Any?
            if erreur == nil, (200..<300).contains(code), let donnees {
                json = try? JSONSerialization.jsonObject(with: donnees)
            }
            DispatchQueue.main.async { fin(json) }
        }.resume()
    }

    // MARK: Lecture tolérante

    private static let motsFraude: Set<String> = [
        "frauduleux", "fraude", "phishing", "hameconnage", "hameçonnage", "malveillant",
        "dangereux", "piege", "piégé", "arnaque",
    ]

    /// Signaux de l'analyseur qui font d'un mail une demande de paiement : le geste qui suit
    /// est un virement, donc critique (quatre yeux).
    private static let codesVirement: Set<String> = ["urgence_argent", "changement_bancaire"]

    private static func liste(_ json: Any, cles: [String]) -> [[String: Any]] {
        if let l = json as? [[String: Any]] { return l }
        if let d = json as? [String: Any] {
            for c in cles { if let l = d[c] as? [[String: Any]] { return l } }
        }
        return []
    }

    static func lireResume(_ brut: [String: Any]) -> MailResume? {
        var d = brut
        if let m = brut["mail"] as? [String: Any] { d.merge(m) { actuel, _ in actuel } }
        guard let id = texte(d, ["mail_id", "id", "identifiant"]), !id.isEmpty else { return nil }
        let objet = texte(d, ["objet", "sujet", "subject", "titre"]) ?? "(sans objet)"
        return MailResume(
            id: Avertissement.nettoyer(id, max: 60),
            objet: Avertissement.nettoyer(objet, max: 120),
            expediteur: Avertissement.nettoyer(adresse(d, ["expediteur", "de", "from", "emetteur"]) ?? "", max: 120),
            date: texte(d, ["recu_a", "recu_le", "date", "horodatage"]).map { Avertissement.nettoyer($0, max: 40) }
        )
    }

    static func lireVerdict(_ brut: [String: Any]) -> VerdictMail? {
        var d = brut
        if let v = brut["verdict"] as? [String: Any] { d.merge(v) { actuel, _ in actuel } }
        if let m = brut["mail"] as? [String: Any] { d.merge(m) { actuel, _ in actuel } }
        guard let mail = lireResume(d) else { return nil }

        var frauduleux = false
        let statut = texte(d, ["verdict", "statut", "classement"])
        // Seul « frauduleux » déclenche une alerte : un mail « suspect » reste dans la boîte.
        if let b = (d["frauduleux"] ?? d["est_frauduleux"] ?? d["fraude"]) as? Bool {
            frauduleux = b
        } else if let s = texte(d, ["verdict", "statut", "classement", "decision", "etiquette", "label"]) {
            frauduleux = motsFraude.contains(s.lowercased())
        } else if let score = (d["score"] as? NSNumber)?.doubleValue {
            frauduleux = (score > 1 ? score / 100 : score) >= 0.5
        }

        var raisons: [String] = []
        if let l = d["raisons"] as? [Any] {
            for r in l {
                if let s = r as? String { raisons.append(s) }
                else if let o = r as? [String: Any],
                        let s = texte(o, ["texte", "phrase", "explication", "detail", "message", "libelle"]) {
                    raisons.append(s)
                }
            }
        } else if let s = texte(d, ["raison_principale", "raisons", "raison", "explication", "pourquoi"]) {
            raisons.append(s)
        }
        raisons = raisons.map { phrase(Avertissement.nettoyer($0, max: 320)) }.filter { !$0.isEmpty }

        let codes = (d["signaux"] as? [[String: Any]] ?? []).compactMap { $0["code"] as? String }
        let paiement = !codesVirement.isDisjoint(with: codes)
        let geste = texte(d, ["geste", "categorie"]).flatMap { Avertissement.gestes[$0] != nil ? $0 : nil }
            ?? (paiement ? "virement" : nil)
        // Un virement ou un export de données clients est critique par nature : quatre yeux.
        let gravite = geste != nil ? "critique"
            : texte(d, ["gravite", "severite"]).flatMap { Avertissement.gravites.contains($0) ? $0 : nil }
        // Un titre distinct de l'objet du mail, sinon la pop-up garde sa phrase par défaut.
        let titre = texte(d, ["titre_alerte", "alerte", "resume_alerte"])
        return VerdictMail(
            mail: mail,
            frauduleux: frauduleux,
            statut: statut.map { Avertissement.identifiantSur($0) },
            titre: titre,
            raisons: raisons,
            gravite: gravite,
            lien: texte(d, ["lien_reel", "url_reelle", "lien", "url"]).map { Avertissement.nettoyer($0, max: 300) },
            // Le « conseil » général de l'analyseur ne dit pas comment repérer le piège :
            // le coach prend son repère dans les codes des signaux.
            conseil: texte(d, ["astuce", "a_retenir", "reperer"]).map { phrase(Avertissement.nettoyer($0, max: 160)) },
            geste: geste,
            sessionSignalement: (d["signalement"] as? [String: Any]).flatMap { texte($0, ["session_id"]) },
            codes: codes
        )
    }

    private static func texte(_ d: [String: Any], _ cles: [String]) -> String? {
        for c in cles {
            if let s = d[c] as? String, !s.trimmingCharacters(in: .whitespaces).isEmpty { return s }
            if let n = d[c] as? NSNumber, !(d[c] is Bool) { return n.stringValue }
        }
        return nil
    }

    /// Une adresse peut arriver en texte (« Nom <a@b> ») ou en objet {nom, adresse}.
    private static func adresse(_ d: [String: Any], _ cles: [String]) -> String? {
        for c in cles {
            if let s = d[c] as? String, !s.isEmpty { return s }
            if let o = d[c] as? [String: Any] {
                let nom = texte(o, ["nom", "name", "affiche"])
                let mel = texte(o, ["adresse", "email", "mail", "address"])
                switch (nom, mel) {
                case let (n?, m?): return "\(n) <\(m)>"
                case let (n?, nil): return n
                case let (nil, m?): return m
                default: continue
                }
            }
            if let l = d[c] as? [String], let premier = l.first { return premier }
        }
        return nil
    }

    /// Majuscule initiale et point final, pour qu'une raison se lise comme une phrase.
    private static func phrase(_ s: String) -> String {
        var t = s.trimmingCharacters(in: .whitespaces)
        guard let premiere = t.first else { return t }
        t = premiere.uppercased() + t.dropFirst()
        if let derniere = t.last, !".!?…".contains(derniere) { t += "." }
        return t
    }

    // MARK: Désarmement

    /// Rend un corps de mail inoffensif à l'affichage : balises HTML retirées, liens réécrits
    /// en `hxxp(s)://` avec les points du domaine en `[.]` et les paramètres masqués, adresses
    /// mail en `[.]`, caractères de contrôle supprimés, longueur bornée. Les sauts de ligne
    /// restent. Appliquer deux fois la fonction ne change plus rien.
    static func desarmer(_ brut: String, max: Int = 8000) -> String {
        var t = brut
        // HTML seulement si on voit de vraies balises : « Nom <adresse> » n'en est pas une.
        let balises = #"(?i)</?(html|head|body|p|div|span|a|br|img|table|tbody|tr|td|th|ul|ol|li|b|i|u|strong|em|font|style|script|h[1-6]|center|meta|link)\b[^>]*>"#
        if t.range(of: balises, options: .regularExpression) != nil {
            t = t.replacingOccurrences(of: #"(?is)<(script|style)\b.*?</\1>"#, with: "", options: .regularExpression)
            t = t.replacingOccurrences(of: #"(?i)<br\s*/?>|</p>|</div>|</li>"#, with: "\n", options: .regularExpression)
            t = t.replacingOccurrences(of: #"<[^>]*>"#, with: "", options: .regularExpression)
            for (entite, car) in [("&nbsp;", " "), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", "\""), ("&#39;", "'"), ("&amp;", "&")] {
                t = t.replacingOccurrences(of: entite, with: car)
            }
        }
        t = String(t.unicodeScalars.map { s -> Character in
            if s == "\n" || s == "\t" { return Character(s) }
            return CharacterSet.controlCharacters.contains(s) ? " " : Character(s)
        })
        t = remplacer(t, motif: #"(?i)\b(https?)://([A-Za-z0-9.-]+)([^\s<>"']*)"#) { g in
            let schema = g[1].lowercased() == "https" ? "hxxps" : "hxxp"
            let hote = g[2].replacingOccurrences(of: ".", with: "[.]")
            var reste = g[3]
            if let q = reste.firstIndex(of: "?") { reste = String(reste[..<q]) + "?[paramètres masqués]" }
            return "\(schema)://\(hote)\(reste)"
        }
        t = remplacer(t, motif: #"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)\b"#) { g in
            "\(g[1])@\(g[2].replacingOccurrences(of: ".", with: "[.]"))"
        }
        t = t.replacingOccurrences(of: #"\n{3,}"#, with: "\n\n", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard t.count > max else { return t }
        return String(t.prefix(max - 1)) + "…"
    }

    /// Désarme un texte court sur une ligne (objet, expéditeur).
    static func desarmerLigne(_ brut: String, max: Int = 160) -> String {
        Avertissement.nettoyer(desarmer(brut, max: max * 2), max: max)
    }

    private static func remplacer(_ texte: String, motif: String, _ f: ([String]) -> String) -> String {
        guard let re = try? NSRegularExpression(pattern: motif) else { return texte }
        let ns = texte as NSString
        var sortie = ""
        var curseur = 0
        for m in re.matches(in: texte, range: NSRange(location: 0, length: ns.length)) {
            sortie += ns.substring(with: NSRange(location: curseur, length: m.range.location - curseur))
            let groupes = (0..<m.numberOfRanges).map { i -> String in
                let r = m.range(at: i)
                return r.location == NSNotFound ? "" : ns.substring(with: r)
            }
            sortie += f(groupes)
            curseur = m.range.location + m.range.length
        }
        sortie += ns.substring(from: curseur)
        return sortie
    }
}

/// Abonnement au flux `GET /flux` (Server-Sent Events) de `messagerie/` : chaque nouveau
/// verdict arrive en moins d'une seconde. La connexion se rouvre seule après une coupure.
/// Le relevé de `GET /verdicts` toutes les 3 s reste le filet : il suffit si le flux manque.
final class FluxVerdicts: NSObject, URLSessionDataDelegate {
    var surVerdict: ((VerdictMail) -> Void)?
    var surEtat: ((Bool) -> Void)?

    private let url: URL
    private var session: URLSession?
    private var tampon = Data()
    private var actif = false
    private var refuse = false
    private(set) var connecte = false

    init(base: URL) {
        url = URL(string: "flux", relativeTo: base.appendingPathComponent("/")) ?? base
        super.init()
    }

    func demarrer() {
        guard !actif else { return }
        actif = true
        ouvrir()
    }

    private func ouvrir() {
        guard actif else { return }
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 45   // le service envoie un « ping » toutes les 15 s
        conf.timeoutIntervalForResource = 24 * 3600
        conf.waitsForConnectivity = false
        let s = URLSession(configuration: conf, delegate: self, delegateQueue: .main)
        session = s
        tampon = Data()
        var requete = URLRequest(url: url)
        requete.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        s.dataTask(with: requete).resume()
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        let ok = (response as? HTTPURLResponse)?.statusCode == 200
        refuse = !ok
        if ok != connecte {
            connecte = ok
            journal(ok ? "flux de verdicts ouvert" : "flux de verdicts refusé")
            surEtat?(ok)
        }
        completionHandler(ok ? .allow : .cancel)
    }

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        tampon.append(data)
        if tampon.count > 1_000_000 { tampon = Data(); return }
        let separateur = Data("\n\n".utf8)
        while let r = tampon.range(of: separateur) {
            let bloc = String(decoding: tampon.subdata(in: tampon.startIndex..<r.lowerBound), as: UTF8.self)
            tampon.removeSubrange(tampon.startIndex..<r.upperBound)
            traiter(bloc)
        }
    }

    private func traiter(_ bloc: String) {
        var evenement = "message"
        var donnees: [String] = []
        for ligne in bloc.split(separator: "\n", omittingEmptySubsequences: false) {
            if ligne.hasPrefix("event:") {
                evenement = ligne.dropFirst(6).trimmingCharacters(in: .whitespaces)
            } else if ligne.hasPrefix("data:") {
                donnees.append(String(ligne.dropFirst(5)).trimmingCharacters(in: .whitespaces))
            }
        }
        guard evenement == "verdict", !donnees.isEmpty,
              let json = try? JSONSerialization.jsonObject(with: Data(donnees.joined(separator: "\n").utf8)),
              let d = json as? [String: Any],
              let v = Messagerie.lireVerdict(d) else { return }
        surVerdict?(v)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if connecte {
            connecte = false
            journal("flux de verdicts coupé, nouvel essai dans 3 s")
            surEtat?(false)
        }
        session.finishTasksAndInvalidate()
        // Route absente (ancien service) : on réessaie moins souvent.
        let delai: Double = refuse ? 30 : 3
        refuse = false
        DispatchQueue.main.asyncAfter(deadline: .now() + delai) { [weak self] in self?.ouvrir() }
    }
}
