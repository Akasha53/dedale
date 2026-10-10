import AppKit
import CoreServices

/// Les navigateurs que Dédale sait lire. Chrome et Safari seulement : les autres
/// (Arc, Firefox, Edge…) ne sont pas surveillés.
enum Navigateur: String, CaseIterable {
    case safari = "com.apple.Safari"
    case chrome = "com.google.Chrome"

    var nom: String { self == .safari ? "Safari" : "Chrome" }
}

/// L'onglet actif d'un navigateur, tel que lu par AppleScript : son adresse, et de quoi le
/// retrouver pour reculer ou le fermer (identifiant de fenêtre, puis identifiant d'onglet pour
/// Chrome, position de l'onglet pour Safari).
struct OngletLu {
    let navigateur: Navigateur
    let adresse: String
    let fenetre: Int
    let onglet: Int

    var cle: String { "\(navigateur.rawValue)/\(fenetre)/\(onglet)" }
}

/// Lit l'adresse de l'onglet actif de Safari ou Chrome par AppleScript, et rien d'autre :
/// ni le contenu des pages, ni l'historique. Chaque lecture est bornée à 2 s.
///
/// La première fois, macOS demande à la personne d'autoriser Dédale à contrôler le
/// navigateur (clé NSAppleEventsUsageDescription). La demande part d'un fil secondaire par
/// AEDeterminePermissionToAutomateTarget : l'interface ne gèle pas pendant qu'elle attend.
final class LecteurNavigateurs {
    enum Permission: String { case inconnue, enCours = "en_cours", accordee, refusee }

    private(set) var permissions: [Navigateur: Permission] = [:]
    private var scripts: [Navigateur: NSAppleScript] = [:]
    private var derniereRelecture: [Navigateur: Date] = [:]

    func permission(_ n: Navigateur) -> Permission { permissions[n] ?? .inconnue }

    /// Vérifie (et demande si besoin) l'autorisation de piloter le navigateur, hors du fil
    /// principal. `fin` est appelé sur le fil principal. Un refus est relu toutes les 10 s,
    /// sans redemander : la personne peut l'accorder plus tard dans Réglages Système.
    func verifierPermission(_ n: Navigateur, fin: @escaping (Permission) -> Void) {
        let actuelle = permission(n)
        if actuelle == .enCours { return }
        if actuelle == .refusee, let d = derniereRelecture[n], Date().timeIntervalSince(d) < 10 { return }
        derniereRelecture[n] = Date()
        let demander = actuelle == .inconnue
        permissions[n] = .enCours
        DispatchQueue.global(qos: .userInitiated).async {
            let cible = NSAppleEventDescriptor(bundleIdentifier: n.rawValue)
            var statut = AEDeterminePermissionToAutomateTarget(cible.aeDesc, AEEventClass(typeWildCard),
                                                                AEEventID(typeWildCard), false)
            if statut == OSStatus(errAEEventWouldRequireUserConsent), demander {
                journal("sites : demande d'autorisation pour \(n.nom) (macOS va poser la question)")
                statut = AEDeterminePermissionToAutomateTarget(cible.aeDesc, AEEventClass(typeWildCard),
                                                                AEEventID(typeWildCard), true)
            }
            let resultat: Permission
            switch statut {
            case noErr: resultat = .accordee
            case OSStatus(errAEEventNotPermitted): resultat = .refusee
            case OSStatus(errAEEventWouldRequireUserConsent): resultat = .refusee
            default: resultat = .inconnue   // navigateur fermé entre-temps (-600) : on réessaiera
            }
            DispatchQueue.main.async {
                if self.permissions[n] != resultat {
                    journal("sites : autorisation \(n.nom) → \(resultat.rawValue) (statut \(statut))")
                }
                self.permissions[n] = resultat
                fin(resultat)
            }
        }
    }

    /// Adresse de l'onglet actif de la fenêtre de devant, ou nil (pas de fenêtre, onglet vide,
    /// erreur). À appeler sur le fil principal, une fois l'autorisation accordée.
    func lire(_ n: Navigateur) -> OngletLu? {
        let script: NSAppleScript
        if let s = scripts[n] {
            script = s
        } else {
            let source = n == .safari ? """
                with timeout of 2 seconds
                    tell application id "com.apple.Safari"
                        if (count of windows) is 0 then return ""
                        set w to front window
                        try
                            set t to current tab of w
                        on error
                            return ""
                        end try
                        set u to URL of t
                        if u is missing value then return ""
                        return u & linefeed & (id of w as text) & linefeed & (index of t as text)
                    end tell
                end timeout
                """ : """
                with timeout of 2 seconds
                    tell application id "com.google.Chrome"
                        if (count of windows) is 0 then return ""
                        set w to front window
                        set t to active tab of w
                        set u to URL of t
                        if u is missing value then return ""
                        return u & linefeed & (id of w as text) & linefeed & (id of t as text)
                    end tell
                end timeout
                """
            guard let s = NSAppleScript(source: source) else { return nil }
            scripts[n] = s
            script = s
        }
        guard let texte = executer(script, n) else { return nil }
        let morceaux = texte.components(separatedBy: "\n")
        guard morceaux.count == 3, let f = Int(morceaux[1]), let o = Int(morceaux[2]),
              !morceaux[0].isEmpty else { return nil }
        return OngletLu(navigateur: n, adresse: morceaux[0], fenetre: f, onglet: o)
    }

