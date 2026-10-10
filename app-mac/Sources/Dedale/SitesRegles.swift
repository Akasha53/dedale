import Foundation

// Moteur d'analyse des adresses, port en Swift de `extension/comparateur.js`.
//
// Les deux lisent les mêmes règles (`partage/regles-sites.json`) et doivent rendre
// exactement les mêmes résultats : `partage/verifier.sh` les compare sur le corpus
// partagé. Toute modification de l'algorithme se fait des deux côtés.
//
// Le moteur ne voit que l'hôte et ce qui précède « @ ». Jamais le chemin, la
// requête ou le contenu de la page.

/// Règles communes, telles que dans le fichier JSON (noms de clés identiques).
struct ReglesSites: Decodable {
    struct Organisation: Decodable {
        let nom: String
        let domaines: [String]
    }
    struct Marque: Decodable {
        let nom: String
        let mots: [String]
        let domaines: [String]
        let ecart: Int?
    }
    struct Palier: Decodable {
        let une_lettre_des: Int
        let deux_lettres_des: Int
    }
    struct Seuils: Decodable {
        let ecart_organisation: Palier
        let ecart_marques: Palier
        let nom_court: Int
        let sous_chaine_des: Int
        let sous_domaines_seuls: Int
        let sous_domaines_avec_signal: Int
        let appats_multiples: Int
        let tirets_appats_multiples: Int
    }
    struct Textes: Decodable {
        let titre_marque: String
        let suite_marque: String
        let titre_sans_marque: String
        let suite_sans_marque: String
        let ecart_un: String
        let ecart_plusieurs: String
        let raisons: [String: String]
        let conseils: [String: String]
        let alphabets: [String: String]
    }

    let organisation: Organisation
    let marques: [Marque]
    let domaines_surs: [String]
    let appats: [String]
    let extensions_risque: [String]
    let raccourcisseurs: [String]
    let suffixes_doubles: [String]
    let confusables: [String: String]
    let sequences: [[String]]
    let chiffres: [String: String]
    let seuils: Seuils
    let textes: Textes

    /// Cherche le fichier : `DEDALE_REGLES_SITES`, puis la copie rangée dans Dedale.app,
    /// puis `partage/regles-sites.json` en remontant depuis le binaire ou le dossier courant.
    static func charger() -> (ReglesSites, URL)? {
        var candidats: [URL] = []
        if let brut = ProcessInfo.processInfo.environment["DEDALE_REGLES_SITES"], !brut.isEmpty {
            candidats.append(URL(fileURLWithPath: brut))
        }
        if let ressources = Bundle.main.resourceURL {
            candidats.append(ressources.appendingPathComponent("regles-sites.json"))
        }
        for depart in [Bundle.main.executableURL?.deletingLastPathComponent(),
                       URL(fileURLWithPath: FileManager.default.currentDirectoryPath)] {
            var dossier = depart
            for _ in 0..<8 {
                guard let d = dossier else { break }
                candidats.append(d.appendingPathComponent("partage/regles-sites.json"))
                dossier = d.deletingLastPathComponent()
            }
        }
        for url in candidats {
            guard let donnees = try? Data(contentsOf: url) else { continue }
            do {
                return (try JSONDecoder().decode(ReglesSites.self, from: donnees), url)
            } catch {
                journal("règles des sites illisibles (\(url.path)) : \(error)")
            }
        }
        return nil
    }
}

/// Résultat d'une analyse, mêmes champs que côté extension.
struct AnalyseSite: Equatable {
    var verdict = "neutre"            // louche | raccourci | confiance | neutre
    var categorie: String? = nil      // sosie | marque_detournee | arobase | ip_brute | alphabets_melanges | adresse_louche | raccourci
    var raison: String? = nil
    var marque: String? = nil
    var imite: String? = nil
    var domaine = ""
    var affiche = ""
    var explication: String? = nil

    var dictionnaire: [String: Any] {
        func ou(_ v: String?) -> Any { v ?? NSNull() }
        return ["verdict": verdict, "categorie": ou(categorie), "raison": ou(raison), "marque": ou(marque),
                "imite": ou(imite), "domaine": domaine, "affiche": affiche, "explication": ou(explication)]
    }
}

