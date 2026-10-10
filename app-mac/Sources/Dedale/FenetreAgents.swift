import AppKit
import DedaleNoyau

/// « Agents IA de ce poste » : les serveurs MCP trouvés, leurs types et leurs droits risqués,
/// tels qu'ils partent à la SOC. Rien d'autre ne s'affiche : ni commande, ni chemin, ni jeton.
final class FenetreAgents: FenetrePanneau {
    private static let lignesMax = 12

    init() { super.init(largeur: 520) }

    func afficher(_ agents: AgentsDuPoste) {
        construire(agents)
        montrer(capture: "agents-ia")
    }

    func rafraichir(_ agents: AgentsDuPoste) {
        guard panneau.isVisible else { return }
        construire(agents)
        ajuster(centrer: false)
    }

    private func construire(_ agents: AgentsDuPoste) {
        let w = largeur - 56
        let pile = NSStackView()
        pile.orientation = .vertical
        pile.alignment = .leading
        pile.spacing = 10
        pile.edgeInsets = NSEdgeInsets(top: 24, left: 28, bottom: 22, right: 28)

        let r = agents.resultat
        let resume: String
        if let r {
            let n = r.serveurs.count
            let c = r.clients.count
            resume = n == 0
                ? "Aucun serveur MCP trouvé dans les assistants connus."
                : "\(n) serveur\(n > 1 ? "s" : "") MCP dans \(c) assistant\(c > 1 ? "s" : ""). "
                  + (r.risques == 0 ? "Aucun n'a de droit risqué."
                     : "\(r.risques) \(r.risques > 1 ? "ont" : "a") des droits risqués.")
        } else {
            resume = "Analyse en cours…"
        }
        let tete = entete(titre: "Agents IA de ce poste", sousTitre: resume)
        pile.addArrangedSubview(tete)
        tete.widthAnchor.constraint(equalToConstant: w).isActive = true

        let source = Coque.pilule(agents.source.libelle, ton: agents.source.code == "reel" ? .risque : .accent,
                                  symbole: agents.source.code == "reel" ? "exclamationmark.triangle" : "flask")
        pile.addArrangedSubview(source)
        pile.setCustomSpacing(16, after: source)

        if let r, !r.serveurs.isEmpty {
            // Les serveurs à droits risqués d'abord.
            let tries = r.serveurs.enumerated().sorted { a, b in
                let ra = a.element.droitsRisques.count, rb = b.element.droitsRisques.count
                return ra != rb ? ra > rb : a.offset < b.offset
            }.map(\.element)
            let liste = NSStackView()
            liste.orientation = .vertical
            liste.alignment = .leading
            liste.spacing = 0
            for (i, s) in tries.prefix(Self.lignesMax).enumerated() {
                if i > 0 {
                    let trait = NSView()
                    trait.wantsLayer = true
                    trait.layer?.backgroundColor = Teinte.bord.withAlphaComponent(0.8).cgColor
                    trait.heightAnchor.constraint(equalToConstant: 1).isActive = true
                    liste.addArrangedSubview(trait)
                    trait.widthAnchor.constraint(equalToConstant: w - 32).isActive = true
                }
                let l = ligne(s, largeur: w - 32)
                liste.addArrangedSubview(l)
                l.widthAnchor.constraint(equalToConstant: w - 32).isActive = true
            }
            if tries.count > Self.lignesMax {
                liste.addArrangedSubview(Gabarit.etiquette("et \(tries.count - Self.lignesMax) autre(s)", taille: 11,
                                                           couleur: Teinte.discret))
            }
            let coque = Coque.creer(liste, marge: NSEdgeInsets(top: 4, left: 12, bottom: 4, right: 12))
            pile.addArrangedSubview(coque)
            coque.widthAnchor.constraint(equalToConstant: w).isActive = true
            pile.setCustomSpacing(14, after: coque)
        }

        let note = Gabarit.paragraphe(
            "Dédale lit le nom de chaque serveur et sa commande de lancement pour en déduire le type. "
            + "Les jetons, les clés et les variables d'environnement ne sont ni gardés ni envoyés.",
            taille: 11, couleur: Teinte.discret, largeur: w)
        pile.addArrangedSubview(note)
        note.widthAnchor.constraint(equalToConstant: w).isActive = true

        let envoi: String
        switch (agents.envoiOk, agents.dernierEnvoi) {
        case (true?, let d?): envoi = "Inventaire envoyé à la SOC à \(Self.heure.string(from: d))."
        case (false?, _): envoi = "SOC injoignable : l'inventaire n'est pas parti."
        default: envoi = "Envoi à la SOC en cours…"
        }
        let bouton = BoutonDedale(titre: "Fermer", style: .neutre, cible: self, action: #selector(fermer))
        bouton.widthAnchor.constraint(equalToConstant: 96).isActive = true
        let pied = NSStackView(views: [Gabarit.etiquette(envoi, taille: 11, graisse: .medium,
                                                         couleur: agents.envoiOk == false ? Teinte.rouge : Teinte.texte),
                                       Gabarit.ressort(), bouton])
        pied.orientation = .horizontal
        pied.alignment = .centerY
        pile.setCustomSpacing(16, after: note)
        pile.addArrangedSubview(pied)
        pied.widthAnchor.constraint(equalToConstant: w).isActive = true
        poser(pile)
    }

    private func ligne(_ s: InventaireAgents.Serveur, largeur: CGFloat) -> NSView {
        let nom = Gabarit.etiquette(s.nom, taille: 13, graisse: .semibold, couleur: Teinte.encre)
        let client = Gabarit.etiquette(s.client + (s.transport == "distant" ? " · serveur distant" : ""), taille: 11,
                                       couleur: Teinte.discret)
        let textes = NSStackView(views: [nom, client])
        textes.orientation = .vertical
        textes.alignment = .leading
        textes.spacing = 1
        // Un droit risqué remplace le type du même nom (Shell, Mail) : une seule pilule, rouge.
        var pilules = s.types.filter { !s.droitsRisques.contains($0) }
            .map { Coque.pilule(AgentsDuPoste.libellesTypes[$0] ?? $0) }
        pilules += s.droitsRisques.map {
            Coque.pilule(AgentsDuPoste.libellesDroits[$0] ?? $0, ton: .risque, symbole: "exclamationmark.triangle.fill")
        }
        let badges = Coque.rangees(pilules, largeur: largeur * 0.55, espace: 5)
        badges.alignment = .trailing
        let l = NSStackView(views: [textes, Gabarit.ressort(), badges])
        l.orientation = .horizontal
        l.alignment = .centerY
        l.spacing = 10
        l.edgeInsets = NSEdgeInsets(top: 11, left: 0, bottom: 11, right: 0)
        return l
    }

    static let heure: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        return f
    }()
}
