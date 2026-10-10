import Foundation

/// Inventaire des assistants et agents IA configurés sur un Mac, à partir des fichiers de
/// configuration MCP des clients connus (Claude Desktop, Claude Code, Cursor, VS Code,
/// Windsurf, Cline, Zed, Gemini CLI, Codex, LM Studio).
///
/// Ce qui est extrait de chaque serveur : son nom, et de quoi deviner son type (la commande
/// de lancement, ses arguments passés au filtre des secrets, l'hôte d'une URL distante). Les
/// clés `env`, `headers` et toutes les autres ne sont jamais extraites : leurs valeurs ne
/// sont ni gardées, ni journalisées, ni envoyées. Les arguments eux-mêmes ne sortent pas de
/// cette analyse : le résultat ne porte que le client, le nom du serveur, ses types, ses
/// droits risqués et son transport.
public enum InventaireAgents {
    /// Un serveur MCP tel qu'il part à la SOC.
    public struct Serveur: Codable, Equatable, Sendable {
        /// Nom du client (« Claude Desktop »).
        public let client: String
        /// Identifiant stable du client (`claude_desktop`).
        public let clientId: String
        /// Nom du serveur dans la configuration, nettoyé et passé au filtre des secrets.
        public let nom: String
        /// Types déduits : `fichiers`, `shell`, `mail`, `navigateur`, `reseau`, `autre`.
        public let types: [String]
        /// Droits risqués : `shell`, `mail`, `disque_entier`.
        public let droitsRisques: [String]
        /// `local` (commande lancée sur le Mac) ou `distant` (URL).
        public let transport: String

        enum CodingKeys: String, CodingKey {
            case client, nom, types, transport
            case clientId = "client_id"
            case droitsRisques = "droits_risques"
        }
    }

    public struct Resultat: Equatable, Sendable {
        public var serveurs: [Serveur] = []
        /// Clients dont au moins un fichier de configuration a été trouvé.
        public var clients: [String] = []
        /// Nombre de fichiers lus.
        public var fichiersLus = 0
        /// Fichiers trouvés mais illisibles (JSON invalide, trop gros).
        public var fichiersIllisibles = 0

        public var risques: Int { serveurs.filter { !$0.droitsRisques.isEmpty }.count }
    }

    /// Un client connu et ses fichiers de configuration, relatifs au dossier personnel.
    struct Client {
        enum Lecture {
            /// Dictionnaire de serveurs à ces chemins de clés, dans un fichier JSON (commentaires admis).
            case json([[String]])
            /// Fichier TOML de Codex : sections `[mcp_servers.<nom>]`.
            case tomlCodex
        }
        let id: String
        let nom: String
        let fichiers: [(String, Lecture)]
    }

    static let clients: [Client] = [
        Client(id: "claude_desktop", nom: "Claude Desktop", fichiers: [
            ("Library/Application Support/Claude/claude_desktop_config.json", .json([["mcpServers"]])),
        ]),
        Client(id: "claude_code", nom: "Claude Code", fichiers: [
            (".claude.json", .json([["mcpServers"], ["projects", "*", "mcpServers"]])),
        ]),
        Client(id: "cursor", nom: "Cursor", fichiers: [
            (".cursor/mcp.json", .json([["mcpServers"]])),
        ]),
        Client(id: "vscode", nom: "VS Code", fichiers: [
            ("Library/Application Support/Code/User/mcp.json", .json([["servers"]])),
            ("Library/Application Support/Code/User/settings.json", .json([["mcp", "servers"]])),
        ]),
        Client(id: "windsurf", nom: "Windsurf", fichiers: [
            (".codeium/windsurf/mcp_config.json", .json([["mcpServers"]])),
        ]),
        Client(id: "cline", nom: "Cline", fichiers: [
            ("Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json",
             .json([["mcpServers"]])),
        ]),
        Client(id: "zed", nom: "Zed", fichiers: [
            (".config/zed/settings.json", .json([["context_servers"]])),
        ]),
        Client(id: "gemini_cli", nom: "Gemini CLI", fichiers: [
            (".gemini/settings.json", .json([["mcpServers"]])),
        ]),
        Client(id: "codex", nom: "Codex", fichiers: [
            (".codex/config.toml", .tomlCodex),
        ]),
        Client(id: "lm_studio", nom: "LM Studio", fichiers: [
            (".lmstudio/mcp.json", .json([["mcpServers"]])),
        ]),
    ]

