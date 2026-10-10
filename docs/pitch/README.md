# Deck sAIfe

Huit slides pour cinq minutes, en thème clair comme la console. Version 3 minutes pour la finale : garder le problème (1), la solution (2), la démo (4), les résultats et limites (5) et le modèle (7) ; chaque slide le rappelle dans ses notes d'oral. Le [PPTX](saife-pitch-8-slides.pptx) se modifie dans Keynote, PowerPoint ou LibreOffice ; le [PDF](saife-pitch-8-slides.pdf) sert à projeter. `generer.js` est la source du deck.

Depuis la racine du dépôt :

```bash
npm --prefix docs/pitch install
npm --prefix docs/pitch run build      # écrit saife-pitch-8-slides.pptx
osascript -e 'tell application "Keynote"
  set d to open POSIX file "'"$PWD"'/docs/pitch/saife-pitch-8-slides.pptx"
  export d to POSIX file "'"$PWD"'/docs/pitch/saife-pitch-8-slides.pdf" as PDF
  close d saving no
end tell'
```

Les chiffres de la slide 5 viennent de [docs/mesures/resultats.md](../mesures/resultats.md) (`python3 docs/mesures/mesurer.py`). La capture de la console est dans `img/`, celle de la pop-up vient de `app-mac/captures/`. La slide 1 cite trois sources vérifiées le 10 octobre 2026, dont les URL sont dans les notes d'oral : le [benchmark 2025 de KnowBe4](https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report) (33,1 % de taux initial aux tests simulés, 4,1 % après un an), EchoLeak (CVE-2025-32711) et l'injection de prompt via le serveur MCP de GitHub (Invariant Labs, 26 mai 2025). Aucun de ces chiffres ne mesure sAIfe. Les scènes utilisent l'entreprise fictive Orbis Pay. Le déroulé de la démo est dans [docs/DEMO_JURY.md](../DEMO_JURY.md).