    /// « Revenir en arrière ». Chrome : retour arrière dans l'onglet, puis fermeture s'il
    /// reste sur le même site (onglet sans historique). Safari, qui n'a pas de commande de
    /// retour : la dernière page sûre vue dans cet onglet si on la connaît, sinon fermeture.
    func revenir(_ o: OngletLu, pageSure: String?, encoreLa: @escaping (String) -> Bool) {
        switch o.navigateur {
        case .chrome:
            _ = executer(source: chrome(o, action: "go back t"), o.navigateur)
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { [self] in
                let actuelle = executer(source: chrome(o, action: "return URL of t"), o.navigateur) ?? ""
                if encoreLa(actuelle) {
                    journal("sites : pas d'historique dans l'onglet, fermeture")
                    _ = executer(source: chrome(o, action: "close t"), o.navigateur)
                }
            }
        case .safari:
            if let page = pageSure, naviguerSafari(fenetre: o.fenetre, onglet: o.onglet, vers: page) {
                return
            }
            _ = executer(source: safari(o, action: "close t"), o.navigateur)
        }
    }

    /// Charge une adresse dans un onglet de Safari (l'onglet courant si `onglet` est nil).
    /// Safari refuse parfois l'écriture de URL sur une référence d'onglet (-10006) : le script
    /// essaie alors d'autres formes, de la plus précise à la plus large.
    @discardableResult
    func naviguerSafari(fenetre: Int, onglet: Int?, vers adresse: String) -> Bool {
        guard let u = Self.chaineAppleScript(adresse) else { return false }
        let t = onglet.map { "tab \($0) of window id \(fenetre)" } ?? "current tab of window id \(fenetre)"
        let source = """
            with timeout of 3 seconds
                tell application id "com.apple.Safari"
                    try
                        set URL of \(t) to \(u)
                        return "1"
                    end try
                    try
                        tell \(t) to set URL to \(u)
                        return "2"
                    end try
                    try
                        set d to (first document whose name is (name of \(t)))
                        set URL of d to \(u)
                        return "3"
                    end try
                    \(onglet == nil ? """
                    try
                        set n to make new tab at end of tabs of window id \(fenetre) with properties {URL:\(u)}
                        set current tab of window id \(fenetre) to n
                        return "4"
                    end try
                    """ : "")
                    return "0"
                end tell
            end timeout
            """
        let r = executer(source: source, .safari) ?? "0"
        if r != "1" { journal("sites : Safari, changement d'adresse par la forme \(r)") }
        if r == "0" { journal("sites : Safari refuse de changer d'adresse dans la fenêtre \(fenetre)") }
        return r != "0"
    }

    // MARK: Scripts

    private func chrome(_ o: OngletLu, action: String) -> String {
        """
        with timeout of 3 seconds
            tell application id "com.google.Chrome"
                repeat with w in windows
                    if id of w is \(o.fenetre) then
                        repeat with t in tabs of w
                            if id of t is \(o.onglet) then
                                \(action)
                                return ""
                            end if
                        end repeat
                    end if
                end repeat
            end tell
        end timeout
        return ""
        """
    }

    private func safari(_ o: OngletLu, action: String) -> String {
        """
        with timeout of 3 seconds
            tell application id "com.apple.Safari"
                set t to tab \(o.onglet) of window id \(o.fenetre)
                \(action)
            end tell
        end timeout
        return ""
        """
    }

    /// Chaîne AppleScript entre guillemets, ou nil si l'adresse porte un caractère de contrôle.
    static func chaineAppleScript(_ texte: String) -> String? {
        guard !texte.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { return nil }
        let echappe = texte.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
        return "\"\(echappe)\""
    }

    /// Script libre sur Safari (essai réel seulement). Renvoie sa sortie texte, ou nil.
    func script(_ source: String) -> String? {
        executer(source: source, .safari)
    }

    private func executer(source: String, _ n: Navigateur) -> String? {
        guard let s = NSAppleScript(source: source) else { return nil }
        return executer(s, n)
    }

    private func executer(_ script: NSAppleScript, _ n: Navigateur) -> String? {
        var erreur: NSDictionary?
        let sortie = script.executeAndReturnError(&erreur)
        if let erreur {
            let code = erreur[NSAppleScript.errorNumber] as? Int ?? 0
            if code == -1743 {
                permissions[n] = .refusee
                journal("sites : \(n.nom) refuse le contrôle par Dédale (Réglages Système, Automatisation)")
            } else if code != -1728 && code != -1719 {
                // -1728 / -1719 : fenêtre ou onglet disparu entre deux lectures, sans gravité.
                journal("sites : AppleScript \(n.nom) en erreur \(code)")
            }
            return nil
        }
        return sortie.stringValue
    }
}
