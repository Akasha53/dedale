import AppKit
import DedaleNoyau
import Foundation

/// Gestes critiques (virement, export de données clients) : Dédale ne se montre que s'il y a un
/// signal de risque.
///
/// - Geste lancé sur le poste (`verifier`) : l'app demande au backend `POST /api/relecteur/verifier`.
///   Aucun signal : le geste part, sans pop-up. Signal sans fraude : le relecteur accorde (une ligne
///   discrète) ou retient le geste, et la pop-up dit pourquoi en clair et qu'il faut le faire
///   confirmer par le responsable ou la finance. Signal de fraude : le geste est refusé ou retenu,
///   et l'équipe sécurité est prévenue. Une réponse lente ouvre « sAIfe vérifie ce virement… » ;
///   une absence de réponse retient le geste, jamais de refus sec à cause d'un délai.
/// - Geste qui suit une alerte de mail (`lancer`) : après « Continuer », la demande part au SOC
///   et le relecteur la tranche ; sans réponse, le geste est retenu.
///
/// Correspondance avec les décisions du backend (section « app Mac » de CONTRATS.md) : `ignorer`
/// et `accorder` accordent le geste, `clore` et `refuser` le refusent.
final class DemandeQuatreYeux {
    enum Issue: Equatable {
        case accorde
        case refuse
        /// Ni accordé ni refusé : à faire confirmer par le responsable ou la finance.
        case retenu
        case expire
        case injoignable
    }

    /// Ce que le relecteur a décidé. Le salarié ne lit que `motifSalarie`, en français courant ;
    /// le motif technique et le nom du modèle restent dans la console.
    struct Relecture {
        let etat: String  // accorde, refuse, retenu
        let motifSalarie: String
        let tranchePar: String
        let dureeMs: Int
        /// Signal de fraude : l'équipe sécurité est prévenue.
        var fraude = false

        var accorde: Bool { etat == "accorde" }
        var retenu: Bool { etat == "retenu" }

        /// « 1,8 s », « moins de 0,1 s » : la durée de la relecture, à la française.
        var duree: String {
            if dureeMs < 100 { return "moins de 0,1 s" }
            let secondes = Double(dureeMs) / 1000
            return String(format: "%.1f s", secondes).replacingOccurrences(of: ".", with: ",")
        }
    }

    static let accords: Set<String> = ["accorder", "autoriser", "valider", "reprendre", "ignorer"]
    static let refus: Set<String> = ["refuser", "clore", "couper", "valider_riposte", "bloquer"]

    /// Attente maximale d'une relecture après « Continuer » sur une alerte de mail, en secondes.
    /// Au-delà, le geste est retenu (`DEDALE_QUATRE_YEUX_DELAI`, 20 par défaut, 5 à 120).
    static var delai: Int {
        let brut = Int(ProcessInfo.processInfo.environment["DEDALE_QUATRE_YEUX_DELAI"] ?? "") ?? 20
        return min(max(brut, 5), 120)
    }

    /// Un geste lancé sur le poste passe par la vérification, sans question au salarié. Une alerte
    /// de mail garde son choix « Annuler » ou « Continuer ».
    static func verifieDAbord(_ a: Avertissement) -> Bool { a.quatreYeux && a.mail == nil }

    /// Relectures reçues, par identifiant d'alerte, lues par la pop-up au moment de l'issue.
    private static var relectures: [String: Relecture] = [:]
    static func relecture(pour id: String) -> Relecture? { relectures[id] }

    // MARK: Textes de la pop-up

    /// Titre de la pop-up : jamais le texte reçu, qui peut venir d'un attaquant. On le bâtit sur
    /// les champs structurés (geste, cible) et sur les seuls nombres du message.
    static func titre(pour a: Avertissement) -> String {
        TitreGeste.titre(geste: a.geste, categorie: a.categorie, message: "\(a.message) \(a.detail)",
                         cible: a.cible, depuisUnMail: a.mail != nil)
    }

    private static var gesteEnCours: String?
    static var titreAttente: String {
        switch gesteEnCours {
        case "virement": return "sAIfe vérifie ce virement…"
        case "export_clients": return "sAIfe vérifie cet export…"
        default: return "sAIfe vérifie ce geste…"
        }
    }

    static let conseilRetenu = "Fais-le confirmer par ton responsable ou par la finance, puis relance-le."

    /// Pas de compte à rebours : le salarié n'a rien à surveiller.
    static func texteAttente(restant _: Int) -> String { "Quelques secondes." }

