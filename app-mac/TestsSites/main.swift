import Foundation

// Banc du moteur Swift des sites louches, compilé à part par `partage/verifier.sh`
// (swiftc, avec SitesRegles.swift). Il passe le corpus partagé, vérifie les
// attentes (aucune alerte sur les légitimes, catégorie et marque des louches) et
// écrit chaque résultat en JSON, une ligne par adresse, pour la comparaison avec
// l'extension.
//
//   essai-sites <regles-sites.json> <corpus-sites.json> <sortie.jsonl>

func journal(_ ligne: String) {
    FileHandle.standardError.write(Data("[essai-sites] \(ligne)\n".utf8))
}

let args = CommandLine.arguments
guard args.count == 4,
      let donneesRegles = FileManager.default.contents(atPath: args[1]),
      let donneesCorpus = FileManager.default.contents(atPath: args[2]),
      let corpus = try? JSONSerialization.jsonObject(with: donneesCorpus) as? [String: Any] else {
    journal("usage : essai-sites <regles-sites.json> <corpus-sites.json> <sortie.jsonl>")
    exit(2)
}
let regles: ReglesSites
do {
    regles = try JSONDecoder().decode(ReglesSites.self, from: donneesRegles)
} catch {
    journal("règles illisibles : \(error)")
    exit(2)
}
let moteur = MoteurSites(regles)

let legitimes = corpus["legitimes"] as? [String] ?? []
let louches = corpus["louches"] as? [[String: Any]] ?? []
let raccourcis = corpus["raccourcis"] as? [String] ?? []
let autres = corpus["comparaison_seule"] as? [String] ?? []

var echecs: [String] = []
var lignes: [String] = []
func noter(_ adresse: String, _ r: AnalyseSite) {
    let objet: [String: Any] = ["adresse": adresse, "resultat": r.dictionnaire]
    if let d = try? JSONSerialization.data(withJSONObject: objet, options: [.sortedKeys]),
       let s = String(data: d, encoding: .utf8) {
        lignes.append(s)
    }
}

var fauxPositifs = 0
for a in legitimes {
    let r = moteur.analyser(a)
    noter(a, r)
    if r.verdict == "louche" || r.verdict == "raccourci" {
        fauxPositifs += 1
        echecs.append("faux positif : \(a) (\(r.raison ?? "?"))")
    }
}
var reperes = 0
for l in louches {
    let a = l["adresse"] as? String ?? ""
    let r = moteur.analyser(a)
    noter(a, r)
    let marque = l["marque"] as? String
    if r.verdict == "louche", r.categorie == (l["categorie"] as? String), r.marque == marque,
       let e = r.explication, !e.contains("{"), moteur.conseil(r) != nil {
        reperes += 1
    } else {
        echecs.append("raté : \(a) → \(r.verdict) \(r.categorie ?? "-") \(r.marque ?? "-")")
    }
}
for a in raccourcis {
    let r = moteur.analyser(a)
    noter(a, r)
    if r.verdict != "raccourci" { echecs.append("raccourci non signalé : \(a)") }
}
for a in autres { noter(a, moteur.analyser(a)) }

// Quelques titres, pour l'alerte de l'app.
let t1 = moteur.titres(moteur.analyser("0rbispay.example"))
if t1.titre != "Ce site imite Orbis Pay." || t1.suite != "Ce n'est pas le vrai site." { echecs.append("titre marque : \(t1)") }
let t2 = moteur.titres(moteur.analyser("203.0.113.5"))
if t2.titre != "Ce site n'a pas l'air sûr." { echecs.append("titre sans marque : \(t2)") }

FileManager.default.createFile(atPath: args[3], contents: Data((lignes.joined(separator: "\n") + "\n").utf8))
print("Swift : \(legitimes.count) légitimes, \(fauxPositifs) faux positif(s) ; \(reperes)/\(louches.count) louches repérés ; \(raccourcis.count) raccourcis ; \(lignes.count) adresses écrites")
for e in echecs { print("ÉCHEC \(e)") }
exit(echecs.isEmpty ? 0 : 1)
