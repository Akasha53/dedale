import Foundation

/// Le coach en 20 secondes : après « Annuler », deux lignes au plus disent ce qui était piégé
/// et comment le repérer la prochaine fois. Le piège vient des raisons du verdict ou du détail
/// de l'alerte ; le repère vient du conseil de l'analyseur ou de ce petit catalogue local.
enum Coach {
    struct Fiche {
        let piege: String
        let repere: String
    }

    /// Catalogue par geste ou par catégorie : le piège type et le repère à retenir.
    static let catalogue: [String: Fiche] = [
        "phishing": Fiche(
            piege: "Le mail imite Orbis Pay pour vous faire cliquer.",
            repere: "Survolez le lien et lisez l'adresse réelle avant de cliquer."),
        "secret": Fiche(
            piege: "Un mot de passe ou une clé allait sortir du poste.",
            repere: "Une clé ne se colle jamais dans un chat ou un site. Elle reste dans le coffre."),
        "mail_externe": Fiche(
            piege: "Des données internes partaient vers une adresse hors d'Orbis Pay.",
            repere: "Vérifiez le domaine du destinataire avant d'envoyer une pièce jointe."),
        "upload_ia": Fiche(
            piege: "Un fichier interne partait vers une IA non autorisée.",
            repere: "Pour un document interne, utilisez l'assistant validé par Orbis Pay."),
        "intrusion_physique": Fiche(
            piege: "Un équipement piégé a été touché.",
            repere: "Ne branchez pas de clé inconnue et signalez tout accès inattendu."),
        "virement": Fiche(
            piege: "Le virement partait vers un compte inconnu, demandé dans l'urgence.",
            repere: "Un virement urgent demandé par mail se confirme par téléphone, au numéro habituel."),
        "export_clients": Fiche(
            piege: "Des fiches clients allaient quitter l'entreprise.",
            repere: "Les données clients restent dans les outils d'Orbis Pay."),
    ]

    /// Repère par signal de l'analyseur de `messagerie/` (code du signal le plus lourd d'abord).
    private static let reperesSignal: [String: String] = [
        "lien_menteur": "Survolez le lien et lisez l'adresse réelle avant de cliquer.",
        "sosie_domaine": "Lisez le domaine lettre par lettre : une lettre changée suffit à faire un faux.",
        "nom_affiche_trompeur": "Lisez l'adresse de l'expéditeur, pas seulement le nom affiché.",
        "reponse_detournee": "Avant de répondre, regardez à quelle adresse part votre réponse.",
        "piece_jointe_dangereuse": "N'ouvrez pas une pièce jointe que vous n'attendiez pas, et n'activez jamais les macros.",
        "urgence_argent": "Un paiement demandé par mail se confirme par téléphone, au numéro habituel.",
        "changement_bancaire": "Un changement de RIB se vérifie par téléphone, auprès d'un contact connu.",
        "urgence_identifiants": "Orbis Pay ne demande jamais votre mot de passe par mail.",
        "instruction_cachee": "Ce mail parle en cachette à votre assistant IA. Ne lui confiez pas un mail douteux.",
        "texte_cache": "Un texte invisible cache le vrai message. Méfiez-vous d'un mail qui semble vide ou anodin.",
        "caracteres_invisibles": "Des caractères invisibles brouillent le texte. Lisez l'adresse et les liens de près.",
        "authentification_echec": "Le serveur n'a pas pu vérifier l'expéditeur. Confirmez par un autre moyen.",
    ]

    /// Repères plus précis pour un mail, choisis d'après les mots de la raison.
    private static let reperesMail: [(mots: [String], repere: String)] = [
        (["virement", "iban", "rib", "paiement", "facture"],
         "Un paiement demandé par mail se confirme par téléphone, au numéro habituel."),
        (["mot de passe", "identifiant", "connexion"],
         "Orbis Pay ne demande jamais votre mot de passe par mail."),
        (["lien", "site", "url", "adresse web"],
         "Survolez le lien et lisez l'adresse réelle avant de cliquer."),
        (["expéditeur", "expediteur", "domaine", "adresse"],
         "Lisez l'adresse complète de l'expéditeur, pas seulement le nom affiché."),
        (["pièce jointe", "piece jointe", "fichier", "macro"],
         "N'ouvrez pas une pièce jointe que vous n'attendiez pas."),
        (["urgent", "urgence", "immédiat", "immediat", "vite", "24 h", "suspendu"],
         "Un mail qui vous presse veut vous empêcher de vérifier. Prenez une minute."),
    ]

    static func fiche(pour a: Avertissement) -> Fiche {
        let base = catalogue[a.geste ?? a.categorie] ?? catalogue["phishing"]!
        let piege = a.raisons.first ?? (a.detail.isEmpty ? base.piege : premierePhrase(a.detail))
        var repere = a.conseil ?? base.repere
        if a.conseil == nil, let code = a.codes.first(where: { reperesSignal[$0] != nil }) {
            repere = reperesSignal[code]!
        } else if a.conseil == nil, a.categorie == "phishing", a.geste == nil {
            let texte = (a.raisons.joined(separator: " ") + " " + a.detail).lowercased()
            if let trouve = reperesMail.first(where: { r in r.mots.contains { texte.contains($0) } }) {
                repere = trouve.repere
            }
        }
        return Fiche(piege: Avertissement.nettoyer(piege, max: 150),
                     repere: Avertissement.nettoyer(repere, max: 150))
    }

    /// La première phrase : un point suivi d'une espace ou de la fin, pas celui d'un nom de
    /// fichier (« contrats.xlsx ») ni d'un domaine.
    private static func premierePhrase(_ s: String) -> String {
        guard let r = s.range(of: #"[.!?…](\s|$)"#, options: .regularExpression) else { return s }
        return String(s[..<r.lowerBound]) + String(s[r].prefix(1))
    }
}