/// Le moteur, préparé une fois pour un jeu de règles.
final class MoteurSites {
    let regles: ReglesSites
    private let confusables: [Unicode.Scalar: String]
    private let chiffres: [Unicode.Scalar: String]
    private let doubles: Set<String>
    private let risque: Set<String>
    private let appats: [(mot: String, sq: String)]
    private let appatParSq: [String: String]
    private static let alphabets = ["latin", "grec", "cyrillique", "armenien"]

    init(_ regles: ReglesSites) {
        self.regles = regles
        func scalaires(_ d: [String: String]) -> [Unicode.Scalar: String] {
            var r: [Unicode.Scalar: String] = [:]
            for (k, v) in d where k.unicodeScalars.count == 1 { r[k.unicodeScalars.first!] = v }
            return r
        }
        let conf = scalaires(regles.confusables)
        let chif = scalaires(regles.chiffres)
        confusables = conf
        chiffres = chif
        doubles = Set(regles.suffixes_doubles)
        risque = Set(regles.extensions_risque)
        let calcules = regles.appats.map {
            (mot: $0, sq: Self.squelette($0, confusables: conf, sequences: regles.sequences, chiffres: chif))
        }
        appats = calcules
        var parSq: [String: String] = [:]
        for a in calcules where parSq[a.sq] == nil { parSq[a.sq] = a.mot }
        appatParSq = parSq
    }

    // MARK: Squelette

    private static func squelette(_ texte: String, confusables: [Unicode.Scalar: String],
                                  sequences: [[String]], chiffres: [Unicode.Scalar: String]) -> String {
        let decompose = texte.decomposedStringWithCompatibilityMapping
        var sansMarques = String.UnicodeScalarView()
        for s in decompose.unicodeScalars where !(0x300...0x36F).contains(s.value) { sansMarques.append(s) }
        var s = String(sansMarques).lowercased()
        s = s.unicodeScalars.map { confusables[$0] ?? String($0) }.joined()
        for paire in sequences where paire.count == 2 {
            s = s.replacingOccurrences(of: paire[0], with: paire[1], options: .literal)
        }
        s = s.unicodeScalars.map { chiffres[$0] ?? String($0) }.joined()
        return String(String.UnicodeScalarView(s.unicodeScalars.filter { $0 != "-" && $0 != "_" }))
    }

    func sq(_ texte: String) -> String {
        Self.squelette(texte, confusables: confusables, sequences: regles.sequences, chiffres: chiffres)
    }

    // MARK: Analyse