    /// Noms des clients reconnus, pour l'affichage.
    public static var clientsConnus: [String] { clients.map(\.nom) }

    /// Taille maximale d'un fichier de configuration lu (1 Mo).
    static let tailleMax = 1 << 20

    /// Ce que l'analyse retient d'un serveur avant de le classer. Rien de cette structure ne
    /// sort de ce fichier.
    struct Indices {
        var nom: String
        var commande: String?
        var arguments: [String]
        var hoteDistant: String?
        var distant: Bool
    }

    /// Analyse les configurations trouvées sous `racine` (le dossier personnel, ou un dossier
    /// factice qui en reproduit l'arborescence).
    public static func analyser(racine: URL) -> Resultat {
        var r = Resultat()
        for client in clients {
            var trouve = false
            for (relatif, lecture) in client.fichiers {
                let url = racine.appendingPathComponent(relatif)
                guard let attributs = try? FileManager.default.attributesOfItem(atPath: url.path),
                      (attributs[.type] as? FileAttributeType) == .typeRegular else { continue }
                trouve = true
                let taille = (attributs[.size] as? NSNumber)?.intValue ?? 0
                guard taille <= tailleMax, let donnees = try? Data(contentsOf: url) else {
                    r.fichiersIllisibles += 1
                    continue
                }
                r.fichiersLus += 1
                let indices: [Indices]?
                switch lecture {
                case .json(let chemins): indices = lireJSON(donnees, chemins: chemins)
                case .tomlCodex: indices = lireTOMLCodex(donnees)
                }
                guard let indices else {
                    r.fichiersIllisibles += 1
                    continue
                }
                for i in indices {
                    let s = classer(i, client: client)
                    if !r.serveurs.contains(s) { r.serveurs.append(s) }
                }
            }
            if trouve { r.clients.append(client.nom) }
        }
        return r
    }

    // MARK: Lecture

    /// Lit les dictionnaires de serveurs aux chemins donnés. `*` parcourt toutes les clés
    /// d'un niveau (les projets de Claude Code).
    static func lireJSON(_ donnees: Data, chemins: [[String]]) -> [Indices]? {
        guard let racine = try? JSONSerialization.jsonObject(with: donnees, options: [.json5Allowed]),
              let objet = racine as? [String: Any] else { return nil }
        var sortie: [Indices] = []
        for chemin in chemins {
            for dico in descendre(objet, chemin[...]) {
                for (nom, valeur) in dico {
                    guard let serveur = valeur as? [String: Any] else { continue }
                    sortie.append(extraire(nom: nom, serveur))
                }
            }
        }
        return sortie
    }

    private static func descendre(_ objet: [String: Any], _ chemin: ArraySlice<String>) -> [[String: Any]] {
        guard let tete = chemin.first else { return [objet] }
        let reste = chemin.dropFirst()
        if tete == "*" {
            return objet.values.compactMap { $0 as? [String: Any] }.flatMap { descendre($0, reste) }
        }
        guard let suivant = objet[tete] as? [String: Any] else { return [] }
        return descendre(suivant, reste)
    }

    /// Extrait d'un serveur JSON les seules clés utiles : `command`, `args`, `url` (ou
    /// `serverUrl`, `httpUrl`) et `type`. Zed range la commande dans `command.path`.
    static func extraire(nom: String, _ s: [String: Any]) -> Indices {
        var commande: String?
        var arguments: [String] = []
        if let c = s["command"] as? String {
            commande = c
        } else if let c = s["command"] as? [String: Any] {
            commande = c["path"] as? String
            arguments = (c["args"] as? [Any])?.compactMap { $0 as? String } ?? []
        }
        if let a = s["args"] as? [Any] { arguments = a.compactMap { $0 as? String } }
        let url = (s["url"] ?? s["serverUrl"] ?? s["httpUrl"]) as? String
        let type = (s["type"] as? String)?.lowercased() ?? ""
        let distant = url != nil || ["sse", "http", "streamable-http", "streamablehttp"].contains(type)
        return Indices(nom: nom, commande: commande, arguments: FiltreSecrets.argumentsSurs(arguments),
                       hoteDistant: url.flatMap(hote), distant: distant)
    }

