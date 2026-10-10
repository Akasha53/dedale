# Deck Dédale

Le pitch compte huit slides pour cinq minutes. Version 3 minutes pour la finale : garder le problème (1), la solution (2), la démo (4), les résultats et limites (5) et le modèle (7) ; chaque slide le rappelle dans ses notes. Le [PPTX](dedale-pitch-8-slides.pptx) se modifie dans PowerPoint ou LibreOffice ; le [PDF](dedale-pitch-8-slides.pdf) sert à projeter la version relue. Le fichier `generer.js` est la source du deck. Il reprend les visuels du dépôt et contient des notes pour l'oral.

Depuis la racine du dépôt, pour le régénérer :

```bash
npm --prefix docs/pitch install
npm --prefix docs/pitch run build
soffice --headless --convert-to pdf --outdir docs/pitch docs/pitch/dedale-pitch-8-slides.pptx  # ou export PDF depuis Keynote
```

Le deck suit le [plan Nila](../PLAN_NILA_2026-10-10.md) et le [parcours de démonstration](../DEMO.md). Les captures proviennent du prototype local du 10 octobre 2026. La slide 1 cite trois sources vérifiées le 10 octobre 2026, dont les URL sont dans les notes d'oral : le [benchmark 2025 de KnowBe4](https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report) (33,1 % de taux initial aux tests simulés, 4,1 % après un an), EchoLeak (CVE-2025-32711) et l'injection de prompt via le serveur MCP de GitHub (Invariant Labs, 26 mai 2025). Aucun de ces chiffres ne mesure Dédale. Les scènes Dédale utilisent l'entreprise fictive Orbis Pay ; le deck distingue le prototype des intégrations visées.
