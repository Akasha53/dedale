// Génère le deck modifiable de sAIfe avec pptxgenjs (npm install pptxgenjs).
// Thème clair, celui de la console et de la landing. Les captures viennent du prototype.
// Les chiffres de la slide 5 viennent de docs/mesures/resultats.md (python3 docs/mesures/mesurer.py).
const path = require('path');
const pptxgen = require('pptxgenjs');

const racine = path.resolve(__dirname, '../..');
const sortie = path.join(__dirname, 'saife-pitch-8-slides.pptx');
const image = (chemin) => path.join(racine, chemin);
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Équipe sAIfe';
pptx.subject = 'Démonstration du prototype sAIfe, Secure Horizons 2026';
pptx.title = 'sAIfe : salariés et agents IA, une même console SOC';
pptx.company = 'sAIfe';
pptx.lang = 'fr-FR';
pptx.theme = {
  headFontFace: 'Arial',
  bodyFontFace: 'Arial',
  lang: 'fr-FR',
};

// Mesures du 11 octobre (9 h 35), reprises de docs/mesures/resultats.md.
const M = {
  quand: '11 octobre 2026 à 9 h 35',
  commit: 'fb6fa41',
  agents: 'Agent piégé : 25/25 sessions arrêtées, 0 rapport sorti ; repéré en 12 ms, coupé en 32 ms (médianes)',
  detection: 'médiane 12 ms, moyenne 17 ms, 25 sessions',
  confinement: 'médiane 32 ms, moyenne 31 ms, 25 sessions',
  fauxPositifs: '0 faux positif sur 50 sessions humaines ou scriptées',
  mails: 'Mails de démo : 8/8 frauduleux repérés, 0/3 légitime signalé, 2/2 consignes cachées retirées',
  desarmeur: 'consigne cachée retirée dans 2/2 mails qui en portent une, 0/10 ailleurs',
  relecteur: 'Relecteur IA : 6 gestes critiques, 4 refusés par les règles dures, 2 relus par Claude Haiku (4,0 et 4,8 s)',
  tests: '926 tests réussis le 11 octobre 2026 à 8 h 55 (commit cb8b6bc), hors tests Swift de l’app Mac',
};

const W = 13.333;
const H = 7.5;
const S = pptx.ShapeType;
// Palette de la landing (landing/index.html, :root).
const C = {
  fond: 'FFFFFF', panneau: 'F4F4F4', carte: 'F9F9F9', trait: 'E5E5E5',
  encre: '0D0D0D', doux: '5D5D5D', faible: '6B6B6B',
  accent: '0E7490', accentPale: 'ECF8FB', ardoise: '334155',
  rouge: 'B42318', vert: '15803D',
};
const sansMarge = 0;