    /// Analyse une adresse. `organisation` remplace celle des règles (nom et domaines).
    func analyser(_ adresse: String, organisation: ReglesSites.Organisation? = nil) -> AnalyseSite {
        let org = organisation ?? regles.organisation
        var orgDomaines: [String] = []
        for d in org.domaines {
            let h = Self.decomposer(d).hote
            if h.contains("."), !orgDomaines.contains(h) { orgDomaines.append(h) }
        }
        var orgMots: [String] = []
        for d in orgDomaines {
            let n = decouper(d).nom
            if !n.isEmpty, !orgMots.contains(n) { orgMots.append(n) }
        }
        let orgMarque = Cible(nom: org.nom.isEmpty ? "Orbis Pay" : org.nom, mots: orgMots, domaines: orgDomaines,
                              ecart: nil, strict: true)
        let publiques = regles.marques.map { Cible(nom: $0.nom, mots: $0.mots, domaines: $0.domaines,
                                                   ecart: $0.ecart, strict: false) }

        let (identifiant, hote) = Self.decomposer(adresse)
        let affiche = hote.hasPrefix("[") ? hote
            : hote.split(separator: ".", omittingEmptySubsequences: false).map { Self.libelleUnicode(String($0)) }
                .joined(separator: ".")
        var base = AnalyseSite()
        base.domaine = hote
        base.affiche = affiche
        if hote.isEmpty { return base }

        func louche(_ categorie: String, _ raison: String, _ marque: String?, _ imite: String?,
                    _ valeurs: [String: String]) -> AnalyseSite {
            var r = base
            r.verdict = "louche"
            r.categorie = categorie
            r.raison = raison
            r.marque = marque
            r.imite = imite
            var v: [String: String] = [
                "marque": marque ?? "",
                "de_marque": Self.elider("de", marque ?? ""),
                "que_marque": Self.elider("que", marque ?? ""),
                "hote": affiche,
            ]
            v.merge(valeurs) { _, nouveau in nouveau }
            r.explication = Self.remplir(regles.textes.raisons[raison] ?? raison, v)
            return r
        }

        // 1. Astuce « marque@vrai-hôte ».
        if !identifiant.isEmpty {
            let leurre = String(identifiant.split(separator: ":", omittingEmptySubsequences: false).first ?? "")
            let trouve = marqueDansTexte(leurre, [orgMarque] + publiques)
            if leurre.contains(".") || trouve != nil {
                return louche("arobase", "arobase", trouve?.nom, trouve?.domaines.first, ["leurre": leurre])
            }
        }

        // 2. Adresse IP ou nom sans point.
        if hote.hasPrefix("[") || Self.ipv4(hote) != nil {
            return Self.ipPrivee(hote) ? base : louche("ip_brute", "ip_brute", nil, nil, [:])
        }
        if !hote.contains(".") { return base }

        // 3. Domaines connus.
        if regles.domaines_surs.contains(where: { Self.couvre(hote, $0) }) {
            var r = base
            r.verdict = "confiance"
            return r
        }
        if let vrai = orgDomaines.first(where: { Self.couvre(hote, $0) }) {
            var r = base
            r.verdict = "confiance"
            r.marque = orgMarque.nom
            r.imite = vrai
            return r
        }
        for m in publiques {
            if let d = m.domaines.first(where: { Self.couvre(hote, $0) }) {
                var r = base
                r.verdict = "confiance"
                r.marque = m.nom
                r.imite = d
                return r
            }
        }

        // 4. Raccourcisseurs : signalés, sans alarme.
        if regles.raccourcisseurs.contains(where: { Self.couvre(hote, $0) }) {
            var r = base
            r.verdict = "raccourci"
            r.categorie = "raccourci"
            r.raison = "raccourci"
            r.explication = Self.remplir(regles.textes.raisons["raccourci"] ?? "", ["hote": affiche])
            return r
        }

        // 5. Marques : l'organisation d'abord, puis les marques connues.
        let lu = decouper(hote)
        var ctx = Contexte(affiche: affiche, lu: lu, nomUni: Self.libelleUnicode(lu.nom),
                           proprietaire: "\(lu.nom).\(lu.suffixe)", libelles: lu.sous + [lu.nom], appats: [])
        ctx.appats = appatsDans(ctx.libelles)
        for m in [orgMarque] + publiques {
            if let r = comparer(m, ctx) {
                return louche(r.categorie, r.raison, m.nom, r.imite, r.valeurs)
            }
        }

        // 6. Signaux sans marque.
        if let r = signauxGeneriques(ctx) {
            return louche(r.categorie, r.raison, nil, nil, r.valeurs)
        }
        return base
    }

    /// Titre et sous-titre de l'alerte, communs à l'extension et à l'app.
    func titres(_ r: AnalyseSite) -> (titre: String, suite: String) {
        let t = regles.textes
        if let m = r.marque { return (Self.remplir(t.titre_marque, ["marque": m]), t.suite_marque) }
        return (t.titre_sans_marque, t.suite_sans_marque)
    }

    func conseil(_ r: AnalyseSite) -> String? {
        r.categorie.flatMap { regles.textes.conseils[$0] }
    }

    // MARK: Marques

    private struct Cible {
        let nom: String
        let mots: [String]
        let domaines: [String]
        let ecart: Int?
        let strict: Bool
    }

    private struct Decoupe {
        let nom: String
        let suffixe: String
        let sous: [String]
    }

    private struct Contexte {
        let affiche: String
        let lu: Decoupe
        let nomUni: String
        let proprietaire: String
        let libelles: [String]
        var appats: [String]
    }

    private struct Trouve {
        let categorie: String
        let raison: String
        let imite: String?
        let valeurs: [String: String]
    }

    private func decouper(_ hote: String) -> Decoupe {
        let e = hote.split(separator: ".", omittingEmptySubsequences: false).map(String.init)
        if e.count < 2 { return Decoupe(nom: "", suffixe: e.first ?? "", sous: []) }
        let deux = e.suffix(2).joined(separator: ".")
        if e.count >= 3, doubles.contains(deux) {
            return Decoupe(nom: e[e.count - 3], suffixe: deux, sous: Array(e.prefix(e.count - 3)))
        }
        return Decoupe(nom: e[e.count - 2], suffixe: e[e.count - 1], sous: Array(e.prefix(e.count - 2)))
    }

