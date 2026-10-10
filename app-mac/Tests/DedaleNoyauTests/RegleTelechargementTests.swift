import DedaleNoyau
import XCTest

final class RegleTelechargementTests: XCTestCase {
    let regle = RegleTelechargement()
    let site = Provenance(canal: .site, domaine: "factures-orbis.example", application: "Safari")
    let siteConnu = Provenance(canal: .site, domaine: "telechargements.orbispay.example", application: "Safari")
    let mail = Provenance(canal: .mail, domaine: "orbis-pay-facturation.example", application: "Mail")
    let locale = Provenance(canal: .locale)

    private var dossier: URL!

    override func setUpWithError() throws {
        dossier = FileManager.default.temporaryDirectory.appendingPathComponent("dedale-tests-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dossier, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dossier)
    }

    // MARK: Double extension et nom trompeur

    func testDoubleExtensionToujoursSignaleeMemeCreeSurCeMac() {
        let v = regle.analyser(nom: "facture.pdf.app", provenance: locale, structure: StructureFichier(paquet: true))
        XCTAssertTrue(v.alerte)
        XCTAssertEqual(v.motifs.first, .doubleExtension)
        XCTAssertTrue(v.motifs.contains(.application))
        XCTAssertEqual(v.typeFichier, "application")
        XCTAssertEqual(v.gravite, "haute")
    }

    func testDoubleExtensionAvecEspacesAvantLExtension() {
        let v = regle.analyser(nom: "releve.pdf      .command", provenance: site, structure: StructureFichier())
        XCTAssertTrue(v.motifs.contains(.doubleExtension))
        XCTAssertTrue(v.motifs.contains(.script))
    }

    func testNomRetourneParUnCaractereBidi() {
        // « facture‮fdp.app » s'affiche « facture.ppa.pdf ».
        let v = regle.analyser(nom: "facture\u{202E}fdp.app", provenance: site, structure: StructureFichier(paquet: true))
        XCTAssertEqual(v.motifs.first, .nomTrompeur)
        XCTAssertTrue(v.alerte)
    }

    func testDeuxExtensionsDeDocumentNeSontPasUneDoubleExtension() {
        let v = regle.analyser(nom: "rapport.final.pdf", provenance: site, structure: StructureFichier())
        XCTAssertFalse(v.alerte)
        XCTAssertEqual(v.typeFichier, "document")
    }

    // MARK: Programmes selon la provenance

    func testApplicationDUnSiteInconnu() {
        let v = regle.analyser(nom: "Lecteur.app", provenance: site, structure: StructureFichier(paquet: true))
        XCTAssertTrue(v.alerte)
        XCTAssertEqual(v.motifs, [.application])
        XCTAssertEqual(v.message, "Ce fichier vient de factures-orbis.example et peut lancer un programme.")
    }

    func testImageDisqueDUnDomaineConnuPasseSansPopup() {
        let v = regle.analyser(nom: "OrbisSync.dmg", provenance: siteConnu, structure: StructureFichier())
        XCTAssertFalse(v.alerte)
        XCTAssertEqual(v.typeFichier, "image_disque")
    }

    func testImageDisqueDUnSiteInconnu() {
        let v = regle.analyser(nom: "OrbisSync.dmg", provenance: site, structure: StructureFichier())
        XCTAssertEqual(v.motifs, [.imageDisque])
    }

    func testInstalleurIsoEtRaccourciRecusParMail() {
        for (nom, motif) in [("mise-a-jour.pkg", RegleTelechargement.Motif.installeur),
                             ("disque.iso", .imageDisque), ("Portail RH.webloc", .raccourci),
                             ("lien.url", .raccourci), ("outil.sh", .script)] {
            let v = regle.analyser(nom: nom, provenance: mail, structure: StructureFichier())
            XCTAssertTrue(v.alerte, nom)
            XCTAssertEqual(v.motifs, [motif], nom)
            XCTAssertTrue(v.detail.contains("pièce jointe d'un mail"), nom)
        }
    }

    func testProgrammeCreeSurCeMacNeDeclenchePasDePopup() {
        let v = regle.analyser(nom: "script-perso.sh", provenance: locale, structure: StructureFichier(scriptExecutable: true))
        XCTAssertFalse(v.alerte)
    }

    func testBinaireSansExtensionReconnuParSaStructure() {
        let v = regle.analyser(nom: "mise_a_jour", provenance: site, structure: StructureFichier(binaire: true))
        XCTAssertEqual(v.motifs, [.application])
    }

    func testDocumentOrdinaireNeDeclenchePasDePopup() {
        let v = regle.analyser(nom: "devis.pdf", provenance: site, structure: StructureFichier())
        XCTAssertFalse(v.alerte)
    }

    func testMessageSansDomaineSelonLeCanal() {
        let v = regle.analyser(nom: "outil.app", provenance: Provenance(canal: .mail), structure: StructureFichier(paquet: true))
        XCTAssertEqual(v.message, "Ce fichier vient d'un mail et peut lancer un programme.")
        let w = regle.analyser(nom: "outil.app", provenance: Provenance(canal: .inconnue), structure: StructureFichier(paquet: true))
        XCTAssertEqual(w.message, "Ce fichier vient d'une source inconnue et peut lancer un programme.")
    }

    // MARK: Macros et archives chiffrées (lues sur de vrais fichiers)

    func testDocmSigneParSonExtension() {
        let v = regle.analyser(nom: "releve.docm", provenance: mail, structure: StructureFichier())
        XCTAssertEqual(v.motifs, [.macros])
        XCTAssertEqual(v.typeFichier, "document_macros")
        XCTAssertEqual(v.gravite, "moyenne")
    }

    func testDocxQuiCacheUnProjetVBA() throws {
        let url = dossier.appendingPathComponent("rapport.docx")
        try ZipFactice.ecrire([("[Content_Types].xml", false), ("word/document.xml", false),
                               ("word/vbaProject.bin", false)], vers: url)
        let s = StructureFichier.inspecter(url)
        XCTAssertTrue(s.macros)
        XCTAssertFalse(s.archiveChiffree)
        let v = regle.analyser(nom: "rapport.docx", provenance: mail, structure: s)
        XCTAssertEqual(v.motifs, [.macros])
    }

    func testDocxSansMacros() throws {
        let url = dossier.appendingPathComponent("propre.docx")
        try ZipFactice.ecrire([("[Content_Types].xml", false), ("word/document.xml", false)], vers: url)
        XCTAssertFalse(StructureFichier.inspecter(url).macros)
    }

    func testArchiveProtegeeParMotDePasse() throws {
        let url = dossier.appendingPathComponent("photos.zip")
        try ZipFactice.ecrire([("photo1.jpg", true), ("lisez-moi.txt", true)], vers: url)
        let s = StructureFichier.inspecter(url)
        XCTAssertTrue(s.archiveChiffree)
        let v = regle.analyser(nom: "photos.zip", provenance: site, structure: s)
        XCTAssertEqual(v.motifs, [.archiveChiffree])
        XCTAssertEqual(v.typeFichier, "archive_chiffree")
        XCTAssertEqual(v.message, "Ce fichier vient de factures-orbis.example et il est verrouillé par un mot de passe.")
    }

    func testArchiveOrdinaire() throws {
        let url = dossier.appendingPathComponent("ordinaire.zip")
        try ZipFactice.ecrire([("a.txt", false)], vers: url)
        XCTAssertFalse(StructureFichier.inspecter(url).archiveChiffree)
    }

    func testDocumentOLEAvecMacros() throws {
        var donnees = Data([0xD0, 0xCF, 0x11, 0xE0, 0xA1, 0xB1, 0x1A, 0xE1])
        donnees.append(Data(repeating: 0, count: 600))
        donnees.append(Data("_VBA_PROJECT".utf16.flatMap { [UInt8($0 & 0xFF), UInt8($0 >> 8)] }))
        let url = dossier.appendingPathComponent("ancien.doc")
        try donnees.write(to: url)
        XCTAssertTrue(StructureFichier.inspecter(url).macros)
    }

    func testMachOEtScriptExecutable() throws {
        let binaire = dossier.appendingPathComponent("prog")
        try Data([0xCF, 0xFA, 0xED, 0xFE, 0, 0, 0, 0]).write(to: binaire)
        XCTAssertTrue(StructureFichier.inspecter(binaire).binaire)

        let script = dossier.appendingPathComponent("lancer")
        try Data("#!/bin/sh\necho bonjour\n".utf8).write(to: script)
        XCTAssertFalse(StructureFichier.inspecter(script).scriptExecutable, "sans droit d'exécution")
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: script.path)
        XCTAssertTrue(StructureFichier.inspecter(script).scriptExecutable)
    }

