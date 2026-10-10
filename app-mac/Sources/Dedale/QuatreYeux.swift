import Foundation

/// Les quatre yeux : un geste critique (virement, export de données clients) ne passe pas sur
/// le seul « Continuer » du salarié. L'app ouvre un incident au SOC, puis attend la décision
/// de l'analyste dans la console. Sans décision dans le délai, ou si le SOC est injoignable,
/// le geste est refusé : on ne laisse jamais passer par défaut.
///
/// Correspondance avec les décisions du backend (section « app Mac » de CONTRATS.md) : sur un
/// incident `humain_*`, `ignorer` (« Classer sans suite », rien d'anormal) accorde le geste,
/// `clore` le refuse. `accorder` et `refuser` sont lus aussi, si le backend les ajoute.
final class DemandeQuatreYeux {
    enum Issue: Equatable {
        case accorde
        case refuse
        case expire
        case injoignable
    }

    static let accords: Set<String> = ["accorder", "autoriser", "valider", "reprendre", "ignorer"]
    static let refus: Set<String> = ["refuser", "clore", "couper", "valider_riposte", "bloquer"]

    /// Délai d'attente de la décision, en secondes (`DEDALE_QUATRE_YEUX_DELAI`, 90 par défaut).
    static var delai: Int {
        let brut = Int(ProcessInfo.processInfo.environment["DEDALE_QUATRE_YEUX_DELAI"] ?? "") ?? 90
        return min(max(brut, 5), 600)
    }

    let avertissement: Avertissement
    /// La session du mail pour une alerte de mail (sa boîte noire porte déjà le mail), sinon
    /// une session neuve par demande. Dans les deux cas, seule une décision prise après la
    /// demande compte : on retient le nombre de décisions au moment de l'envoi.
    let sessionId: String
    let total = DemandeQuatreYeux.delai

    private let backend: Backend
    private var restant: Int
    private var minuteur: Timer?
    private var finie = false
    private var interrogationEnCours = false
    private var decisionsAvant = 0

    init(_ a: Avertissement, backend: Backend) {
        avertissement = a
        self.backend = backend
        restant = DemandeQuatreYeux.delai
        let base = a.sessionId.count > 60 ? String(a.sessionId.prefix(60)) : a.sessionId
        sessionId = a.mail != nil ? a.sessionId : "\(base)-4y-\(a.id)"
    }

    /// Envoie la demande puis interroge le backend chaque seconde. `tic` reçoit le temps
    /// restant, `fin` l'issue, une seule fois. Tout se passe sur le fil principal.
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
            self.interroger(fin: fin)
        }
    }

    private func interroger(fin: @escaping (Issue) -> Void) {
        guard !interrogationEnCours, !finie else { return }
        interrogationEnCours = true
        backend.decisions(session: sessionId) { [weak self] actions in
            guard let self else { return }
            self.interrogationEnCours = false
            guard !self.finie, let actions, actions.count > self.decisionsAvant, let derniere = actions.last else { return }
            if Self.accords.contains(derniere) { self.terminer(.accorde, fin: fin) }
            else if Self.refus.contains(derniere) { self.terminer(.refuse, fin: fin) }
        }
    }

    private func terminer(_ issue: Issue, fin: @escaping (Issue) -> Void) {
        guard !finie else { return }
        finie = true
        minuteur?.invalidate()
        minuteur = nil
        journal("quatre yeux : demande \(avertissement.id) \(issue)")
        fin(issue)
        // L'issue entre dans la boîte noire de l'incident (étape « conséquence »).
        let (code, texte): (String, String)
        switch issue {
        case .accorde: (code, texte) = ("accorde", "Accordé par le SOC : le salarié a pu continuer.")
        case .refuse: (code, texte) = ("refuse", "Refusé par le SOC : le geste n'a pas eu lieu.")
        case .expire: (code, texte) = ("expire", "Aucune décision du SOC dans le délai : le geste a été refusé.")
        case .injoignable: return
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