    private func marqueDansTexte(_ texte: String, _ marques: [Cible]) -> Cible? {
        let libelles = texte.split(separator: ".").map(String.init)
        for m in marques {
            if m.domaines.contains(where: { d in
                texte == d || texte.hasSuffix("." + d) || texte.hasPrefix(d + ".") || Self.inclut(texte, "." + d + ".")
            }) { return m }
            if m.mots.contains(where: { mot in libelles.contains { contient($0, mot) } }) { return m }
        }
        return nil
    }

    private func contient(_ libelle: String, _ mot: String) -> Bool {
        let skm = sq(mot)
        if skm.isEmpty { return false }
        let u = Self.libelleUnicode(libelle)
        if Self.longueur(skm) >= regles.seuils.sous_chaine_des { return Self.inclut(sq(u), skm) }
        return Self.jetons(u).contains { sq($0) == skm }
    }

    private func appatsDans(_ libelles: [String]) -> [String] {
        var vus: [String] = []
        for l in libelles {
            for jeton in Self.jetons(Self.libelleUnicode(l)) {
                if let mot = appatParSq[sq(jeton)], !vus.contains(mot) { vus.append(mot) }
            }
        }
        return vus
    }

    private func appatColle(_ libelles: [String], _ mot: String) -> String? {
        let skm = sq(mot)
        if Self.longueur(skm) < regles.seuils.sous_chaine_des { return nil }
        for l in libelles {
            let s = sq(Self.libelleUnicode(l))
            if !Self.inclut(s, skm) { continue }
            let reste = s.replacingOccurrences(of: skm, with: " ", options: .literal)
            if let a = appats.first(where: { Self.longueur($0.sq) >= 4 && Self.inclut(reste, $0.sq) }) { return a.mot }
        }
        return nil
    }

    private func seuil(_ mot: String, _ palier: ReglesSites.Palier) -> Int {
        let n = Self.longueur(mot)
        if n < palier.une_lettre_des { return 0 }
        return n < palier.deux_lettres_des ? 1 : 2
    }