    func testPaquetApp() throws {
        let app = dossier.appendingPathComponent("Facture.pdf.app/Contents", isDirectory: true)
        try FileManager.default.createDirectory(at: app, withIntermediateDirectories: true)
        XCTAssertTrue(StructureFichier.inspecter(dossier.appendingPathComponent("Facture.pdf.app")).paquet)
    }

    // MARK: Empreinte

    func testEmpreinteSHA256() throws {
        let url = dossier.appendingPathComponent("abc.txt")
        try Data("abc".utf8).write(to: url)
        XCTAssertEqual(StructureFichier.empreinte(url),
                       "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    }

    func testEmpreinteDUnPaquetStableEtSensibleAuContenu() throws {
        let app = dossier.appendingPathComponent("X.app")
        try FileManager.default.createDirectory(at: app.appendingPathComponent("Contents"), withIntermediateDirectories: true)
        try Data("un".utf8).write(to: app.appendingPathComponent("Contents/Info.plist"))
        let e1 = StructureFichier.empreinte(app)
        XCTAssertEqual(e1, StructureFichier.empreinte(app))
        try Data("deux".utf8).write(to: app.appendingPathComponent("Contents/Info.plist"))
        XCTAssertNotEqual(e1, StructureFichier.empreinte(app))
        XCTAssertEqual(e1?.count, 64)
    }

    // MARK: Provenance

    func testQuarantaineSafariGardeLeDomaineSeul() {
        let p = Provenance.lire(
            quarantaine: "0083;66f5d2a1;Safari;8F3B2C1A-0000-4000-8000-000000000001",
            ouVient: ["https://cdn.factures-orbis.example/dl/facture.pdf.app?jeton=abc123&u=camille",
                      "https://www.factures-orbis.example/espace-client"])
        XCTAssertEqual(p.canal, .site)
        XCTAssertEqual(p.domaine, "cdn.factures-orbis.example")
        XCTAssertEqual(p.application, "Safari")
    }

    func testQuarantaineMailGardeLeDomaineDeLExpediteur() {
        let p = Provenance.lire(quarantaine: "0081;66f5d2a1;Mail;",
                                ouVient: ["Service facturation <facturation@orbis-pay-facturation.example>",
                                          "Votre facture d'octobre", "message:%3C1234@orbis-pay-facturation.example%3E"])
        XCTAssertEqual(p.canal, .mail)
        XCTAssertEqual(p.domaine, "orbis-pay-facturation.example")
    }

    func testSansQuarantaineLeFichierEstLocal() {
        let p = Provenance.lire(quarantaine: nil, ouVient: ["https://factures-orbis.example/x"])
        XCTAssertEqual(p.canal, .locale)
        XCTAssertNil(p.domaine)
    }

    func testQuarantaineSansOrigine() {
        XCTAssertEqual(Provenance.lire(quarantaine: "0081;66f5d2a1;;", ouVient: []).canal, .inconnue)
        XCTAssertEqual(Provenance.lire(quarantaine: "0081;66f5d2a1;sharingd;", ouVient: []).canal, .airdrop)
    }

    func testDomaineConnuEtSousDomaines() {
        XCTAssertTrue(Provenance.estConnu("orbispay.example", parmi: ["orbispay.example"]))
        XCTAssertTrue(Provenance.estConnu("dl.orbispay.example", parmi: ["orbispay.example"]))
        XCTAssertFalse(Provenance.estConnu("orbispay.example.factures.example", parmi: ["orbispay.example"]))
        XCTAssertFalse(Provenance.estConnu("faux-orbispay.example", parmi: ["orbispay.example"]))
    }
}

/// Écrit une petite archive ZIP (entrées stockées, sans compression) dont chaque entrée peut
/// porter le drapeau « chiffrée ». Assez pour tester la lecture de l'annuaire.
enum ZipFactice {
    static func ecrire(_ entrees: [(String, Bool)], vers url: URL) throws {
        var corps = Data()
        var annuaire = Data()
        for (nom, chiffree) in entrees {
            let nomOctets = Data(nom.utf8)
            let contenu = Data("contenu inoffensif".utf8)
            let decalage = UInt32(corps.count)
            let drapeaux: UInt16 = chiffree ? 1 : 0
            corps.append(u32(0x04034b50)); corps.append(u16(20)); corps.append(u16(drapeaux)); corps.append(u16(0))
            corps.append(u16(0)); corps.append(u16(0)); corps.append(u32(0))
            corps.append(u32(UInt32(contenu.count))); corps.append(u32(UInt32(contenu.count)))
            corps.append(u16(UInt16(nomOctets.count))); corps.append(u16(0))
            corps.append(nomOctets); corps.append(contenu)

            annuaire.append(u32(0x02014b50)); annuaire.append(u16(20)); annuaire.append(u16(20))
            annuaire.append(u16(drapeaux)); annuaire.append(u16(0)); annuaire.append(u16(0)); annuaire.append(u16(0))
            annuaire.append(u32(0)); annuaire.append(u32(UInt32(contenu.count))); annuaire.append(u32(UInt32(contenu.count)))
            annuaire.append(u16(UInt16(nomOctets.count))); annuaire.append(u16(0)); annuaire.append(u16(0))
            annuaire.append(u16(0)); annuaire.append(u16(0)); annuaire.append(u32(0)); annuaire.append(u32(decalage))
            annuaire.append(nomOctets)
        }
        var fin = Data()
        fin.append(u32(0x06054b50)); fin.append(u16(0)); fin.append(u16(0))
        fin.append(u16(UInt16(entrees.count))); fin.append(u16(UInt16(entrees.count)))
        fin.append(u32(UInt32(annuaire.count))); fin.append(u32(UInt32(corps.count))); fin.append(u16(0))
        try (corps + annuaire + fin).write(to: url)
    }

    private static func u16(_ v: UInt16) -> Data { Data([UInt8(v & 0xFF), UInt8(v >> 8)]) }
    private static func u32(_ v: UInt32) -> Data {
        Data([UInt8(v & 0xFF), UInt8((v >> 8) & 0xFF), UInt8((v >> 16) & 0xFF), UInt8(v >> 24)])
    }
}