function fond(slide) {
  slide.background = { color: C.fond };
  slide.addShape(S.rect, { x:0, y:0, w:W, h:0.06, line:{color:C.accent, transparency:100}, fill:{color:C.accent} });
}
function texte(slide, contenu, x, y, w, h, options={}) {
  slide.addText(contenu, {
    x, y, w, h, margin:sansMarge, breakLine:false, valign:'mid',
    color:C.encre, fontFace:'Arial', fontSize:18,
    ...options,
  });
}
// Logotype : « sAIfe », jamais en capitales, « AI » en gras dans la même couleur.
// Une option de run à false hérite de la boîte (pptxgenjs) : la boîte qui porte
// le logotype ne met donc pas bold, chaque run le précise.
function marque(suite, grasSuite=false) {
  return [
    {text:'s'}, {text:'AI', options:{bold:true}}, {text:'fe'},
    {text:suite, options:grasSuite ? {bold:true} : {}},
  ];
}
function titre(slide, numero, rubrique, libelle, sousTitre) {
  fond(slide);
  // Une rubrique en runs (logotype) n'est pas passée en capitales.
  const enRuns = Array.isArray(rubrique);
  texte(slide, enRuns ? rubrique : rubrique.toUpperCase(), 0.65, 0.37, 8, 0.31,
        {fontSize:11, color:C.accent, bold:!enRuns, charSpacing:1.2});
  texte(slide, libelle, 0.65, 0.83, 12.05, 0.66,
        {fontSize:30, bold:true, fit:'shrink'});
  if (sousTitre) texte(slide, sousTitre, 0.67, 1.49, 11.95, 0.48,
                       {fontSize:15, color:C.doux, fit:'shrink'});
  pied(slide, numero);
}
function pied(slide, numero) {
  slide.addShape(S.line, {x:0.65,y:7.11,w:12.05,h:0,line:{color:C.trait,width:0.8}});
  texte(slide, marque('  /  SECURE HORIZONS 2026  /  PROTOTYPE LOCAL'),
        0.65, 7.17, 10.6, 0.19,
        {fontFace:'Courier New',fontSize:8.2,color:C.faible,charSpacing:0.5});
  texte(slide, `${String(numero).padStart(2,'0')} / 08`, 11.6, 7.16, 1.1, 0.2,
        {fontFace:'Courier New',fontSize:8.4,color:C.faible,align:'right'});
}
function bloc(slide,x,y,w,h,options={}) {
  slide.addShape(S.roundRect, {x,y,w,h,rectRadius:0.12,
    line:{color:options.bord||C.trait,width:options.largeur||0.9},
    fill:{color:options.fond||C.carte}, radius:0.12});
}
function etiquette(slide,libelle,x,y,w,couleur=C.accent) {
  slide.addShape(S.roundRect,{x,y,w,h:0.33,rectRadius:0.12,
    line:{color:couleur,width:0.7},fill:{color:C.fond}});
  texte(slide,libelle,x+0.08,y+0.055,w-0.16,0.21,
        {fontFace:'Courier New',fontSize:9.5,color:couleur,bold:true,align:'center'});
}
function ligne(slide,x1,y1,x2,y2,couleur=C.trait,largeur=1.5) {
  slide.addShape(S.line,{x:x1,y:y1,w:x2-x1,h:y2-y1,line:{color:couleur,width:largeur}});
}
function capture(slide,chemin,x,y,w,h,legende) {
  bloc(slide,x-0.08,y-0.08,w+0.16,h+0.16,{fond:C.panneau,bord:C.trait});
  slide.addImage({path:image(chemin),x,y,w,h});
  if (legende) texte(slide,legende,x,y+h+0.12,w,0.28,
                     {fontSize:9.2,color:C.faible,fontFace:'Courier New'});
}

const URL_KB = 'https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report';
const URL_ECHO = 'https://thehackernews.com/2025/06/zero-click-ai-vulnerability-exposes.html';
const URL_MCP = 'https://invariantlabs.ai/blog/mcp-github-vulnerability';