    private func comparer(_ m: Cible, _ ctx: Contexte) -> Trouve? {
        let lu = ctx.lu
        let palier = m.strict ? regles.seuils.ecart_organisation : regles.seuils.ecart_marques
        func domainePour(_ mot: String) -> String? {
            m.domaines.first { decouper($0).nom == mot } ?? m.domaines.first
        }

        for mot in m.mots {
            let skm = sq(mot)
            let court = Self.longueur(mot) < regles.seuils.nom_court
            let vrai = domainePour(mot)
            // a. Même nom, autre extension.
            if lu.nom == mot, m.strict || !court {
                return Trouve(categorie: "sosie", raison: "autre_extension", imite: vrai, valeurs: [
                    "nom": lu.nom, "suffixe": lu.suffixe, "vrai_suffixe": vrai.map { decouper($0).suffixe } ?? "",
                ])
            }
            // b. Même squelette.
            if lu.nom != mot, sq(ctx.nomUni) == skm {
                let deguise = lu.nom.unicodeScalars.contains { ("0"..."9").contains($0) } || lu.nom.hasPrefix("xn--")
                if m.strict || !court || deguise {
                    if lu.nom.hasPrefix("xn--") {
                        var intrus: [Unicode.Scalar] = []
                        for s in ctx.nomUni.unicodeScalars where s.value > 0x7F && !intrus.contains(s) { intrus.append(s) }
                        let etranger = ctx.nomUni.unicodeScalars.contains { confusables[$0] != nil }
                        return Trouve(categorie: "sosie", raison: etranger ? "punycode_etranger" : "punycode_accents",
                                      imite: vrai, valeurs: ["mot": mot, "intrus": intrus.map { String($0) }.joined(separator: " ")])
                    }
                    let sansTiret = { (x: String) in x.replacingOccurrences(of: "-", with: "").replacingOccurrences(of: "_", with: "") }
                    if sansTiret(lu.nom) == sansTiret(mot) {
                        let raison = Self.longueur(lu.nom) > Self.longueur(mot) ? "tiret_ajoute" : "tiret_retire"
                        return Trouve(categorie: "sosie", raison: raison, imite: vrai, valeurs: ["nom": lu.nom, "mot": mot])
                    }
                    return Trouve(categorie: "sosie", raison: "confusables", imite: vrai, valeurs: ["nom": lu.nom, "mot": mot])
                }
            }
            // c. Une ou deux lettres d'écart.
            let max = m.ecart ?? seuil(mot, palier)
            let ecart = Self.distance(sq(ctx.nomUni), skm)
            if ecart > 0, ecart <= max {
                let n = Self.distance(ctx.nomUni, mot)
                let texte = n == 1 ? regles.textes.ecart_un : Self.remplir(regles.textes.ecart_plusieurs, ["n": String(n)])
                return Trouve(categorie: "sosie", raison: "distance", imite: vrai,
                              valeurs: ["nom": ctx.nomUni, "mot": mot, "ecart": texte])
            }
        }

        // d. Un vrai domaine de la marque placé en sous-domaine.
        let sous = lu.sous.joined(separator: ".")
        for d in m.domaines where d.contains(".") {
            if sous == d || sous.hasSuffix("." + d) || sous.hasPrefix(d + ".") || Self.inclut(sous, "." + d + ".") {
                return Trouve(categorie: "marque_detournee", raison: "marque_sous_domaine", imite: d,
                              valeurs: ["leurre": d, "proprietaire": ctx.proprietaire])
            }
        }

        if m.strict {
            // e. Organisation : son nom n'a rien à faire dans un autre domaine.
            var morceaux: [String] = []
            for l in ctx.affiche.split(separator: ".", omittingEmptySubsequences: false).map(String.init) {
                morceaux.append(l)
                morceaux.append(contentsOf: Self.jetons(l))
            }
            morceaux = morceaux.filter { !$0.isEmpty }
            for mot in m.mots where Self.longueur(mot) >= 4 {
                let skm = sq(mot)
                let dedans = morceaux.contains { Self.inclut($0, mot) || Self.inclut(sq($0), skm) }
                    || (Self.longueur(mot) >= 6 && Self.inclut(sq(ctx.affiche.replacingOccurrences(of: ".", with: "")), skm))
                if dedans {
                    return Trouve(categorie: "marque_detournee", raison: "nom_noye", imite: domainePour(mot),
                                  valeurs: ["mot": mot, "proprietaire": ctx.proprietaire])
                }
            }
            // f. Un mot proche du nom, accolé à un autre.
            for mot in m.mots where Self.longueur(mot) >= 4 {
                let skm = sq(mot)
                let max = m.ecart ?? seuil(mot, palier)
                if let proche = morceaux.first(where: { let e = Self.distance(sq($0), skm); return e > 0 && e <= max }) {
                    return Trouve(categorie: "sosie", raison: "nom_proche", imite: domainePour(mot),
                                  valeurs: ["proche": proche, "mot": mot, "proprietaire": ctx.proprietaire])
                }
            }
            return nil
        }

        // e. Marque connue accolée à un mot d'appât, ou posée sur une extension à risque.
        for mot in m.mots {
            if !ctx.libelles.contains(where: { contient($0, mot) }) { continue }
            if let appat = ctx.appats.first ?? appatColle(ctx.libelles, mot) {
                return Trouve(categorie: "marque_detournee", raison: "marque_appat", imite: domainePour(mot),
                              valeurs: ["mot": mot, "appat": appat, "proprietaire": ctx.proprietaire])
            }
            if risque.contains(lu.suffixe) {
                return Trouve(categorie: "marque_detournee", raison: "marque_extension", imite: domainePour(mot),
                              valeurs: ["mot": mot, "suffixe": lu.suffixe])
            }
        }
        // f. Un mot proche de la marque, accompagné d'un mot d'appât.
        if !ctx.appats.isEmpty {
            let jetons = ctx.libelles.flatMap { Self.jetons(Self.libelleUnicode($0)) }.filter { !$0.isEmpty }
            for mot in m.mots {
                let max = m.ecart ?? seuil(mot, palier)
                let skm = sq(mot)
                if let proche = jetons.first(where: { let e = Self.distance(sq($0), skm); return e > 0 && e <= max }) {
                    return Trouve(categorie: "sosie", raison: "nom_proche", imite: domainePour(mot),
                                  valeurs: ["proche": proche, "mot": mot, "proprietaire": ctx.proprietaire])
                }
            }
        }
        return nil
    }

