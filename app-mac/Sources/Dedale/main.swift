import AppKit

// Dédale, garde du corps du poste (démo). Application de barre de menus, sans icône
// dans le Dock : LSUIElement dans Info.plist, et la politique « accessory » pour le
// binaire lancé hors du paquet .app.
let application = NSApplication.shared
let delegue = AppDelegue()
application.delegate = delegue
application.setActivationPolicy(.accessory)
application.run()