// 1. Problème
{
  const slide = pptx.addSlide();
  titre(slide,1,marque('  /  LE PROBLÈME', true),'Un contenu piégé vise deux lecteurs : le salarié et l’agent',
        'Trois cas documentés, aucun ne vient de sAIfe.');
  const cartes = [
    {tag:'SALARIÉ', c:C.accent, gros:'33 %', txt:'des salariés non formés échouent aux tests de phishing simulés. Après un an de formation : 4 %.',
     src:'KnowBe4, rapport 2025', url:URL_KB},
    {tag:'AGENT', c:C.ardoise, gros:'EchoLeak', txt:'CVE-2025-32711. Un mail piégé fait fuiter des données par Microsoft 365 Copilot, sans aucune action humaine.',
     src:'Aim Security, juin 2025', url:URL_ECHO},
    {tag:'AGENT', c:C.ardoise, gros:'Serveur MCP', txt:'Une issue GitHub piégée pousse l’agent à copier des dépôts privés dans une pull request publique (mai 2025).',
     src:'Invariant Labs, 26 mai 2025', url:URL_MCP},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*4.1;
    bloc(slide,x,2.3,3.85,3.75,{bord:o.c});
    etiquette(slide,o.tag,x+0.25,2.55,1.5,o.c);
    texte(slide,o.gros,x+0.25,3.05,3.4,0.8,{fontSize:o.gros.length>6?28:44,bold:true,color:o.c,fit:'shrink'});
    texte(slide,o.txt,x+0.25,3.95,3.35,1.5,{fontSize:15,fit:'shrink',valign:'top'});
    texte(slide,o.src,x+0.25,5.6,3.35,0.3,{fontFace:'Courier New',fontSize:10.5,color:C.doux});
  });
  texte(slide,'Les deux lecteurs ouvrent le même contenu, mais personne ne les surveille dans la même console.',
        0.68,6.4,12.0,0.4,{fontSize:12.5,color:C.faible,fit:'shrink'});
  slide.addNotes(`VERSION 3 MIN : garder cette slide.
Phrase d’ouverture : un contenu piégé vise deux lecteurs, le salarié et l’agent.
1. KnowBe4, Phishing by Industry Benchmarking Report 2025 : taux initial de 33,1 % (Phish-prone Percentage) avant formation, 4,1 % après douze mois, sur 67,7 millions de tests simulés dans 62 400 organisations. C’est un test simulé, pas la part de salariés qui cliquent sur de vrais mails frauduleux. ${URL_KB}
2. EchoLeak, CVE-2025-32711, Microsoft 365 Copilot, découvert par Aim Security, correctif côté serveur en juin 2025, CVSS 9,3, aucun clic requis, aucune exploitation connue dans la nature. ${URL_ECHO}
3. Injection de prompt via le serveur MCP de GitHub : Invariant Labs, 26 mai 2025. Une issue publique piégée amène l’agent à lire des dépôts privés et à les recopier dans une pull request publique. Invariant parle d’un problème d’architecture, pas d’un bogue du serveur. ${URL_MCP}
Sources vérifiées en ligne le 10 octobre 2026.`);
}