    private func signauxGeneriques(_ ctx: Contexte) -> Trouve? {
        let s = regles.seuils
        for l in ctx.affiche.split(separator: ".", omittingEmptySubsequences: false) {
            var vus = Set<String>()
            for c in l.unicodeScalars { if let a = Self.alphabet(c.value) { vus.insert(a) } }
            if vus.count >= 2 {
                let noms = Self.alphabets.filter { vus.contains($0) }
                    .map { regles.textes.alphabets[$0] ?? $0 }.joined(separator: ", ")
                return Trouve(categorie: "alphabets_melanges", raison: "alphabets_melanges", imite: nil,
                              valeurs: ["nom": String(l), "alphabets": noms])
            }
        }
        let risqueExt = risque.contains(ctx.lu.suffixe)
        let n = ctx.lu.sous.count
        if n >= s.sous_domaines_seuls || (n >= s.sous_domaines_avec_signal && (risqueExt || !ctx.appats.isEmpty)) {
            return Trouve(categorie: "adresse_louche", raison: "sous_domaines", imite: nil,
                          valeurs: ["n": String(n), "proprietaire": ctx.proprietaire])
        }
        if risqueExt, !ctx.appats.isEmpty {
            return Trouve(categorie: "adresse_louche", raison: "appat_extension", imite: nil,
                          valeurs: ["appats": ctx.appats.joined(separator: ", "), "suffixe": ctx.lu.suffixe])
        }
        let appatsNom = appatsDans([ctx.lu.nom])
        let tirets = ctx.lu.nom.filter { $0 == "-" }.count
        if appatsNom.count >= s.appats_multiples, tirets >= s.tirets_appats_multiples {
            return Trouve(categorie: "adresse_louche", raison: "appats_multiples", imite: nil,
                          valeurs: ["nom": Self.libelleUnicode(ctx.lu.nom), "appats": appatsNom.joined(separator: ", ")])
        }
        return nil
    }

    // MARK: Lecture de l'adresse

    /// Sépare une adresse en identifiant (avant « @ ») et hôte : minuscules, sans port ni
    /// point final, en ASCII (punycode pour un nom Unicode). "" si l'hôte est illisible.
    static func decomposer(_ entree: String) -> (identifiant: String, hote: String) {
        var s = entree.trimmingCharacters(in: .whitespacesAndNewlines)
        if let r = s.range(of: "://") {
            let schema = s[..<r.lowerBound]
            if let premier = schema.unicodeScalars.first, premier.isASCII, CharacterSet.letters.contains(premier),
               schema.unicodeScalars.allSatisfy({ $0.isASCII && (CharacterSet.alphanumerics.contains($0) || "+.-".unicodeScalars.contains($0)) }) {
                s = String(s[r.upperBound...])
            }
        }
        let finIndex = s.firstIndex { "/?#\\".contains($0) }
        let autorite = finIndex.map { String(s[..<$0]) } ?? s
        var identifiant = ""
        var hote = autorite
        if let a = autorite.range(of: "@", options: .backwards) {
            identifiant = String(autorite[..<a.lowerBound])
            hote = String(autorite[a.upperBound...])
        }
        identifiant = identifiant.lowercased()
        if hote.hasPrefix("[") {
            guard let ferme = hote.firstIndex(of: "]") else { return (identifiant, "") }
            let ip = String(hote[...ferme]).lowercased()
            let interieur = ip.dropFirst().dropLast()
            let ok = !interieur.isEmpty && interieur.unicodeScalars.allSatisfy { "0123456789abcdef:.".unicodeScalars.contains($0) }
            return (identifiant, ok ? ip : "")
        }
        if let dp = hote.firstIndex(of: ":") { hote = String(hote[..<dp]) }
        hote = hote.precomposedStringWithCanonicalMapping.lowercased()
        while hote.hasSuffix(".") { hote.removeLast() }
        if hote.isEmpty || hote.hasPrefix(".") { return (identifiant, "") }
        hote = hote.split(separator: ".", omittingEmptySubsequences: false).map { l -> String in
            let libelle = String(l)
            if libelle.unicodeScalars.allSatisfy({ $0.isASCII }) { return libelle }
            return "xn--" + encoderPunycode(libelle)
        }.joined(separator: ".")
        let admis = "abcdefghijklmnopqrstuvwxyz0123456789.-_".unicodeScalars
        if !hote.unicodeScalars.allSatisfy({ admis.contains($0) }) || hote.contains("..") { hote = "" }
        return (identifiant, hote)
    }

