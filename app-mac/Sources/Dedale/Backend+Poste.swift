import Foundation

extension Backend {
    /// Choix du salarié devant un téléchargement à risque (CONTRATS.md, avenant « app Mac,
    /// poste »). Part à la SOC : le type du fichier, les motifs de la règle, le canal et le
    /// domaine d'origine, l'empreinte SHA-256 et le choix. Jamais le nom ni le contenu.
    ///
    /// L'événement reprend le schéma `avertissement` du pilier humain : « Mettre de côté » vaut
    /// `annuler` (bon réflexe), « Garder » vaut `continuer` (passer outre, l'incident s'ouvre).
    func envoyerTelechargement(_ f: FichierSignale, choix: String, fin: @escaping (Bool) -> Void) {
        var details: [String: Any] = [
            "origine": "app-mac",
            "contexte": "telechargement",
            "categorie": "phishing",
            "choix": choix == "garder" ? "continuer" : "annuler",
            "choix_poste": choix,
            "type_fichier": f.verdict.typeFichier,
            "motifs": f.verdict.motifs.map(\.rawValue),
            "provenance": f.provenance.canal.rawValue,
            "gravite": f.verdict.gravite,
            "message": f.verdict.message,
        ]
        if let d = f.provenance.domaine {
            details["domaine"] = d
            details["cible"] = d
        }
        if let e = f.empreinte { details["sha256"] = e }
        let session = "poste-mac-telechargement-" + (f.empreinte.map { String($0.prefix(12)) } ?? f.id)
        envoyer(type: "avertissement", sessionId: session, details: details) { ok in
            journal(ok ? "téléchargement remonté à la SOC (choix=\(choix), session=\(session))"
                       : "téléchargement non remonté (choix=\(choix))")
            fin(ok)
        }
    }
}
