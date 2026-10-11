import DedaleNoyau
import XCTest

/// Le jeton n'est jamais écrit en clair dans ce fichier : il est assemblé à l'exécution, pour
/// que les détecteurs de secrets du dépôt ne le prennent pas pour une vraie clé.
private let jeton = "ghp_" + String(repeating: "Zq7", count: 12)
private let cleAPI = "sk-" + "ant-" + String(repeating: "Xy9w", count: 8)
private let motDePasse = "Mdp" + String(repeating: "8x", count: 9)

final class FiltreSecretsTests: XCTestCase {
    func testJetonsConnus() {
        XCTAssertTrue(FiltreSecrets.estSecret(jeton))
        XCTAssertTrue(FiltreSecrets.estSecret(cleAPI))
        XCTAssertTrue(FiltreSecrets.estSecret("Bearer " + String(repeating: "a1", count: 12)))
        XCTAssertTrue(FiltreSecrets.estSecret("token=" + motDePasse))
        XCTAssertTrue(FiltreSecrets.estSecret("https://mcp.recherche.example/sse?cle=" + motDePasse))
        XCTAssertTrue(FiltreSecrets.estSecret("https://camille:" + motDePasse + "@imap.orbispay.example"))
        XCTAssertTrue(FiltreSecrets.estSecret(String(repeating: "a3f9", count: 10)), "hexadécimal long")
    }

    func testValeursOrdinaires() {
        for v in ["-y", "@modelcontextprotocol/server-filesystem", "/Users/camille/Documents",
                  "desktop-commander", "mcp-server-sqlite", "imap.orbispay.example", "ghcr.io/orbis/mcp-mail:1.2.0",
                  "fichiers-camille", "https://mcp.recherche.example/sse", "Claude Desktop"] {
            XCTAssertFalse(FiltreSecrets.estSecret(v), v)
        }
    }

    func testArgumentsSurs() {
        let args = ["-y", "mcp-mail-imap", "--host", "imap.orbispay.example", "--password", motDePasse,
                    "--api-key=" + cleAPI, "--token", jeton, jeton, "--verbose"]
        let surs = FiltreSecrets.argumentsSurs(args)
        XCTAssertEqual(surs, ["-y", "mcp-mail-imap", "--host", "imap.orbispay.example", "--verbose"])
    }

    func testPurgerDescendDansLObjet() {
        let objet: [String: Any] = ["a": ["b": jeton], "c": [1, cleAPI, "ok"]]
        let propre = FiltreSecrets.purger(objet) as! [String: Any]
        let texte = String(describing: propre)
        XCTAssertFalse(texte.contains(jeton))
        XCTAssertFalse(texte.contains(cleAPI))
        XCTAssertTrue(texte.contains("ok"))
    }
}

final class InventaireAgentsTests: XCTestCase {
    private var racine: URL!

