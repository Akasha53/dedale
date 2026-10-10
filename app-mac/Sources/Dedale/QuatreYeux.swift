import DedaleNoyau
import Foundation

/// Les quatre yeux : un geste critique (virement, export de données clients) ne passe pas sur
/// le seul « Continuer » du salarié. L'app ouvre un incident au SOC, puis attend une décision.
/// Le relecteur IA du backend tranche en quelques secondes ; sans lui, un analyste décide dans
/// la console. Sans décision dans le délai, ou si le SOC est injoignable, le geste est refusé :
/// on ne laisse jamais passer par défaut.
///
/// Correspondance avec les décisions du backend (section « app Mac » de CONTRATS.md) : sur un
/// incident `humain_*`, `ignorer` et `accorder` accordent le geste, `clore` et `refuser` le
/// refusent. Le relecteur pose `accorder` ou `refuser`, et son motif se lit sur
/// `GET /api/relecteur/demandes/{id}` (avenant « relecteur IA »).
final class DemandeQuatreYeux {
    enum Issue: Equatable {
        case accorde
        case refuse
        case expire
        case injoignable
    }

    /// Ce que le relecteur a décidé. Le salarié ne lit que `motifSalarie`, en français courant ;
    /// le motif technique et le nom du modèle restent dans la console.
    struct Relecture {
        let accorde: Bool
        /// Ni accordé ni refusé : le relecteur laisse la main à l'équipe sécurité (RIB changé…).
        var retenu = false
        let motifSalarie: String
        let tranchePar: String
        let dureeMs: Int

        /// « 1,8 s », « moins de 0,1 s » : la durée de la relecture, à la française.
        var duree: String {
            if dureeMs < 100 { return "moins de 0,1 s" }
            let secondes = Double(dureeMs) / 1000
            return String(format: "%.1f s", secondes).replacingOccurrences(of: ".", with: ",")
        }
    }

    static let accords: Set<String> = ["accorder", "autoriser", "valider", "reprendre", "ignorer"]
    static let refus: Set<String> = ["refuser", "clore", "couper", "valider_riposte", "bloquer"]

    /// Délai d'attente de la décision, en secondes (`DEDALE_QUATRE_YEUX_DELAI`, 90 par défaut).
    static var delai: Int {
        let brut = Int(ProcessInfo.processInfo.environment["DEDALE_QUATRE_YEUX_DELAI"] ?? "") ?? 90
        return min(max(brut, 5), 600)
    }

    /// Au-delà, le relecteur ne répond plus : la pop-up le dit et compte le temps restant.
    static let attenteRelecteur = 12

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

    static let titreAttente = "Vérification en cours…"
    static let conseilRefus = "Si c'est légitime, demande à ton responsable de le confirmer à l'équipe sécurité."

    /// Motif d'un geste retenu par le relecteur, montré pendant que l'équipe sécurité décide.
    private static var motifRetenu: String?

    static func texteAttente(restant: Int) -> String {
        if let motif = motifRetenu {
            return "\(motif)\nSans décision de l'équipe sécurité dans \(restant) s, le geste est refusé."
        }
        if delai - restant < attenteRelecteur {
            return "Dédale vérifie ce geste, cela prend quelques secondes."
        }
        return "Pas encore de réponse. Sans décision de l'équipe sécurité dans \(restant) s, le geste est refusé."
    }

