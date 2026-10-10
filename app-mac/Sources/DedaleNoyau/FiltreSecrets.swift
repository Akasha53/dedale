import Foundation

/// Reconnaît ce qui ressemble à un secret (jeton, clé d'API, mot de passe) pour qu'il ne
/// sorte jamais du poste. Le filtre se trompe volontairement dans le sens prudent : une
/// valeur douteuse est écartée, au prix de perdre parfois une information anodine.
public enum FiltreSecrets {
    /// Préfixes de jetons connus (GitHub, OpenAI, Anthropic, Slack, AWS, Google, Stripe…).
    private static let prefixes = try! NSRegularExpression(pattern: """
        (sk-[A-Za-z0-9_-]{8,}|sk_(live|test)_[A-Za-z0-9]{6,}|[rp]k_live_[A-Za-z0-9]{6,}|\
        gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[abprs]-[A-Za-z0-9-]{8,}|\
        (AKIA|ASIA)[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|glpat-[A-Za-z0-9_-]{12,}|ya29\\.[A-Za-z0-9_-]{8,}|\
        eyJ[A-Za-z0-9_-]{8,}\\.[A-Za-z0-9_-]{8,}|npm_[A-Za-z0-9]{20,}|hf_[A-Za-z0-9]{20,}|\
        pplx-[A-Za-z0-9]{12,}|gsk_[A-Za-z0-9]{16,}|xai-[A-Za-z0-9]{16,}|lin_api_[A-Za-z0-9]{12,}|\
        ntn_[A-Za-z0-9]{16,}|secret_[A-Za-z0-9]{16,}|-----BEGIN)
        """, options: [])

    /// Nom de clé ou d'option qui annonce un secret : `token`, `api_key`, `--password`…
    private static let nomSecret = try! NSRegularExpression(pattern:
        "(token|secret|passw(or)?d|pwd|api[_-]?key|apikey|access[_-]?key|private[_-]?key|"
        + "client[_-]?secret|credential|bearer|auth(orization)?|cle|clef|jeton|mot[_-]?de[_-]?passe)",
        options: [.caseInsensitive])

    /// Option de ligne de commande dont la valeur suit : `--token`, `-k`, `--api-key`.
    private static let optionSecrete = try! NSRegularExpression(pattern:
        "^--?[A-Za-z0-9_-]*(token|secret|passw(or)?d|pwd|key|auth|credential|bearer|jeton|cle)[A-Za-z0-9_-]*$",
        options: [.caseInsensitive])

    /// Vrai si `valeur` ressemble à un secret.
    public static func estSecret(_ valeur: String) -> Bool {
        let v = valeur.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !v.isEmpty else { return false }
        let plage = NSRange(v.startIndex..., in: v)
        if prefixes.firstMatch(in: v, range: plage) != nil { return true }
        let bas = v.lowercased()
        if bas.hasPrefix("bearer ") || bas.hasPrefix("basic ") || bas.hasPrefix("token ") { return true }
        // `cle=valeur`, `token: valeur`, et l'URL qui porte un secret en paramètre ou en identifiants.
        if let sep = v.firstIndex(where: { $0 == "=" || $0 == ":" }) {
            let gauche = String(v[..<sep])
            let droite = String(v[v.index(after: sep)...])
            if !droite.isEmpty, !gauche.contains("/"),
               nomSecret.firstMatch(in: gauche, range: NSRange(gauche.startIndex..., in: gauche)) != nil {
                return true
            }
        }
        if let url = URLComponents(string: v), url.scheme != nil {
            if url.password != nil || url.user != nil { return true }
            for item in url.queryItems ?? [] where item.value.map({ !$0.isEmpty }) ?? false {
                if nomSecret.firstMatch(in: item.name, range: NSRange(item.name.startIndex..., in: item.name)) != nil
                    || estSecret(item.value ?? "") {
                    return true
                }
            }
            return false
        }
        return aspectAleatoire(v)
    }

    /// Une longue chaîne sans espace, sans structure de chemin ni de nom de paquet, qui mêle
    /// lettres et chiffres et dont les caractères sont très variés : l'allure d'une clé.
    static func aspectAleatoire(_ v: String) -> Bool {
        guard v.count >= 20, v.count <= 512 else { return false }
        if v.hasPrefix("/") || v.hasPrefix("~") || v.hasPrefix("@") || v.hasPrefix("-") || v.hasPrefix(".") {
            return false
        }
        let admis = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/=_-")
        guard v.unicodeScalars.allSatisfy({ admis.contains($0) }) else { return false }
        let chiffres = v.filter(\.isNumber).count
        let lettres = v.filter(\.isLetter).count
        guard chiffres >= 2, lettres >= 2 else { return false }
        // Hexadécimal de 32 caractères ou plus : clé d'API probable.
        if v.count >= 32, v.allSatisfy(\.isHexDigit) { return true }
        return entropie(v) >= 3.6
    }

    static func entropie(_ v: String) -> Double {
        var compte: [Character: Int] = [:]
        for c in v { compte[c, default: 0] += 1 }
        let n = Double(v.count)
        return -compte.values.reduce(0) { somme, k in
            let p = Double(k) / n
            return somme + p * log2(p)
        }
    }

    /// Arguments de lancement sans aucun secret : l'option qui annonce un secret part avec la
    /// valeur qui la suit, `--cle=valeur` part en entier, toute valeur à l'allure de clé part.
    public static func argumentsSurs(_ arguments: [String]) -> [String] {
        var sortie: [String] = []
        var i = 0
        while i < arguments.count {
            let a = arguments[i]
            let plage = NSRange(a.startIndex..., in: a)
            if optionSecrete.firstMatch(in: a, range: plage) != nil {
                // L'option et sa valeur, si la suivante n'est pas une autre option.
                if i + 1 < arguments.count, !arguments[i + 1].hasPrefix("-") { i += 1 }
                i += 1
                continue
            }
            if a.hasPrefix("-"), let egal = a.firstIndex(of: "=") {
                let nom = String(a[..<egal])
                if optionSecrete.firstMatch(in: nom, range: NSRange(nom.startIndex..., in: nom)) != nil {
                    i += 1
                    continue
                }
            }
            if !estSecret(a) { sortie.append(a) }
            i += 1
        }
        return sortie
    }

    /// Dernier garde-fou avant un envoi : remplace toute chaîne qui ressemble à un secret, à
    /// n'importe quelle profondeur d'un objet JSON.
    public static func purger(_ objet: Any) -> Any {
        switch objet {
        case let s as String:
            return estSecret(s) ? "[masqué]" : s
        case let liste as [Any]:
            return liste.map(purger)
        case let dico as [String: Any]:
            return dico.mapValues(purger)
        default:
            return objet
        }
    }
}