// 2. Solution
{
  const slide = pptx.addSlide();
  titre(slide,2,'La solution','Un seul moteur pour le salarié et pour l’agent','sAIfe intervient une seconde avant le geste, en local, et c’est un humain qui tranche.');
  const cartes = [
    {n:'01',t:'Prévenir',d:'Pop-up avant le clic sur le poste. Consigne cachée retirée avant que l’agent la lise.',c:C.accent},
    {n:'02',t:'Retenir',d:'Chaque appel d’outil passe la passerelle : envoi externe, outil inconnu ou détourné attend l’analyste.',c:C.ardoise},
    {n:'03',t:'L’humain tranche',d:'Le salarié choisit. Son responsable confirme un virement retenu. L’analyste coupe un agent, avec un motif.',c:C.accent},
    {n:'04',t:'Prouver',d:'Journal scellé et signé, rapport d’une page, exports ECS, CEF et Sigma vers le SIEM.',c:C.ardoise},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*3.07;
    bloc(slide,x,2.39,2.8,3.0,{bord:o.c});
    texte(slide,o.n,x+0.22,2.65,0.65,0.43,{fontFace:'Courier New',fontSize:16.5,color:o.c,bold:true});
    texte(slide,o.t,x+0.22,3.2,2.5,0.44,{fontSize:20,bold:true,fit:'shrink'});
    ligne(slide,x+0.22,3.8,x+2.58,3.8,C.trait,0.9);
    texte(slide,o.d,x+0.22,4.0,2.36,1.25,{fontSize:15.1,color:C.doux,fit:'shrink',valign:'top'});
  });
  texte(slide,'Ce qu’on ne fait pas : tout bloquer, remplacer votre SIEM, classer vos documents.',
        0.68,5.75,12.0,0.4,{fontSize:16,bold:true,fit:'shrink'});
  texte(slide,'On contrôle l’action de l’agent, pas seulement le texte qu’il lit : une consigne paraphrasée peut passer un filtre, pas la retenue.',
        0.68,6.3,12.0,0.4,{fontSize:12.5,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : garder cette slide.\nUn pare-feu protège les tuyaux ; sAIfe protège ceux qui décident d’ouvrir. Le poste du salarié n’est jamais coupé : il avertit, la personne choisit, sauf un geste critique (virement, export de clients) qui attend un second regard. Un virement normal part sans rien afficher ; un signal sans fraude le retient pour le responsable ou la finance, un signal de fraude prévient la sécurité. Pour l’agent, la passerelle désarme le contenu avant lecture et contrôle chaque appel d’outil avant exécution, outils inconnus et MCP compris. Ce qu’on ne fait pas : tout bloquer, remplacer le SIEM (on lui envoie ECS, CEF par syslog et des règles Sigma validées par sigma-cli), classer les documents de l’entreprise. Le brouillon NIS2 est à relire, ce n’est ni une qualification ni une notification envoyée. Référentiels de lecture, sans certification : NIST CSF 2.0, MITRE ATT&CK et ATLAS, OWASP agentique.');
}

// 3. Volet poste
{
  const slide = pptx.addSlide();
  titre(slide,3,'Volet poste','Protéger le salarié sans le fliquer','Ce que le DPO et le CSE voudront entendre.');
  const lignes = [
    ['01','Une app visible qui prévient avant le geste et laisse le choix. Un virement normal part sans rien afficher.'],
    ['02','Quatre modules qu’on peut couper : mails reçus, onglet actif, téléchargements, agents IA du poste. L’analyse se fait sur le poste.'],
    ['03','Virement retenu sans fraude : le responsable ou la finance le confirme. La sécurité n’en voit que l’issue.'],
    ['04','Au SOC : un pseudonyme et des montants en tranches. Le détail ne s’ouvre que sur un signal de fraude, et chaque consultation est journalisée.'],
  ];
  lignes.forEach((l,i)=>{
    texte(slide,l[0],0.72,2.35+i*0.98,0.6,0.5,{fontFace:'Courier New',fontSize:15,color:i%2?C.ardoise:C.accent,bold:true});
    texte(slide,l[1],1.4,2.2+i*0.98,5.3,0.8,{fontSize:14.5,fit:'shrink'});
  });
  capture(slide,'app-mac/captures/mail.png',7.1,2.12,4.9,3.81,'Pop-up de l’app Mac, prototype local');
  texte(slide,'Prévu avant un déploiement : purge à 90 jours, analyse d’impact, salariés informés et CSE consulté, score de tri réservé aux agents.',
        0.68,6.45,12.0,0.4,{fontSize:14,color:C.doux,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : sauter cette slide, garder une phrase dans la démo : le poste avertit, le salarié décide.\nCe qui est en place, module par module (même texte que la section Vie privée de la landing et le panneau « Ce que sAIfe regarde sur ce poste ») : mails reçus, onglet actif, téléchargements, agents IA installés, chacun avec son interrupteur. Part au SOC : la catégorie, le domaine et le choix du salarié ; l’empreinte d’un fichier ; l’inventaire des agents sans secret. La copie désarmée d’un mail jugé frauduleux part du serveur de messagerie, pas du poste. « Annuler » envoie aussi un événement : la SOC compte un piège évité, sans ouvrir de dossier. Jamais lus : presse-papiers, frappes, écran, contenu des pages, historique. Jamais envoyés : le contenu d’un fichier, la valeur d’un secret, les autres mails.\nPour le DPO : la console montre « Salarié 4821 · Finance », jamais un nom ; lever l’identité demande un motif, l’acte est scellé et le journal ne garde pas le nom révélé. Le SOC lit « entre 10 et 50 k€ » et « [bénéficiaire masqué] » ; le détail ne s’ouvre que sur un signal de fraude, et la consultation entre au journal. Un virement retenu sans fraude va au responsable ou à la finance sur /validation, qui voit montant, bénéficiaire et raison, et décide avec un motif signé. Le relecteur reçoit des faits pseudonymisés ; il tourne aussi sans modèle (mode règles), et en production il passerait par un modèle hébergé dans l’UE ou local (pas encore branché).\nPrévu, pas encore fait : purge à 90 jours, analyse d’impact, information des salariés et consultation du CSE, score de tri réservé aux agents IA. Le volet poste est une option.');
}

// 4. Démo
{
  const slide = pptx.addSlide();
  titre(slide,4,'La démo','Ce que vous allez voir en direct','Deux minutes, sur la machine. Elle tourne aussi sans réseau.');
  bloc(slide,0.68,2.15,4.9,3.98,{bord:C.accent});
  const etapes = [
    'Camille reçoit un mail sosie : la pop-up la prévient avant le clic.',
    'L’assistant de Jean lit un mail qui cache une consigne et veut envoyer son rapport dehors.',
    'La passerelle retient l’appel. La console montre la chaîne, preuve par preuve.',
    'L’analyste coupe l’agent : rien n’est sorti, le rapport porte le sceau du journal.',
    'Deux virements : l’habituel part sans rien afficher, celui au RIB nouveau attend le responsable.',
  ];
  etapes.forEach((t,i)=>{
    texte(slide,`${i+1}`,0.98,2.4+i*0.73,0.4,0.4,{fontFace:'Courier New',fontSize:14,color:i%2?C.ardoise:C.accent,bold:true});
    texte(slide,t,1.45,2.3+i*0.73,3.95,0.66,{fontSize:14,fit:'shrink'});
  });
  capture(slide,'docs/pitch/img/console-incident-agent.png',5.9,2.28,6.75,3.8,
          'Console SOC, prototype local');
  texte(slide,'Entreprise fictive Orbis Pay. L’agent est scripté pour que la démo se rejoue à l’identique.',
        0.68,6.55,12.0,0.37,{fontSize:12,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : garder cette slide, c’est le cœur.\nAvant de monter : cd messagerie && ./demarrer.sh --service ; cd app-mac && ./construire.sh --lancer. Ne pas lancer ./lancer.sh.\nSur scène : Entrée sur « uv run python envoyer_demo.py --cas sosie » (pop-up, Annuler, coach), puis Entrée sur « ./demo.sh jury » à la racine (base neuve, scènes, chrono). Ouvrir le lien de l’incident imprimé par le script, lire « Ce qui s’est passé », puis « Couper l’agent » (motif court, 5 s pour annuler). Le terminal confirme qu’aucun rapport n’est parti. Puis, depuis le dossier, « Exporter » et « Rapport » : le rapport d’une page avec le sceau (une adresse /api/…/rapport tapée à la main répond « Jeton absent ou invalide »). Puis les deux virements par curl sur 127.0.0.1:8712 (commandes dans docs/DEMO_JURY.md) : 320 € à Imprimerie du Lys passe sans pop-up, 3 480 € à Atelier Nord avec un nouveau RIB est retenu, à trancher sur /validation.\nDire clairement : une tentative retenue n’est pas une fuite réussie, et nous ne revendiquons aucun taux de réussite d’attaque sur des modèles réels. Déroulé complet : docs/DEMO_JURY.md.');
}

// 5. Résultats et limites
{
  const slide = pptx.addSlide();
  titre(slide,5,'Résultats et limites','Ce que le banc mesure, et ce qu’il ne prouve pas',`Mesuré le ${M.quand}, sur des backends isolés, avec du trafic écrit pour la démo.`);
  bloc(slide,0.68,2.19,6.6,3.96,{bord:C.accent});
  bloc(slide,7.45,2.19,5.21,3.96,{bord:C.ardoise});
  etiquette(slide,'MESURÉ',0.98,2.49,1.4,C.accent);
  etiquette(slide,'LIMITES',7.75,2.49,1.5,C.ardoise);
  const res=[M.agents, M.fauxPositifs, M.mails, M.relecteur];
  const lim=[
    'Trafic et mails écrits pour la démo',
    'Agent scripté dans le banc ; en mode réel, Haiku a résisté à l’injection (0 tentative en 8 essais)',
    'Désarmeur et analyseur par motifs : une paraphrase peut passer',
    'Coupure envoyée par script : temps de décision humain non mesuré',
  ];
  res.forEach((t,i)=>texte(slide,t,1.0,3.05+i*0.75,6.05,0.66,{fontSize:14.5,fit:'shrink',valign:'top'}));
  lim.forEach((t,i)=>texte(slide,t,7.75,3.05+i*0.75,4.7,0.66,{fontSize:14.5,fit:'shrink',valign:'top'}));
  texte(slide,'Rejouer : python3 docs/mesures/mesurer.py. Dénominateurs et détail dans docs/mesures/resultats.md.',
        0.68,6.45,12.0,0.37,{fontSize:12,color:C.faible,fit:'shrink'});
  slide.addNotes(`VERSION 3 MIN : garder cette slide. Dire les limites avant que le jury les cherche.
Mesures du ${M.quand}, commit ${M.commit}, par python3 docs/mesures/mesurer.py : deux backends isolés (port libre, base temporaire), jamais le backend partagé.
Agents : ${M.agents}. Détection : ${M.detection}. Confinement : ${M.confinement} ; la coupure part d’un script qui relève les incidents toutes les 20 ms, donc c’est le temps technique, pas le temps de réflexion d’un analyste.
Faux positifs : ${M.fauxPositifs}. Mails : ${M.mails}. Désarmeur : ${M.desarmeur}. Relecteur IA : ${M.relecteur}.
Tests : ${M.tests}.
Ces chiffres montrent que le moteur tient sur notre jeu, pas un taux de détection en production. Ils précèdent la vérification des gestes sur signal, la validation métier et la médiation de tous les outils, ajoutées dans la nuit ; la médiation coûte 0,07 ms en médiane sur un appel autorisé. Mode réel (docs/REEL_OU_SIMULE.md) : Haiku a résisté 0/3 puis 0/5 ; avec un attaquant déterministe sur les mêmes services locaux, le mail part sans sAIfe et reste retenu avec.`);
}

// 6. Ce qu'on a fait, ce qu'on vend
{
  const slide = pptx.addSlide();
  titre(slide,6,'Fait et à construire','Ce qu’on a fait, ce qu’on vend','Serveur sur site, données chez le client. Seuls le relecteur IA et l’agent des règles appellent un modèle.');
  bloc(slide,0.68,2.19,5.91,3.7,{bord:C.accent});
  bloc(slide,6.77,2.19,5.89,3.7,{bord:C.ardoise});
  etiquette(slide,'FAIT (PROTOTYPE)',0.98,2.49,2.4,C.accent);
  etiquette(slide,'FEUILLE DE ROUTE',7.07,2.49,2.4,C.ardoise);
  const fait=[
    'Poste : app Mac (mails, sites, téléchargements, agents IA du poste), extension Chrome, garde-mail',
    'Agent : passerelle et médiation de tous les outils, désarmeur, jeton de tâche, canaris',
    'SOC : console en tranches, validation par le responsable, relecteur IA, règles en français, journal signé, SIEM',
  ];
  const route=[
    'App Windows',
    'Microsoft 365 (Outlook, Exchange), puis Google',
    'SSO (OIDC), rôles tirés de l’annuaire',
    'Ancrage du journal sur Avalanche (exploration)',
  ];
  fait.forEach((t,i)=>{
    texte(slide,`${i+1}.`,0.99,3.28+i*0.82,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.accent});
    texte(slide,t,1.48,3.2+i*0.82,4.9,0.62,{fontSize:16,fit:'shrink'});
  });
  route.forEach((t,i)=>{
    texte(slide,`${i+1}.`,7.08,3.2+i*0.62,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.ardoise});
    texte(slide,t,7.57,3.12+i*0.62,4.8,0.55,{fontSize:15.5,fit:'shrink'});
  });
  texte(slide,'On vend la supervision des agents IA, avec le volet poste en option.',
        0.68,6.12,12.0,0.4,{fontSize:16,bold:true,fit:'shrink'});
  texte(slide,'Pas de connexion à Outlook ni à Gmail dans cette démo : le garde-mail lit une boîte locale.',
        0.68,6.6,12.0,0.35,{fontSize:12.3,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : sauter, ou une phrase : ce qui tourne est un prototype, et les testeurs ont demandé Windows, Microsoft 365 et le SSO.\nFait : sur le poste, l’app Mac (pop-up sur un mail frauduleux, un site louche ou un fichier à risque, vérification des virements sur signal, inventaire des agents IA, panneau de transparence), l’extension Chrome contre les sites sosies ou louches et le garde-mail qui explique chaque verdict ; côté agent, la passerelle qui contrôle chaque appel d’outil (outil inconnu, canal détourné, outil MCP modifié), le désarmeur avant lecture, le jeton limité à la tâche, les canaris et la retenue de tout envoi externe ; côté SOC, la console qui lit des tranches, l’espace /validation du responsable et de la finance, le relecteur IA (Haiku) et sa mémoire alimentée par des humains, les règles en français lues par un agent jetable et le retrait réel des droits en trop, le journal chaîné, signé et en ajout seul, l’authentification par rôle, les exports ECS, CEF, Sigma, le syslog, les alertes par rôle et le résumé du lundi.\nFeuille de route : app Windows, Microsoft 365 puis Google, SSO. Avalanche : voie d’exploration, aucune ancre publiée, ne jamais dire que c’est fait.');
}

// 7. Cible et modèle
{
  const slide = pptx.addSlide();
  titre(slide,7,'Cible et modèle','Des entreprises régulées, une licence par agent supervisé','Hypothèses à valider, pas des clients.');
  bloc(slide,0.68,2.19,3.9,3.75,{bord:C.accent});
  etiquette(slide,'CIBLE',0.98,2.45,1.2,C.accent);
  texte(slide,'Finance (DORA, applicable depuis janvier 2025) et santé. 500 à 5 000 salariés, une équipe sécurité, un agent IA en production ou en pilote avancé, Microsoft 365 ou Google Workspace, un SIEM.',
        0.98,2.95,3.3,2.9,{fontSize:16,fit:'shrink',valign:'top'});
  bloc(slide,4.72,2.19,4.1,3.75,{bord:C.ardoise});
  etiquette(slide,'LES PERSONNES',5.02,2.45,2.1,C.ardoise);
  texte(slide,'Le RSSI achète. L’analyste SOC utilise. Le responsable ou la finance confirme les virements retenus. Le DPO valide, le CSE est consulté pour le volet poste.',
        5.02,2.95,3.6,2.9,{fontSize:16.5,fit:'shrink',valign:'top'});
  bloc(slide,8.96,2.19,3.7,3.75,{bord:C.accent});
  etiquette(slide,'MODÈLE',9.26,2.45,1.4,C.accent);
  texte(slide,'Licence annuelle par agent supervisé, poste salarié en option, pilote de 3 mois. Pas de prix affiché.',
        9.26,2.95,3.1,1.7,{fontSize:16.5,fit:'shrink',valign:'top'});
  texte(slide,'À valider en dix entretiens avec des RSSI.',
        9.26,4.8,3.1,1.0,{fontSize:15,color:C.accent,fit:'shrink',valign:'top'});
  texte(slide,'Prospects à vérifier : fintech et paiement, assurtech et mutuelles, santé numérique ; grandes banques comme validateurs. Pas la première cible : moins de 250 salariés, sans équipe sécurité ni agents ; une PME s’en sert avec la validation par le responsable. Aucun n’est client ni contacté.',
        0.68,6.2,12.0,0.7,{fontSize:12,color:C.faible,fit:'shrink',valign:'top'});
  slide.addNotes(`VERSION 3 MIN : garder cette slide, en trente secondes : cible, qui achète, licence par agent supervisé, pilote de 3 mois.
Deux hypothèses à valider en dix entretiens avec des RSSI : (1) un RSSI finance la supervision d’agents IA sur un budget sécurité existant ; (2) la licence par agent supervisé reste lisible quand le nombre d’agents monte. Méthode : dix RSSI de la cible, un guide d’entretien identique, on note le budget, le décideur et le déclencheur d’achat. Aucun prix n’est affiché : l’ancienne fourchette de 5 à 30 euros par utilisateur est abandonnée.
DORA s’applique depuis le 17 janvier 2025. NIS2 est une directive européenne ; la loi française de transposition est encore attendue (texte inscrit à l’Assemblée nationale début octobre 2026, non adopté à notre connaissance) : ne pas la présenter comme applicable en France.`);
}

// 8. Équipe et retours de test
{
  const slide = pptx.addSlide();
  titre(slide,8,'Équipe','Deux personnes, un week-end','Secure Horizons, Track 2.');
  const gens=[
    ['Guilhem','Agents IA et technique',C.accent],
    ['Paul','Mails et business',C.ardoise],
  ];
  gens.forEach((g,i)=>{
    const x=0.68+i*3.07;
    bloc(slide,x,2.39,2.8,2.6,{bord:g[2]});
    texte(slide,g[0],x+0.22,2.9,2.5,0.5,{fontSize:22,bold:true,fit:'shrink'});
    ligne(slide,x+0.22,3.6,x+2.58,3.6,C.trait,0.9);
    texte(slide,g[1],x+0.22,3.8,2.36,0.9,{fontSize:15,color:C.doux,fit:'shrink'});
  });
  bloc(slide,6.82,2.39,5.84,2.6,{bord:C.trait,fond:C.panneau});
  etiquette(slide,'TESTÉ CE WEEK-END',7.1,2.62,2.6,C.accent);
  texte(slide,'Deux tours de trois testeurs joués par des agents (RSSI, analyste SOC, DPO, DSI sans SOC, sécurité IA) : 4, 5 et 4 sur 10, puis 5, 5 et 6. Corrigé depuis : authentification, journal signé, médiation des outils, SOC en tranches, validation par le responsable, SIEM, SMS simulé. Demandé, pas fait : Windows, Microsoft 365, SSO.',
        7.1,3.1,5.3,1.75,{fontSize:13.5,fit:'shrink',valign:'top'});
  texte(slide,'Code, tests et mesures dans le dépôt Git. Déroulé de la démo : docs/DEMO_JURY.md',
        0.68,6.45,12.0,0.36,{fontFace:'Courier New',fontSize:11.2,color:C.faible});
  slide.addNotes('VERSION 3 MIN : sauter ou citer les deux noms en dix secondes.\nLes tests de samedi soir ont été joués par des agents, pas par de vraies personnes : le dire si on en parle. Premier tour : RSSI d’une fintech, analyste SOC, DPO d’une santé numérique. Second tour (22 h 45) : RSSI d’une ETI industrielle, responsable informatique d’un cabinet sans SOC, responsable sécurité IA d’une mutuelle. Le second tour a trouvé l’absence d’authentification, le journal qu’on pouvait réécrire, les règles qui perdaient des conditions et les outils inconnus de la passerelle : tout est corrigé. Ce qu’ils ont aimé : « Ce qui s’est passé » en deux phrases, le panneau de décision, les chiffres avec leurs dénominateurs. Ce qu’ils ont relevé et qu’on a corrigé : agents tous nommés « Agent IA », prénom du salarié trop visible, décisions au premier clic sans motif, virement sans montant ni bénéficiaire, rien à faire côté salarié.');
}

pptx.writeFile({fileName:sortie}).then(()=>console.log(sortie));