    /// Codex : `[mcp_servers.nom]` puis `command = "…"`, `args = ["…"]`, `url = "…"`. Les
    /// sous-sections (`[mcp_servers.nom.env]`) et toute autre clé sont ignorées.
    static func lireTOMLCodex(_ donnees: Data) -> [Indices]? {
        guard let texte = String(data: donnees, encoding: .utf8) else { return nil }
        var serveurs: [(String, [String: String])] = []
        var courant: Int?
        for ligneBrute in texte.split(whereSeparator: \.isNewline) {
            let ligne = ligneBrute.trimmingCharacters(in: .whitespaces)
            if ligne.hasPrefix("[") {
                courant = nil
                guard ligne.hasPrefix("[mcp_servers."), ligne.hasSuffix("]"), !ligne.hasPrefix("[[") else { continue }
                var nom = String(ligne.dropFirst("[mcp_servers.".count).dropLast())
                if nom.hasPrefix("\""), nom.hasSuffix("\""), nom.count >= 2 {
                    nom = String(nom.dropFirst().dropLast())
                } else if nom.contains(".") {
                    continue  // sous-section : env, en-têtes…
                }
                serveurs.append((nom, [:]))
                courant = serveurs.count - 1
                continue
            }
            guard let i = courant, let egal = ligne.firstIndex(of: "=") else { continue }
            let cle = ligne[..<egal].trimmingCharacters(in: .whitespaces)
            guard ["command", "args", "url"].contains(cle) else { continue }
            serveurs[i].1[cle] = ligne[ligne.index(after: egal)...].trimmingCharacters(in: .whitespaces)
        }
        return serveurs.map { nom, cles in
            let commande = cles["command"].flatMap(chainesTOML).flatMap(\.first)
            let arguments = cles["args"].flatMap(chainesTOML) ?? []
            let url = cles["url"].flatMap(chainesTOML).flatMap(\.first)
            return Indices(nom: nom, commande: commande, arguments: FiltreSecrets.argumentsSurs(arguments),
                           hoteDistant: url.flatMap(hote), distant: url != nil)
        }
    }

    /// Chaînes entre guillemets d'une valeur TOML sur une ligne (`"a"` ou `["a", "b"]`).
    static func chainesTOML(_ valeur: String) -> [String]? {
        var sortie: [String] = []
        var courante: String?
        var echappe = false
        for c in valeur {
            if var s = courante {
                if echappe { s.append(c); echappe = false; courante = s; continue }
                if c == "\\" { echappe = true; continue }
                if c == "\"" { sortie.append(s); courante = nil; continue }
                s.append(c)
                courante = s
            } else if c == "\"" {
                courante = ""
            } else if c == "#" {
                break
            }
        }
        return sortie.isEmpty ? nil : sortie
    }

    static func hote(_ url: String) -> String? {
        guard let u = URLComponents(string: url), let h = u.host, !h.isEmpty else { return nil }
        return h.lowercased()
    }

    // MARK: Classement

    /// Lanceurs génériques : leur nom ne dit rien du serveur (`npx -y paquet`).
    static let lanceurs: Set<String> = ["npx", "node", "uvx", "uv", "python", "python3", "docker", "podman", "bunx",
                                        "bun", "pipx", "deno", "pnpm", "yarn", "npm", "env", "sh", "bash", "zsh"]

    static let motsCles: [(String, [String])] = [
        ("shell", ["shell", "terminal", "bash", "zsh", "exec", "commander", "iterm", "tmux", "ssh", "osascript",
                   "applescript", "run-command", "command-runner", "cli-mcp", "mcp-cli", "kubectl", "powershell"]),
        ("mail", ["mail", "gmail", "outlook", "imap", "smtp", "courriel", "resend", "sendgrid", "postmark", "mailgun",
                  "exchange", "proton"]),
        ("navigateur", ["browser", "playwright", "puppeteer", "chrome", "chromium", "selenium", "browserbase",
                        "webdriver", "navigateur", "safari", "firefox"]),
        ("fichiers", ["filesystem", "file-system", "fichier", "files", "desktop-commander", "obsidian", "drive",
                      "dropbox", "documents", "notes"]),
        ("reseau", ["fetch", "http", "web", "search", "brave", "tavily", "exa", "perplexity", "slack", "github",
                    "gitlab", "notion", "linear", "jira", "api", "recherche", "internet"]),
    ]