    private static func ipv4(_ hote: String) -> [Int]? {
        let parties = hote.split(separator: ".", omittingEmptySubsequences: false)
        guard parties.count == 4 else { return nil }
        var octets: [Int] = []
        for p in parties {
            guard (1...3).contains(p.count), p.unicodeScalars.allSatisfy({ ("0"..."9").contains($0) }),
                  let v = Int(p), v <= 255 else { return nil }
            octets.append(v)
        }
        return octets
    }

    private static func ipPrivee(_ hote: String) -> Bool {
        if hote.hasPrefix("[") {
            let h = String(hote.dropFirst().dropLast())
            return h == "::1" || h == "::" || h.hasPrefix("fc") || h.hasPrefix("fd")
                || ["fe8", "fe9", "fea", "feb"].contains { h.hasPrefix($0) }
        }
        guard let o = ipv4(hote) else { return false }
        let (a, b) = (o[0], o[1])
        return a == 10 || a == 127 || a == 0 || (a == 169 && b == 254) || (a == 172 && (16...31).contains(b))
            || (a == 192 && b == 168) || (a == 100 && (64...127).contains(b))
    }

    private static func couvre(_ hote: String, _ domaine: String) -> Bool {
        hote == domaine || hote.hasSuffix("." + domaine)
    }

    // MARK: Outils

    private static func inclut(_ texte: String, _ morceau: String) -> Bool {
        morceau.isEmpty || texte.range(of: morceau, options: .literal) != nil
    }

    private static func longueur(_ texte: String) -> Int { texte.unicodeScalars.count }

    /// Découpe un libellé sur « - » et « _ », en gardant les morceaux vides (comme `split` en JS).
    private static func jetons(_ libelle: String) -> [String] {
        libelle.split(omittingEmptySubsequences: false) { $0 == "-" || $0 == "_" }.map(String.init)
    }

