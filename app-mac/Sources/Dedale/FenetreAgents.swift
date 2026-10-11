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

        let r = agents.resultat
        let resume: String
        if let r {
            let total = r.serveurs.count
            let agentsT = r.serveurs.filter(\.agentTerminal).count
            let mcp = total - agentsT
            let c = r.clients.count
            if total == 0 {
                resume = "Aucun assistant IA trouvé parmi les clients connus."
            } else {
                var tete = "\(mcp) serveur\(mcp > 1 ? "s" : "") MCP dans \(c) assistant\(c > 1 ? "s" : "")"
                if agentsT > 0 {
                    tete += ", dont \(agentsT) agent\(agentsT > 1 ? "s" : "") en terminal"
                }
                let fin = r.risques == 0
                    ? "Aucun n'a de droit risqué."
                    : "\(r.risques) sur \(total) \(r.risques > 1 ? "ont" : "a") des droits risqués."
                resume = tete + ". " + fin
            }
        } else {
            resume = "Analyse en cours…"
        }
        let tete = entete(titre: "Agents IA de ce poste", sousTitre: resume)
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
                    trait.layer?.backgroundColor = Teinte.bord.cgColor
                    trait.heightAnchor.constraint(equalToConstant: 1).isActive = true
                    liste.addArrangedSubview(trait)
                    trait.widthAnchor.constraint(equalToConstant: w - 32).isActive = true
                }
                let l = ligne(s, largeur: w - 32)
                liste.addArrangedSubview(l)
                l.widthAnchor.constraint(equalToConstant: w - 32).isActive = true
            }
            if tries.count > Self.lignesMax {
                liste.addArrangedSubview(Gabarit.etiquette("et \(tries.count - Self.lignesMax) autre(s)", taille: Taille.note,
                                                           couleur: Teinte.discret))
            }
            let coque = Coque.creer(liste, marge: NSEdgeInsets(top: 4, left: 16, bottom: 4, right: 16))
            pile.addArrangedSubview(coque)
            coque.widthAnchor.constraint(equalToConstant: w).isActive = true
            pile.setCustomSpacing(14, after: coque)
        }

        let note = Gabarit.paragraphe(
            "sAIfe lit le nom de chaque serveur et sa commande de lancement pour en déduire le type. "
            + "Les jetons, les clés et les variables d'environnement ne sont ni gardés ni envoyés.",
            taille: Taille.note, couleur: Teinte.discret, largeur: w)
        pile.addArrangedSubview(note)
        note.widthAnchor.constraint(equalToConstant: w).isActive = true

        let envoi: String
        switch (agents.envoiOk, agents.dernierEnvoi) {
        case (true?, let d?): envoi = "Inventaire envoyé à l'équipe sécurité à \(Self.heure.string(from: d))."
        case (false?, _): envoi = "Équipe sécurité injoignable : l'inventaire n'est pas parti."
        default: envoi = "Envoi à l'équipe sécurité en cours…"
        }
        let bouton = BoutonDedale(titre: "Fermer", style: .neutre, cible: self, action: #selector(fermer))
        bouton.widthAnchor.constraint(equalToConstant: 96).isActive = true
        let pied = NSStackView(views: [Gabarit.etiquette(envoi, taille: Taille.note, graisse: .medium,
                                                         couleur: agents.envoiOk == false ? Teinte.rouge : Teinte.texte),
                                       Gabarit.ressort(), bouton])
        pied.orientation = .horizontal
        pied.alignment = .centerY
        pied.widthAnchor.constraint(equalToConstant: w).isActive = true
        poser(tete: tete, corps: pile, pied: pied)
    }

    private func ligne(_ s: InventaireAgents.Serveur, largeur: CGFloat) -> NSView {
        let nom = Gabarit.etiquette(s.nom, taille: Taille.texte, graisse: .semibold, couleur: Teinte.encre)
        let sousTitre = s.agentTerminal
            ? "agent en terminal · accès shell et disque complet"
            : s.client + (s.transport == "distant" ? " · serveur distant" : "")
        let client = Gabarit.etiquette(sousTitre, taille: Taille.note, couleur: Teinte.discret)
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
        let badges = Coque.rangees(pilules, largeur: largeur - 150, espace: 5)
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
