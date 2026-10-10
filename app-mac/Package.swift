// swift-tools-version:5.9
// Dédale, garde du corps du poste : application de barre de menus (démo).
//
// `DedaleNoyau` porte les règles sans interface (téléchargements, inventaire des agents IA,
// filtre des secrets) : elles se testent sans lancer l'app (`swift test`).
import PackageDescription

let package = Package(
    name: "Dedale",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "DedaleNoyau", path: "Sources/DedaleNoyau"),
        .executableTarget(name: "Dedale", dependencies: ["DedaleNoyau"], path: "Sources/Dedale"),
        .testTarget(name: "DedaleNoyauTests", dependencies: ["DedaleNoyau"], path: "Tests/DedaleNoyauTests"),
    ]
)