    static func distance(_ a: String, _ b: String) -> Int {
        let A = Array(a.unicodeScalars), B = Array(b.unicodeScalars)
        if A.isEmpty { return B.count }
        if B.isEmpty { return A.count }
        var d = Array(repeating: Array(repeating: 0, count: B.count + 1), count: A.count + 1)
        for i in 0...A.count { d[i][0] = i }
        for j in 0...B.count { d[0][j] = j }
        for i in 1...A.count {
            for j in 1...B.count {
                let cout = A[i - 1] == B[j - 1] ? 0 : 1
                d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cout)
                if i > 1, j > 1, A[i - 1] == B[j - 2], A[i - 2] == B[j - 1] {
                    d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
                }
            }
        }
        return d[A.count][B.count]
    }

    private static func alphabet(_ p: UInt32) -> String? {
        if (0x41...0x5A).contains(p) || (0x61...0x7A).contains(p) { return "latin" }
        if (0xC0...0x2AF).contains(p), p != 0xD7, p != 0xF7 { return "latin" }
        if (0x1E00...0x1EFF).contains(p) { return "latin" }
        if (0x370...0x3FF).contains(p) || (0x1F00...0x1FFF).contains(p) { return "grec" }
        if (0x400...0x52F).contains(p) { return "cyrillique" }
        if (0x530...0x58F).contains(p) { return "armenien" }
        return nil
    }

    static func remplir(_ modele: String, _ valeurs: [String: String]) -> String {
        var sortie = ""
        var reste = Substring(modele)
        while let ouvre = reste.firstIndex(of: "{") {
            sortie += reste[..<ouvre]
            let apres = reste[reste.index(after: ouvre)...]
            if let ferme = apres.firstIndex(of: "}") {
                let cle = String(apres[..<ferme])
                let valide = !cle.isEmpty && cle.unicodeScalars.allSatisfy {
                    $0.isASCII && (CharacterSet.alphanumerics.contains($0) || $0 == "_")
                }
                if valide, let v = valeurs[cle] {
                    sortie += v
                    reste = apres[apres.index(after: ferme)...]
                    continue
                }
            }
            sortie += "{"
            reste = apres
        }
        return sortie + reste
    }

    /// « de PayPal », mais « d'Apple » ; « que Google », mais « qu'Orbis Pay ».
    static func elider(_ mot: String, _ nom: String) -> String {
        let voyelles = "aeiouyhàâäéèêëîïôöûü"
        if let premier = nom.first, voyelles.contains(Character(premier.lowercased())) {
            return String(mot.dropLast()) + "'" + nom
        }
        return mot + " " + nom
    }

    // MARK: Punycode (RFC 3492)

    private static let base = 36, tmin = 1, tmax = 26, skew = 38, damp = 700, biais0 = 72, n0 = 128

    private static func adapter(_ d: Int, _ nbPoints: Int, _ premier: Bool) -> Int {
        var delta = premier ? d / damp : d / 2
        delta += delta / nbPoints
        var k = 0
        while delta > ((base - tmin) * tmax) / 2 {
            delta /= base - tmin
            k += base
        }
        return k + ((base - tmin + 1) * delta) / (delta + skew)
    }

    static func libelleUnicode(_ libelle: String) -> String {
        guard libelle.hasPrefix("xn--") else { return libelle }
        return decoderPunycode(String(libelle.dropFirst(4))) ?? libelle
    }

    static func decoderPunycode(_ entree: String) -> String? {
        let c = Array(entree.unicodeScalars)
        var sortie: [UInt32] = []
        let delim = c.lastIndex(of: "-") ?? -1
        if delim > 0 {
            for j in 0..<delim {
                if !c[j].isASCII { return nil }
                sortie.append(c[j].value)
            }
        }
        var n = n0, biais = biais0, i = 0
        var idx = delim > 0 ? delim + 1 : 0
        while idx < c.count {
            let ancienI = i
            var w = 1
            var k = base
            while true {
                if idx >= c.count { return nil }
                let v = c[idx].value
                idx += 1
                let chiffre: Int
                switch v {
                case 48...57: chiffre = Int(v) - 22
                case 65...90: chiffre = Int(v) - 65
                case 97...122: chiffre = Int(v) - 97
                default: return nil
                }
                i += chiffre * w
                let t = k <= biais ? tmin : (k >= biais + tmax ? tmax : k - biais)
                if chiffre < t { break }
                w *= base - t
                k += base
            }
            biais = adapter(i - ancienI, sortie.count + 1, ancienI == 0)
            n += i / (sortie.count + 1)
            i %= sortie.count + 1
            if n > 0x10FFFF { return nil }
            sortie.insert(UInt32(n), at: i)
            i += 1
        }
        var resultat = String.UnicodeScalarView()
        for p in sortie {
            guard let s = Unicode.Scalar(p) else { return nil }
            resultat.append(s)
        }
        return String(resultat)
    }

    static func encoderPunycode(_ texte: String) -> String {
        let points = texte.unicodeScalars.map { Int($0.value) }
        var sortie = String(String.UnicodeScalarView(texte.unicodeScalars.filter { $0.isASCII }))
        let nbBase = sortie.unicodeScalars.count
        var h = nbBase
        if nbBase > 0 { sortie += "-" }
        var n = n0, delta = 0, biais = biais0
        func car(_ d: Int) -> Character { Character(Unicode.Scalar(UInt8(d < 26 ? 97 + d : 22 + d))) }
        while h < points.count {
            let m = points.filter { $0 >= n }.min()!
            delta += (m - n) * (h + 1)
            n = m
            for p in points {
                if p < n { delta += 1 }
                if p == n {
                    var q = delta
                    var k = base
                    while true {
                        let t = k <= biais ? tmin : (k >= biais + tmax ? tmax : k - biais)
                        if q < t { break }
                        sortie.append(car(t + (q - t) % (base - t)))
                        q = (q - t) / (base - t)
                        k += base
                    }
                    sortie.append(car(q))
                    biais = adapter(delta, h + 1, h == nbBase)
                    delta = 0
                    h += 1
                }
            }
            delta += 1
            n += 1
        }
        return sortie
    }
}