    static func texteIssue(_ issue: Issue, relecture r: Relecture?) -> String {
        let verifie = r.map { "Vérifié automatiquement en \($0.duree)." }
        let lignes: [String?]
        switch issue {
        case .accorde:
            lignes = r == nil ? ["L'équipe sécurité a validé ce geste. Tu peux continuer."] : [r?.motifSalarie, verifie]
        case .retenu:
            lignes = [r?.motifSalarie ?? "sAIfe n'a pas pu vérifier ce geste.", conseilRetenu,
                      r?.fraude == true ? "L'équipe sécurité est prévenue." : nil, verifie]
        case .expire:
            lignes = ["sAIfe n'a pas pu vérifier ce geste à temps.", conseilRetenu]
        case .injoignable:
            lignes = ["sAIfe est injoignable : ce geste attend.", conseilRetenu]
        case .refuse:
            lignes = r == nil
                ? ["L'équipe sécurité a refusé ce geste. Il n'aura pas lieu."]
                : [r?.motifSalarie, "Parles-en à ton responsable. L'équipe sécurité est prévenue.", verifie]
        }
        return lignes.compactMap { $0 }.joined(separator: "\n")
    }

    let avertissement: Avertissement
    /// La session du mail pour une alerte de mail (sa boîte noire porte déjà le mail), sinon
    /// une session neuve par demande. Dans les deux cas, seule une décision prise après la
    /// demande compte : on retient le nombre de décisions au moment de l'envoi.
    let sessionId: String
    let total = DemandeQuatreYeux.delai

    private let backend: Backend
    private let reseau: URLSession = {
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 2
        conf.timeoutIntervalForResource = 3
        conf.waitsForConnectivity = false
        return URLSession(configuration: conf)
    }()
    /// La vérification attend le relecteur : jusqu'à 12 s quand il y a un signal.
    private let reseauLent: URLSession = {
        let conf = URLSessionConfiguration.ephemeral
        conf.timeoutIntervalForRequest = 12
        conf.timeoutIntervalForResource = 13
        conf.waitsForConnectivity = false
        return URLSession(configuration: conf)
    }()
    private var restant: Int
    private var minuteur: Timer?
    private var sonde: Timer?
    private var finie = false
    private var interrogationEnCours = false
    private var sondeEnCours = false
    /// Un backend sans relecteur répond 404 : après trois, on ne sonde plus.
    private var sondesSansRelecteur = 0
    private var decisionsAvant = 0
    private(set) var relecture: Relecture?

    init(_ a: Avertissement, backend: Backend) {
        avertissement = a
        self.backend = backend
        restant = DemandeQuatreYeux.delai
        let base = a.sessionId.count > 60 ? String(a.sessionId.prefix(60)) : a.sessionId
        sessionId = a.mail != nil ? a.sessionId : "\(base)-4y-\(a.id)"
    }

    // MARK: Requêtes signées