    override func setUpWithError() throws {
        racine = FileManager.default.temporaryDirectory.appendingPathComponent("dedale-agents-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: racine, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: racine)
    }

    private func ecrire(_ relatif: String, _ texte: String) throws {
        let url = racine.appendingPathComponent(relatif)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data(texte.utf8).write(to: url)
    }

    /// Une configuration factice qui porte le jeton partout où un vrai fichier peut en avoir :
    /// variable d'environnement, argument, option, URL, en-tête, et même nom de serveur.
    private func configurationPiegee() throws {
        try ecrire("Library/Application Support/Claude/claude_desktop_config.json", """
        {
          "mcpServers": {
            "fichiers-camille": {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/camille"]
            },
            "github": {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-github", "--token", "\(jeton)"],
              "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "\(jeton)" }
            },
            "\(jeton)": { "command": "node", "args": ["serveur.js"] }
          },
          "globalShortcut": "Cmd+Shift+Space"
        }
        """)
        try ecrire(".cursor/mcp.json", """
        {
          "mcpServers": {
            "terminal": { "command": "npx", "args": ["-y", "@wonderwhy-er/desktop-commander"] },
            "navigateur": { "command": "npx", "args": ["@playwright/mcp@latest"], "env": { "API_KEY": "\(cleAPI)" } },
            "recherche": { "url": "https://mcp.recherche.example/sse?cle=\(jeton)",
                           "headers": { "Authorization": "Bearer \(jeton)" } }
          }
        }
        """)
        // VS Code : JSON avec commentaires et virgules finales.
        try ecrire("Library/Application Support/Code/User/mcp.json", """
        {
          // boîte mail de l'équipe
          "servers": {
            "boite-mail-orbis": {
              "type": "stdio",
              "command": "uvx",
              "args": ["mcp-mail-imap", "--host", "imap.orbispay.example", "--password=\(motDePasse)",],
            },
          },
        }
        """)
        try ecrire(".codex/config.toml", """
        model = "gpt-5"

        [mcp_servers.documents-equipe]
        command = "npx"
        args = ["-y", "@modelcontextprotocol/server-filesystem", "/Users/camille/Documents/Orbis"]

        [mcp_servers.documents-equipe.env]
        JETON = "\(jeton)"

        [mcp_servers.tableur]
        url = "https://tableur.orbispay.example/mcp"
        """)
    }

    func testInventaireComplet() throws {
        try configurationPiegee()
        let r = InventaireAgents.analyser(racine: racine)
        XCTAssertEqual(r.clients, ["Claude Desktop", "Cursor", "VS Code", "Codex"])
        XCTAssertEqual(r.fichiersLus, 4)
        XCTAssertEqual(r.fichiersIllisibles, 0)

        func serveur(_ nom: String) -> InventaireAgents.Serveur? { r.serveurs.first { $0.nom == nom } }

        let fichiers = try XCTUnwrap(serveur("fichiers-camille"))
        XCTAssertEqual(fichiers.types, ["fichiers"])
        XCTAssertEqual(fichiers.droitsRisques, ["disque_entier"])
        XCTAssertEqual(fichiers.transport, "local")

        XCTAssertEqual(serveur("github")?.types, ["reseau"])
        XCTAssertEqual(serveur("github")?.droitsRisques, [])

        let terminal = try XCTUnwrap(serveur("terminal"))
        XCTAssertTrue(terminal.types.contains("shell"))
        XCTAssertTrue(terminal.types.contains("fichiers"))
        XCTAssertEqual(Set(terminal.droitsRisques), ["shell", "disque_entier"])

        XCTAssertEqual(serveur("navigateur")?.types, ["navigateur"])
        XCTAssertEqual(serveur("recherche")?.transport, "distant")
        XCTAssertEqual(serveur("recherche")?.types, ["reseau"])

        let mail = try XCTUnwrap(serveur("boite-mail-orbis"))
        XCTAssertEqual(mail.client, "VS Code")
        XCTAssertEqual(mail.droitsRisques, ["mail"])

        let documents = try XCTUnwrap(serveur("documents-equipe"))
        XCTAssertEqual(documents.client, "Codex")
        XCTAssertEqual(documents.types, ["fichiers"])
        XCTAssertEqual(documents.droitsRisques, [], "un sous-dossier n'est pas tout le disque")
        XCTAssertEqual(serveur("tableur")?.transport, "distant")

        XCTAssertNotNil(serveur("nom masqué"), "un nom de serveur qui ressemble à un jeton est masqué")

        // Les assistants qui tournent en terminal comptent par eux-mêmes : Cursor et Codex ont
        // le shell et tout le disque, serveurs MCP ou pas. Claude Desktop et VS Code, non.
        let cursor = try XCTUnwrap(r.serveurs.first { $0.nom == "Cursor" && $0.agentTerminal })
        XCTAssertEqual(cursor.client, "Cursor")
        XCTAssertEqual(Set(cursor.droitsRisques), ["shell", "disque_entier"])
        let codexAgent = try XCTUnwrap(r.serveurs.first { $0.nom == "Codex" && $0.agentTerminal })
        XCTAssertEqual(Set(codexAgent.droitsRisques), ["shell", "disque_entier"])
        XCTAssertFalse(r.serveurs.contains { $0.agentTerminal && $0.client == "Claude Desktop" },
                       "Claude Desktop est une app sandboxée, pas un agent en terminal")
        XCTAssertFalse(r.serveurs.contains { $0.agentTerminal && $0.client == "VS Code" })

        // 3 serveurs MCP risqués (fichiers-camille, terminal, boîte mail) + 2 agents en terminal.
        XCTAssertEqual(r.risques, 5)
    }

    func testServeursRisquesParNomEtCommande() throws {
        try ecrire(".codex/config.toml", """
        model = "gpt-5"

        [mcp_servers.computer-use]
        command = "./Codex Computer Use.app/Contents/MacOS/SkyComputerUseClient"
        args = ["mcp"]

        [mcp_servers.node_repl]
        command = "/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node_repl"
        args = []

        [mcp_servers.console]
        command = "bash"
        args = ["-c", "serveur-maison"]

        [mcp_servers.replicate-images]
        command = "npx"
        args = ["-y", "replicate-mcp"]
        """)
        let r = InventaireAgents.analyser(racine: racine)
        func serveur(_ nom: String) -> InventaireAgents.Serveur? { r.serveurs.first { $0.nom == nom } }

        let cu = try XCTUnwrap(serveur("computer-use"))
        XCTAssertTrue(cu.types.contains("shell"), "le contrôle clavier/souris/écran vaut un accès shell")
        XCTAssertEqual(cu.droitsRisques, ["shell"])

        let repl = try XCTUnwrap(serveur("node_repl"))
        XCTAssertTrue(repl.types.contains("shell"), "exécuter du code arbitraire vaut le shell")
        XCTAssertEqual(repl.droitsRisques, ["shell"])

        let console = try XCTUnwrap(serveur("console"))
        XCTAssertTrue(console.types.contains("shell"), "une commande `bash -c` ouvre un shell")
        XCTAssertEqual(console.droitsRisques, ["shell"])

        // Un serveur dont le nom contient « repl » comme fragment (replicate) n'est pas un REPL.
        XCTAssertEqual(serveur("replicate-images")?.droitsRisques, [], "pas de faux positif sur « repl »")

        // Codex est lui-même un agent en terminal.
        XCTAssertTrue(r.serveurs.contains { $0.nom == "Codex" && $0.agentTerminal })
    }

    func testLeJetonNeSortNullePart() throws {
        try configurationPiegee()
        let r = InventaireAgents.analyser(racine: racine)
        let charge = InventaireAgents.charge(r, poste: "poste-mac-test", source: "demo",
                                             horodatage: "2026-10-10T21:00:00.000+02:00")
        let json = String(decoding: try JSONSerialization.data(withJSONObject: charge), as: UTF8.self)
        let encode = String(decoding: try JSONEncoder().encode(r.serveurs), as: UTF8.self)
        let decrit = String(describing: r) + String(reflecting: r.serveurs)
        for sortie in [json, encode, decrit] {
            for secret in [jeton, cleAPI, motDePasse, String(jeton.dropFirst(4).prefix(12))] {
                XCTAssertFalse(sortie.contains(secret), "un secret apparaît dans : \(sortie.prefix(80))…")
            }
            XCTAssertFalse(sortie.contains("Authorization"))
            XCTAssertFalse(sortie.contains("GITHUB_PERSONAL_ACCESS_TOKEN"))
            XCTAssertFalse(sortie.contains("/Users/camille"), "les chemins ne sortent pas")
            XCTAssertFalse(sortie.contains("imap.orbispay.example"), "les arguments ne sortent pas")
        }
        // Le corps envoyé ne porte que les champs du contrat.
        XCTAssertEqual(Set(charge.keys), ["poste", "contexte", "source_config", "horodatage", "clients", "agents"])
        let agents = try XCTUnwrap(charge["agents"] as? [[String: Any]])
        for a in agents {
            XCTAssertEqual(Set(a.keys), ["client", "client_id", "serveur", "types", "droits_risques", "transport"])
        }
    }

    func testFichierAbsentOuIllisible() throws {
        XCTAssertEqual(InventaireAgents.analyser(racine: racine).serveurs, [])
        try ecrire(".cursor/mcp.json", "{ pas du json")
        let r = InventaireAgents.analyser(racine: racine)
        XCTAssertEqual(r.fichiersIllisibles, 1)
        XCTAssertEqual(r.clients, ["Cursor"])
    }

    func testProjetsDeClaudeCodeEtServeurDistantDeZed() throws {
        try ecrire(".claude.json", """
        {"projects": {"/Users/camille/orbis": {"mcpServers": {"gmail": {"command": "npx", "args": ["mcp-gmail"]}}}},
         "mcpServers": {"execution": {"command": "/usr/local/bin/mcp-shell"}}}
        """)
        try ecrire(".config/zed/settings.json", """
        { "context_servers": { "pages": { "command": { "path": "npx", "args": ["-y", "mcp-fetch"] } } } }
        """)
        let r = InventaireAgents.analyser(racine: racine)
        XCTAssertEqual(r.serveurs.first { $0.nom == "gmail" }?.droitsRisques, ["mail"])
        XCTAssertEqual(r.serveurs.first { $0.nom == "execution" }?.droitsRisques, ["shell"])
        XCTAssertEqual(r.serveurs.first { $0.nom == "pages" }?.types, ["reseau"])
        // Claude Code est un agent en terminal ; Zed, une app, ne l'est pas.
        XCTAssertTrue(r.serveurs.contains { $0.nom == "Claude Code" && $0.agentTerminal })
        XCTAssertFalse(r.serveurs.contains { $0.agentTerminal && $0.client == "Zed" })
    }
}
