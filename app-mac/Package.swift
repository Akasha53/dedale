// swift-tools-version:5.9
// Dédale, garde du corps du poste : application de barre de menus (démo).
import PackageDescription

let package = Package(
    name: "Dedale",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "Dedale", path: "Sources/Dedale")
    ]
)