    /// Jeton `poste`, lu hors du dépôt (`~/.config/dedale/jeton-poste`, ou `DEDALE_JETONS`).
    private static func signer(_ r: inout URLRequest) {
        let env = ProcessInfo.processInfo.environment
        let dossier = env["DEDALE_JETONS"].map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) }
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".config/dedale")
        guard let brut = try? String(contentsOf: dossier.appendingPathComponent("jeton-poste"), encoding: .ascii)
        else { return }
        let jeton = brut.trimmingCharacters(in: .whitespacesAndNewlines)
        if !jeton.isEmpty { r.setValue("Bearer \(jeton)", forHTTPHeaderField: "Authorization") }
    }

    private func requete(_ chemin: String, corps: [String: Any]? = nil) -> URLRequest {
        var r = URLRequest(url: backend.base.appendingPathComponent(chemin))
        if let corps, let donnees = try? JSONSerialization.data(withJSONObject: corps) {
            r.httpMethod = "POST"
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = donnees
        }
        Self.signer(&r)
        return r
    }

    // MARK: Geste lancé sur le poste

    /// Vérifie le geste sans rien demander au salarié. `fenetre` n'est montrée que si Dédale a
    /// quelque chose à dire ; sinon elle est rendue sans avoir été vue. `fin` est appelé une fois.
    func verifier(fenetre f: FenetreAlerte, fin: @escaping () -> Void) {
        Self.gesteEnCours = avertissement.geste
        var corps: [String: Any] = [
            "demande_id": avertissement.id,
            "session_id": avertissement.sessionId,
            "categorie": avertissement.categorie,
            "message": "\(avertissement.message) \(avertissement.detail)",
        ]
        if let g = avertissement.geste { corps["geste"] = g }
        if let c = avertissement.cible { corps["cible"] = c }
        if let l = avertissement.lien { corps["lien"] = l }
        var montree = false
        var conclu = false
        // Une réponse lente (signal, relecteur au travail) ouvre la pop-up d'attente.
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {
            guard !conclu, !montree else { return }
            montree = true
            f.montrer()
            f.montrerAttente(restant: 0)
        }
        journal("vérification du geste \(avertissement.id) (\(avertissement.geste ?? avertissement.categorie))")
        reseauLent.dataTask(with: requete("api/relecteur/verifier", corps: corps)) { [weak self] donnees, reponse, _ in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            let json = (code == 200 ? donnees.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } : nil)
            DispatchQueue.main.async {
                guard let self, !conclu else { return }
                conclu = true
                Self.gesteEnCours = nil
                let issue = json?["issue"] as? String
                let motif = (json?["motif_salarie"] as? String).map { String($0.prefix(220)) }
                let duree = (json?["duree_ms"] as? NSNumber)?.intValue ?? 0
                journal("vérification du geste \(self.avertissement.id) : \(issue ?? "sans réponse (HTTP \(code))")")
                switch issue {
                case "passe", "accorde":
                    if montree {
                        Self.relectures[self.avertissement.id] = Relecture(
                            etat: "accorde", motifSalarie: motif ?? "Rien d'inhabituel : le geste part.",
                            tranchePar: json?["tranche_par"] as? String ?? "règles", dureeMs: duree)
                        f.montrerIssue(.accorde)
                    } else {
                        if issue == "accorde" {
                            Bulle("Vérifié par sAIfe : le geste part.", ok: true).montrer()
                        }
                        f.surFermeture?()
                    }
                case "retenu", "refuse":
                    Self.relectures[self.avertissement.id] = Relecture(
                        etat: issue!, motifSalarie: motif ?? "Ce geste présente un signal inhabituel.",
                        tranchePar: json?["tranche_par"] as? String ?? "règles", dureeMs: duree,
                        fraude: json?["fraude"] as? Bool ?? false)
                    if !montree { f.montrer() }
                    f.montrerIssue(issue == "refuse" ? .refuse : .retenu)
                default:
                    // Backend injoignable ou réponse illisible : le geste est retenu, jamais refusé.
                    if !montree { f.montrer() }
                    f.montrerIssue(.injoignable)
                }
                fin()
            }
        }.resume()
    }

    // MARK: Geste qui suit une alerte de mail

    /// Envoie la demande puis attend une décision : relecteur sondé toutes les 0,4 s, décisions
    /// de l'incident relues chaque seconde. Sans décision dans le délai, le geste est retenu.
    /// `tic` reçoit le temps restant (non affiché), `fin` l'issue, une seule fois.
    func lancer(tic: @escaping (Int) -> Void, fin: @escaping (Issue) -> Void) {
        Self.gesteEnCours = avertissement.geste
        let extra: [String: Any] = [
            "quatre_yeux": "demande",
            "demande_id": avertissement.id,
            "delai_s": total,
            "consequence": "Geste suspendu : sAIfe le vérifie.",
        ]
        backend.decisions(session: sessionId) { [weak self] avant in
            guard let self else { return }
            self.decisionsAvant = avant?.count ?? 0
            self.envoyer(extra: extra, tic: tic, fin: fin)
        }
    }

    private func envoyer(extra: [String: Any], tic: @escaping (Int) -> Void, fin: @escaping (Issue) -> Void) {
        journal("quatre yeux : demande \(avertissement.id) envoyée (session \(sessionId), délai \(total) s)")
        backend.envoyerChoix(avertissement, choix: "continuer", sessionId: sessionId, extra: extra) { [weak self] ok in
            guard let self else { return }
            guard ok else { self.terminer(.injoignable, fin: fin); return }
            tic(self.restant)
            self.minuteur = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in
                guard let self, !self.finie else { return }
                self.restant -= 1
                if self.restant <= 0 { self.terminer(.expire, fin: fin); return }
                tic(self.restant)
                self.interroger(fin: fin)
            }
            RunLoop.main.add(self.minuteur!, forMode: .common)
            self.sonde = Timer.scheduledTimer(withTimeInterval: 0.4, repeats: true) { [weak self] _ in
                self?.sonder(fin: fin)
            }
            RunLoop.main.add(self.sonde!, forMode: .common)
            self.sonder(fin: fin)
            self.interroger(fin: fin)
        }
    }

    /// Le relecteur a-t-il tranché ? `GET /api/relecteur/demandes/{id}`.
    private func sonder(fin: @escaping (Issue) -> Void) {
        guard !finie, !sondeEnCours, sondesSansRelecteur < 3 else { return }
        sondeEnCours = true
        lireRelecture { [weak self] r, absent in
            guard let self else { return }
            self.sondeEnCours = false
            if absent { self.sondesSansRelecteur += 1 }
            guard !self.finie, let r else { return }
            self.relecture = r
            self.terminer(r.accorde ? .accorde : r.retenu ? .retenu : .refuse, fin: fin)
        }
    }

    private func lireRelecture(_ fin: @escaping (Relecture?, Bool) -> Void) {
        reseau.dataTask(with: requete("api/relecteur/demandes/\(avertissement.id)")) { donnees, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            var r: Relecture?
            if erreur == nil, code == 200, let donnees,
               let json = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any],
               json["statut"] as? String == "tranchee",
               let decision = json["decision"] as? String, ["accorde", "refuse", "retenu"].contains(decision) {
                // Jamais `motif` ni `motif_soc` : ce sont les détails techniques de la SOC.
                let defaut = decision == "accorde" ? "Rien d'inhabituel n'a été repéré dans ce geste."
                    : decision == "retenu" ? "Ce geste présente un signal inhabituel."
                    : "Ce geste présente des signes de fraude : il est bloqué."
                let phrase = (json["motif_salarie"] as? String).map { String($0.prefix(220)) } ?? ""
                r = Relecture(etat: decision, motifSalarie: phrase.isEmpty ? defaut : phrase,
                              tranchePar: (json["tranche_par"] as? String) ?? "règles",
                              dureeMs: (json["duree_ms"] as? NSNumber)?.intValue ?? 0)
            }
            DispatchQueue.main.async { fin(r, code == 404) }
        }.resume()
    }

    private func interroger(fin: @escaping (Issue) -> Void) {
        guard !interrogationEnCours, !finie else { return }
        interrogationEnCours = true
        backend.decisions(session: sessionId) { [weak self] actions in
            guard let self else { return }
            self.interrogationEnCours = false
            guard !self.finie, let actions, actions.count > self.decisionsAvant, let derniere = actions.last else { return }
            let issue: Issue
            if Self.accords.contains(derniere) { issue = .accorde }
            else if Self.refus.contains(derniere) { issue = .refuse }
            else { return }
            // La décision peut venir du relecteur : on lit son motif avant de conclure.
            self.lireRelecture { [weak self] r, _ in
                guard let self, !self.finie else { return }
                if let r, !r.retenu, r.accorde == (issue == .accorde) { self.relecture = r }
                self.terminer(issue, fin: fin)
            }
        }
    }

    private func terminer(_ issue: Issue, fin: @escaping (Issue) -> Void) {
        guard !finie else { return }
        finie = true
        minuteur?.invalidate()
        minuteur = nil
        sonde?.invalidate()
        sonde = nil
        Self.gesteEnCours = nil
        if let relecture { Self.relectures[avertissement.id] = relecture }
        let par = relecture.map { " par le relecteur (\($0.tranchePar), \($0.duree))" } ?? ""
        journal("quatre yeux : demande \(avertissement.id) \(issue)\(par)")
        fin(issue)
        // L'issue entre dans la boîte noire de l'incident (étape « conséquence »).
        let (code, texte): (String, String)
        switch (issue, relecture) {
        case (.accorde, .some(let r)):
            (code, texte) = ("accorde", "Accordé par le relecteur sAIfe (\(r.tranchePar)) en \(r.duree) : le salarié a pu continuer.")
        case (.refuse, .some(let r)):
            (code, texte) = ("refuse", "Refusé par le relecteur sAIfe (\(r.tranchePar)) en \(r.duree) : le geste n'a pas eu lieu.")
        case (.retenu, .some(let r)):
            (code, texte) = ("retenu", "Retenu par le relecteur sAIfe (\(r.tranchePar)) en \(r.duree) : à faire confirmer par le responsable.")
        case (.accorde, _): (code, texte) = ("accorde", "Accordé par le SOC : le salarié a pu continuer.")
        case (.refuse, _): (code, texte) = ("refuse", "Refusé par le SOC : le geste n'a pas eu lieu.")
        case (.retenu, _), (.expire, _):
            (code, texte) = ("retenu", "Pas de relecture dans le délai : le geste est retenu, à faire confirmer par le responsable.")
        case (.injoignable, _): return
        }
        backend.envoyer(type: "riposte", sessionId: sessionId, details: [
            "origine": "app-mac",
            "quatre_yeux": code,
            "demande_id": avertissement.id,
            "categorie": avertissement.categorie,
            "consequence": texte,
        ]) { _ in }
    }
}