    static func classer(_ i: Indices, client: Client) -> Serveur {
        // Ce qui identifie le serveur : son nom, la commande si ce n'est pas un lanceur, et
        // les arguments qui ne sont ni des options ni des chemins.
        var identite = [i.nom.lowercased()]
        if let c = i.commande {
            let base = (c as NSString).lastPathComponent.lowercased()
            if !lanceurs.contains(base) { identite.append(base) }
        }
        identite += i.arguments.filter { !$0.hasPrefix("-") && !$0.hasPrefix("/") && !$0.hasPrefix("~") }
            .map { $0.lowercased() }
        if let h = i.hoteDistant { identite.append(h) }
        let texte = identite.joined(separator: " ")

        let jetons = texte.split(whereSeparator: { !$0.isLetter && !$0.isNumber }).map(String.init)
        var types: [String] = []
        for (type, mots) in motsCles where mots.contains(where: { correspond($0, texte: texte, jetons: jetons) }) {
            types.append(type)
        }
        if texte.contains("desktop-commander"), !types.contains("fichiers") { types.append("fichiers") }
        if i.distant, !types.contains("reseau") { types.append("reseau") }
        if types.isEmpty { types = ["autre"] }

        var droits: [String] = []
        if types.contains("shell") { droits.append("shell") }
        if types.contains("mail") { droits.append("mail") }
        if types.contains("fichiers"), accesDisqueEntier(i, texte: texte) { droits.append("disque_entier") }

        return Serveur(client: client.nom, clientId: client.id, nom: nomSur(i.nom), types: types,
                       droitsRisques: droits, transport: i.distant ? "distant" : "local")
    }

    /// Un mot clé composé (`desktop-commander`) se cherche dans le texte ; un mot simple doit
    /// être un jeton entier, ou en être le début ou la fin s'il a au moins 4 lettres (`gmail`,
    /// `websearch`). Ainsi `exa` ne se trouve pas dans `example`.
    static func correspond(_ mot: String, texte: String, jetons: [String]) -> Bool {
        if mot.contains("-") { return texte.contains(mot) }
        return jetons.contains { j in
            j == mot || (mot.count >= 4 && (j.hasPrefix(mot) || j.hasSuffix(mot)))
        }
    }

    /// Tout le disque : un dossier racine ou personnel ouvert à un serveur de fichiers, ou un
    /// serveur qui a le shell et les fichiers (Desktop Commander lit tout le disque par défaut).
    static func accesDisqueEntier(_ i: Indices, texte: String) -> Bool {
        if texte.contains("desktop-commander") { return true }
        for a in i.arguments {
            var chemin = a
            if let egal = a.firstIndex(of: "="), a.hasPrefix("-") { chemin = String(a[a.index(after: egal)...]) }
            let p = chemin.trimmingCharacters(in: CharacterSet(charactersIn: " /")).lowercased()
            if chemin.hasPrefix("/") || chemin.hasPrefix("~") || chemin.hasPrefix("$home") {
                let parties = p.split(separator: "/")
                if p.isEmpty || p == "~" || p == "$home" || p == "${home}" { return true }
                if parties.first == "users" || parties.first == "home", parties.count <= 2 { return true }
                if parties.first == "volumes", parties.count <= 1 { return true }
            }
        }
        return false
    }

    /// Nom affichable et envoyable : sans caractères de contrôle ni bidirectionnels, 64
    /// caractères au plus, et masqué s'il a l'allure d'un secret.
    public static func nomSur(_ brut: String) -> String {
        let interdits: Set<UInt32> = [0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069, 0x200B,
                                      0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF]
        let propre = brut.unicodeScalars.filter {
            !CharacterSet.controlCharacters.contains($0) && !interdits.contains($0.value)
        }
        let texte = String(String.UnicodeScalarView(propre)).trimmingCharacters(in: .whitespaces)
        if texte.isEmpty { return "(sans nom)" }
        if FiltreSecrets.estSecret(texte) { return "nom masqué" }
        return texte.count > 64 ? String(texte.prefix(63)) + "…" : texte
    }

    // MARK: Envoi

    /// Corps de `POST /api/agents/poste` (voir CONTRATS.md), passé au filtre des secrets.
    public static func charge(_ r: Resultat, poste: String, source: String, horodatage: String) -> [String: Any] {
        let agents: [[String: Any]] = r.serveurs.map {
            ["client": $0.client, "client_id": $0.clientId, "serveur": $0.nom, "types": $0.types,
             "droits_risques": $0.droitsRisques, "transport": $0.transport]
        }
        let corps: [String: Any] = [
            "poste": poste,
            "contexte": "poste",
            "source_config": source,
            "horodatage": horodatage,
            "clients": r.clients,
            "agents": agents,
        ]
        return FiltreSecrets.purger(corps) as? [String: Any] ?? [:]
    }
}