    static func texteIssue(_ issue: Issue, relecture r: Relecture?) -> String {
        if let r, issue == .accorde || issue == .refuse {
            var lignes = [r.motifSalarie]
            if !r.accorde { lignes.append(conseilRefus) }
            lignes.append("Vérifié automatiquement en \(r.duree). L'équipe sécurité peut revenir sur cette décision.")
            return lignes.joined(separator: "\n")
        }
        switch issue {
        case .accorde: return "L'équipe sécurité a validé ce geste. Tu peux continuer."
        case .refuse: return "L'équipe sécurité a refusé ce geste. Il n'aura pas lieu.\n\(conseilRefus)"
        case .expire: return "Pas de réponse de l'équipe sécurité à temps : le geste n'aura pas lieu.\n\(conseilRefus)"
        case .injoignable: return "L'équipe sécurité est injoignable : le geste n'aura pas lieu."
        }
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

    /// Envoie la demande puis attend une décision : relecteur sondé toutes les 0,4 s, décisions
    /// de l'incident relues chaque seconde. `tic` reçoit le temps restant, `fin` l'issue, une
    /// seule fois. Tout se passe sur le fil principal.
    func lancer(tic: @escaping (Int) -> Void, fin: @escaping (Issue) -> Void) {
        let extra: [String: Any] = [
            "quatre_yeux": "demande",
            "demande_id": avertissement.id,
            "delai_s": total,
            "consequence": "Geste suspendu : il attend la validation d'un analyste du SOC.",
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
            if r.retenu {
                // Le relecteur passe la main : on attend la décision d'un analyste, avec le délai.
                Self.motifRetenu = r.motifSalarie
                self.sondesSansRelecteur = 3
                self.sonde?.invalidate()
                self.sonde = nil
                journal("quatre yeux : demande \(self.avertissement.id) retenue par le relecteur, l'analyste décide")
                return
            }
            self.relecture = r
            self.terminer(r.accorde ? .accorde : .refuse, fin: fin)
        }
    }

    private func lireRelecture(_ fin: @escaping (Relecture?, Bool) -> Void) {
        let chemin = "api/relecteur/demandes/\(avertissement.id)"
        reseau.dataTask(with: backend.base.appendingPathComponent(chemin)) { donnees, reponse, erreur in
            let code = (reponse as? HTTPURLResponse)?.statusCode ?? 0
            var r: Relecture?
            if erreur == nil, code == 200, let donnees,
               let json = try? JSONSerialization.jsonObject(with: donnees) as? [String: Any],
               json["statut"] as? String == "tranchee",
               let decision = json["decision"] as? String, ["accorde", "refuse", "retenu"].contains(decision) {
                // Jamais `motif` ni `motif_soc` : ce sont les détails techniques de la SOC.
                let defaut = decision == "accorde" ? "Rien d'inhabituel n'a été repéré dans ce geste."
                    : decision == "retenu" ? "Ce geste doit être confirmé par l'équipe sécurité avant d'avoir lieu."
                    : "Ce geste présente des signes inhabituels : il est bloqué par précaution."
                let phrase = (json["motif_salarie"] as? String).map { String($0.prefix(220)) } ?? ""
                r = Relecture(accorde: decision == "accorde", retenu: decision == "retenu",
                              motifSalarie: phrase.isEmpty ? defaut : phrase,
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
        Self.motifRetenu = nil
        if let relecture { Self.relectures[avertissement.id] = relecture }
        let par = relecture.map { " par le relecteur (\($0.tranchePar), \($0.duree))" } ?? ""
        journal("quatre yeux : demande \(avertissement.id) \(issue)\(par)")
        fin(issue)
        // L'issue entre dans la boîte noire de l'incident (étape « conséquence »).
        let (code, texte): (String, String)
        switch (issue, relecture) {
        case (.accorde, .some(let r)):
            (code, texte) = ("accorde", "Accordé par le relecteur Dédale (\(r.tranchePar)) en \(r.duree) : le salarié a pu continuer.")
        case (.refuse, .some(let r)):
            (code, texte) = ("refuse", "Refusé par le relecteur Dédale (\(r.tranchePar)) en \(r.duree) : le geste n'a pas eu lieu.")
        case (.accorde, _): (code, texte) = ("accorde", "Accordé par le SOC : le salarié a pu continuer.")
        case (.refuse, _): (code, texte) = ("refuse", "Refusé par le SOC : le geste n'a pas eu lieu.")
        case (.expire, _): (code, texte) = ("expire", "Aucune décision du SOC dans le délai : le geste a été refusé.")
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
