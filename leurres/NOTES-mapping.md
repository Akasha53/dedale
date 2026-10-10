# Cartographie OWASP Agentic / MITRE ATLAS des leurres

À confirmer avant la fiche défense (contrat `CONTRATS.md`, § Leurres et canaris).
Ces correspondances sont **plausibles**, pas vérifiées une par une contre les
référentiels. Les points les plus incertains sont signalés.

## OWASP Agentic (codes `ASI01`–`ASI10` du contrat)

Le contrat impose la notation `ASI01`…`ASI10`. Ce préfixe n'est pas celui des
publications OWASP que je connais (le GenAI Security Project parle plutôt de
menaces `T1`…`T15` dans « Agentic AI – Threats and Mitigations »). J'ai donc
posé une table interne et m'y suis tenu ; **à aligner** sur la liste que l'équipe
retient avant le livrable.

| Code retenu | Intitulé supposé |
|---|---|
| ASI01 | Memory / context poisoning (injection indirecte persistée) |
| ASI02 | Tool misuse (usage détourné d'un outil) |
| ASI03 | Privilege compromise (secrets, identifiants, escalade) |
| ASI04 | Resource overload (saturation, boucles) |
| ASI06 | Intent breaking & goal manipulation |
| ASI07 | Misaligned & deceptive behaviors |

`ASI05`, `ASI08`, `ASI09`, `ASI10` ne sont pas utilisés ici.

## MITRE ATLAS (`AML.Txxxx`)

Techniques employées et niveau de confiance :

| Technique | Usage | Confiance |
|---|---|---|
| `AML.T0051` LLM Prompt Injection | consignes cachées, descriptions d'outils | bonne |
| `AML.T0051.001` Indirect Prompt Injection | leurres de contenu lus sur le site | bonne |
| `AML.T0054` LLM Jailbreak | fausse instruction système de `executer_requete_sql` | moyenne |
| `AML.T0057` LLM Data Leakage | faux secrets, faux exports | moyenne (intitulé exact à vérifier) |
| `AML.T0053` LLM Plugin Compromise | faux manifeste + faux outils MCP | moyenne (existence/libellé à vérifier) |
| `AML.T0024` Exfiltration via ML Inference API | export massif `/api/internal/export-clients` | faible (rapprochement discutable) |

## Par leurre

- **L-0001** consigne cachée accueil → ASI06, ASI01 / T0051.001
- **L-0002** faux jeton de service (doc) → ASI03, ASI07 / T0057
- **L-0003** faux identifiants preprod (login) → ASI03, ASI07 / T0051.001 *(ATLAS incertain)*
- **L-0004** robots.txt carte des zones internes → ASI06 / T0051.001
- **L-0005** security.txt orientant vers l'API interne → ASI06 / T0051.001
- **L-0006** faux manifeste ai-plugin.json → ASI02 / T0053
- **L-0010** route export-clients → ASI02, ASI03 / T0024, T0057
- **L-0011** /admin → ASI03 / T0051.001
- **L-0012** /.git/config → ASI03 / T0057
- **L-0013** /sauvegardes/orbis-prod.sql → ASI03, ASI04 / T0057
- **L-0014** /api/internal/debug → ASI03, ASI07 / T0057
- **L-0020** outil MCP export_clients → ASI02, ASI06 / T0053, T0051
- **L-0021** outil MCP lire_secrets → ASI02, ASI03 / T0057
- **L-0022** outil MCP executer_requete_sql → ASI02, ASI06 / T0054, T0053 *(jailbreak vs plugin compromise à trancher)*
