// Génère le deck modifiable de Dédale avec pptxgenjs (npm install pptxgenjs).
// Les captures sont celles du prototype local du 10 octobre 2026.
const path = require('path');
const pptxgen = require('pptxgenjs');

const racine = path.resolve(__dirname, '../..');
const sortie = path.join(__dirname, 'dedale-pitch-8-slides.pptx');
const image = (chemin) => path.join(racine, chemin);
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Équipe Dédale';
pptx.subject = 'Démonstration du prototype Dédale, Secure Horizons 2026';
pptx.title = 'Dédale : salariés et agents IA, une même console SOC';
pptx.company = 'Dédale';
pptx.lang = 'fr-FR';
pptx.theme = {
  headFontFace: 'Arial',
  bodyFontFace: 'Arial',
  lang: 'fr-FR',
};

const W = 13.333;
const H = 7.5;
const S = pptx.ShapeType;
const C = {
  nuit: '071522', fond: '0A1A29', panneau: '12263A', panneau2: '0F2234',
  trait: '294459', blanc: 'F4F8FB', doux: 'ABC0CE', faible: '718EA1',
  cyan: '46CFF1', cyanPale: '173B50', violet: 'A29CF8', violetPale: '252C55',
  rouge: 'F18F92', vert: '65D6B0',
};
const sansMarge = 0;

function fond(slide, couleur=C.nuit) {
  slide.background = { color: couleur };
  slide.addShape(S.rect, { x:0, y:0, w:W, h:0.06, line:{color:C.cyan, transparency:100}, fill:{color:C.cyan} });
}
function texte(slide, contenu, x, y, w, h, options={}) {
  slide.addText(contenu, {
    x, y, w, h, margin:sansMarge, breakLine:false, valign:'mid',
    color:C.blanc, fontFace:'Arial', fontSize:18,
    ...options,
  });
}
function titre(slide, numero, rubrique, libelle, sousTitre) {
  fond(slide);
  texte(slide, rubrique.toUpperCase(), 0.65, 0.37, 8, 0.31,
        {fontSize:11, color:C.cyan, bold:true, charSpacing:1.2});
  texte(slide, libelle, 0.65, 0.83, 12.05, 0.66,
        {fontSize:30, bold:true, fit:'shrink'});
  if (sousTitre) texte(slide, sousTitre, 0.67, 1.49, 11.95, 0.48,
                       {fontSize:15, color:C.doux, fit:'shrink'});
  pied(slide, numero);
}
function pied(slide, numero) {
  slide.addShape(S.line, {x:0.65,y:7.11,w:12.05,h:0,line:{color:C.trait,width:0.8}});
  texte(slide, 'DÉDALE  /  SECURE HORIZONS 2026  /  PROTOTYPE LOCAL',
        0.65, 7.17, 10.6, 0.19,
        {fontFace:'Courier New',fontSize:8.2,color:C.faible,charSpacing:0.5});
  texte(slide, `${String(numero).padStart(2,'0')} / 08`, 11.6, 7.16, 1.1, 0.2,
        {fontFace:'Courier New',fontSize:8.4,color:C.faible,align:'right'});
}
function bloc(slide,x,y,w,h,options={}) {
  slide.addShape(S.roundRect, {x,y,w,h,rectRadius:0.12,
    line:{color:options.bord||C.trait,width:options.largeur||0.9},
    fill:{color:options.fond||C.panneau}, radius:0.12});
}
function etiquette(slide,libelle,x,y,w,couleur=C.cyan) {
  slide.addShape(S.roundRect,{x,y,w,h:0.33,rectRadius:0.12,
    line:{color:couleur,width:0.7},fill:{color:C.nuit,transparency:20}});
  texte(slide,libelle,x+0.08,y+0.055,w-0.16,0.21,
        {fontFace:'Courier New',fontSize:9.5,color:couleur,bold:true,align:'center'});
}
function ligne(slide,x1,y1,x2,y2,couleur=C.trait,largeur=1.5) {
  slide.addShape(S.line,{x:x1,y:y1,w:x2-x1,h:y2-y1,line:{color:couleur,width:largeur}});
}
function capture(slide,chemin,x,y,w,h,legende) {
  bloc(slide,x-0.08,y-0.08,w+0.16,h+0.16,{fond:'081522',bord:C.trait});
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
  titre(slide,1,'Dédale  /  Le problème','Un contenu piégé vise deux lecteurs : le salarié et l’agent',
        'Trois cas documentés, aucun ne vient de Dédale.');
  const cartes = [
    {tag:'SALARIÉ', c:C.cyan, gros:'33 %', txt:'des salariés non formés échouent aux tests de phishing simulés. Après un an de formation : 4 %.',
     src:'KnowBe4, rapport 2025', url:URL_KB},
    {tag:'AGENT', c:C.violet, gros:'EchoLeak', txt:'CVE-2025-32711. Un mail piégé fait fuiter des données par Microsoft 365 Copilot, sans aucune action humaine.',
     src:'Aim Security, juin 2025', url:URL_ECHO},
    {tag:'AGENT', c:C.violet, gros:'Serveur MCP', txt:'Une issue GitHub piégée pousse l’agent à copier des dépôts privés dans une pull request publique (mai 2025).',
     src:'Invariant Labs, 26 mai 2025', url:URL_MCP},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*4.1;
    bloc(slide,x,2.3,3.85,3.75,{fond:C.panneau2,bord:o.c});
    etiquette(slide,o.tag,x+0.25,2.55,1.5,o.c);
    texte(slide,o.gros,x+0.25,3.05,3.4,0.8,{fontSize:o.gros.length>6?28:44,bold:true,color:o.c,fit:'shrink'});
    texte(slide,o.txt,x+0.25,3.95,3.35,1.5,{fontSize:15,fit:'shrink',valign:'top'});
    texte(slide,o.src,x+0.25,5.6,3.35,0.3,{fontFace:'Courier New',fontSize:10.5,color:C.doux});
  });
  texte(slide,'Sources de chaque cas dans les notes. Un seul tableau de bord pour les deux lecteurs.',
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
  titre(slide,2,'La solution','Un seul moteur pour le salarié et pour l’agent','Un garde du corps qui intervient une seconde avant le geste, en local.');
  const cartes = [
    {n:'01',t:'Détecter',d:'Le geste à risque, au poste ou à la passerelle de l’agent.',c:C.cyan},
    {n:'02',t:'Boîte noire',d:'Source, consigne, outil appelé, décision, résultat.',c:C.violet},
    {n:'03',t:'L’humain tranche',d:'Le salarié ou l’analyste SOC choisit. Rien ne se bloque tout seul.',c:C.cyan},
    {n:'04',t:'Exports',d:'Export ECS et règles Sigma pour le SIEM, brouillon de notification NIS2.',c:C.violet},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*3.07;
    bloc(slide,x,2.39,2.8,3.0,{fond:C.panneau2,bord:o.c});
    texte(slide,o.n,x+0.22,2.65,0.65,0.43,{fontFace:'Courier New',fontSize:16.5,color:o.c,bold:true});
    texte(slide,o.t,x+0.22,3.2,2.5,0.44,{fontSize:20,bold:true,fit:'shrink'});
    ligne(slide,x+0.22,3.8,x+2.58,3.8,C.trait,0.9);
    texte(slide,o.d,x+0.22,4.0,2.36,1.25,{fontSize:15.1,color:C.doux,fit:'shrink',valign:'top'});
  });
  texte(slide,'Ce qu’on ne fait pas : tout bloquer, remplacer votre SIEM, classer vos documents.',
        0.68,5.75,12.0,0.4,{fontSize:16,bold:true,fit:'shrink'});
  texte(slide,'Le brouillon NIS2 est à relire : ce n’est ni une qualification juridique ni une notification envoyée.',
        0.68,6.3,12.0,0.4,{fontSize:12.5,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : garder cette slide.\nUn pare-feu protège les tuyaux ; Dédale protège ceux qui décident d’ouvrir. Le poste du salarié n’est jamais coupé : il avertit, la personne choisit. Pour l’agent, c’est l’appel d’outil qui est retenu avant exécution. Ce qu’on ne fait pas : tout bloquer, remplacer le SIEM (on lui envoie des incidents ECS et des règles Sigma), classer les documents de l’entreprise. NIS2 est une directive européenne et la loi française de transposition est encore attendue : on ne la présente pas comme déjà applicable en France. Référentiels de lecture, sans certification : NIST CSF 2.0, MITRE ATT&CK et ATLAS, OWASP agentique.');
}

// 3. Volet poste
{
  const slide = pptx.addSlide();
  titre(slide,3,'Volet poste','Protéger le salarié sans le fliquer','Ce que le DPO et le CSE voudront entendre.');
  const lignes = [
    ['01','Tout est traité en local sur le poste.'],
    ['02','Aucun contenu ne sort : ni mail, ni fichier, ni texte collé.'],
    ['03','Seule une catégorie neutralisée remonte à la SOC.'],
    ['04','Le salarié garde la main : Dédale avertit, il ne bloque jamais.'],
  ];
  lignes.forEach((l,i)=>{
    texte(slide,l[0],0.72,2.35+i*0.98,0.6,0.5,{fontFace:'Courier New',fontSize:15,color:i%2?C.violet:C.cyan,bold:true});
    texte(slide,l[1],1.4,2.2+i*0.98,4.8,0.8,{fontSize:17.5,fit:'shrink'});
  });
  capture(slide,'landing/img/gen/salarie-garde.png',6.45,2.18,6.2,3.49,'Image d’illustration');
  texte(slide,'Le volet poste est une option. Le CSE est consulté avant tout déploiement.',
        0.68,6.35,12.0,0.4,{fontSize:15,color:C.doux,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : sauter cette slide, garder une phrase dans la démo : le poste avertit, le salarié décide, rien ne sort. Pour le DPO : pas de contenu collecté, seulement une catégorie neutralisée. Pour le CSE : pas de blocage, pas de profil individuel, volet poste en option et consulté en amont. Dans le prototype, les gestes du poste sont simulés.');
}

// 4. Démo
{
  const slide = pptx.addSlide();
  titre(slide,4,'La démo','Ce que vous allez voir en direct','Une commande, trois minutes, hors ligne.');
  bloc(slide,0.68,2.15,4.9,3.98,{fond:C.panneau2,bord:C.cyan});
  const etapes = [
    'Camille ouvre un faux mail : la pop-up l’arrête avant le clic.',
    'Un agent interne lit un mail piégé et tente un appel d’outil.',
    'La passerelle retient l’appel. La console reconstruit la chaîne.',
    'L’analyste coupe ou reprend. Export SIEM et brouillon NIS2.',
  ];
  etapes.forEach((t,i)=>{
    texte(slide,`${i+1}`,0.98,2.45+i*0.88,0.4,0.4,{fontFace:'Courier New',fontSize:15,color:i%2?C.violet:C.cyan,bold:true});
    texte(slide,t,1.45,2.35+i*0.88,3.95,0.75,{fontSize:15.2,fit:'shrink'});
  });
  capture(slide,'landing/img/shots/incident-boite-noire.png',5.9,2.28,6.75,3.36,
          'Console SOC, prototype local du 10 octobre 2026');
  texte(slide,'Entreprise fictive Orbis Pay. L’agent est scripté pour que la démo soit reproductible.',
        0.68,6.47,12.0,0.37,{fontSize:12,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : garder cette slide, c’est le cœur.\nLancer ./lancer.sh puis ./demo.sh. Pour voir un incident côté salarié, choisir continuer. Dans la console, ouvrir l’incident de l’agent et décider couper. Dire clairement : une tentative retenue n’est pas une fuite réussie, et nous ne revendiquons aucun taux de réussite d’attaque sur des modèles réels.');
}

// 5. Résultats et limites
{
  const slide = pptx.addSlide();
  titre(slide,5,'Résultats et limites','Ce que le banc mesure, et ce qu’il ne prouve pas','Trafic synthétique produit par notre propre banc, contre le vrai backend.');
  bloc(slide,0.68,2.19,5.91,3.96,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.19,5.89,3.96,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'RÉSULTATS DU 10 OCTOBRE',0.98,2.49,3.1,C.cyan);
  etiquette(slide,'LIMITES',7.07,2.49,1.5,C.violet);
  const res=[
    '0 faux positif sur 50 sessions humaines ou scriptées',
    '25 sessions de la vraie passerelle : 25 incidents, 25 suspendues',
    'Agent imité par le banc : classé 0/25, le canari l’arrête (25/50 au sens strict)',
  ];
  const lim=[
    'Cohérence du moteur, pas détection réelle',
    'Outil MCP piégé repéré par motifs, contournable par paraphrase ; désarmeur en cours',
    'Agents fictifs, scénarios scriptés',
    'Journal horodaté, scellement en cours',
  ];
  res.forEach((t,i)=>texte(slide,t,1.0,3.1+i*0.99,5.3,0.85,{fontSize:15.5,fit:'shrink',valign:'top'}));
  lim.forEach((t,i)=>texte(slide,t,7.1,3.1+i*0.75,5.3,0.65,{fontSize:15.5,fit:'shrink',valign:'top'}));
  texte(slide,'Détail et dénominateurs dans docs/FICHE_JURY.md. Ces taux ne prédisent pas une performance en production.',
        0.68,6.45,12.0,0.37,{fontSize:12,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : garder cette slide. Dire les limites avant que le jury les cherche.\nRésultats : campagne c1010184730f49a (100 sessions, 25 par type) et campagne c10101848586937 (25 sessions jouées par la vraie bibliothèque interne et sa passerelle : 25/25 classées, 25/25 incidents, 25/25 suspendues). Limites : métriques sur trafic synthétique ; détection de l’outil MCP piégé par motifs, contournable par paraphrase, renforcée par le désarmeur en cours ; agents fictifs et scénarios scriptés ; journal horodaté, le scellement est en cours (on ne dit pas « infalsifiable » tant que l’endpoint de vérification n’existe pas).');
}

// 6. Ce qu'on a fait, ce qu'on vend
{
  const slide = pptx.addSlide();
  titre(slide,6,'Fait et à construire','Ce qu’on a fait, ce qu’on vend','Rien ne sort de l’entreprise : serveur sur site, données chez le client.');
  bloc(slide,0.68,2.19,5.91,3.7,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.19,5.89,3.7,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'FAIT (PROTOTYPE)',0.98,2.49,2.4,C.cyan);
  etiquette(slide,'FEUILLE DE ROUTE',7.07,2.49,2.4,C.violet);
  const fait=[
    'Gestes salariés simulés, pop-up d’avertissement',
    'Passerelle, droits minimaux et canaris pour l’agent',
    'Console SOC, boîte noire, exports',
  ];
  const route=[
    'Connecteurs réels Microsoft 365 et Google',
    'Étiquettes de sensibilité',
    'Authentification et journal persistant',
  ];
  fait.forEach((t,i)=>{
    texte(slide,`${i+1}.`,0.99,3.28+i*0.82,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.cyan});
    texte(slide,t,1.48,3.2+i*0.82,4.8,0.62,{fontSize:16,fit:'shrink'});
  });
  route.forEach((t,i)=>{
    texte(slide,`${i+1}.`,7.08,3.28+i*0.82,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.violet});
    texte(slide,t,7.57,3.2+i*0.82,4.8,0.62,{fontSize:16,fit:'shrink'});
  });
  texte(slide,'On vend la supervision des agents IA, avec le volet poste en option.',
        0.68,6.12,12.0,0.4,{fontSize:16,bold:true,fit:'shrink'});
  texte(slide,'Pas de surveillance native du Mac ni de connexion Outlook ou Gmail dans cette démo.',
        0.68,6.6,12.0,0.35,{fontSize:12.3,color:C.faible,fit:'shrink'});
  slide.addNotes('VERSION 3 MIN : sauter, ou une phrase : ce qui tourne est un prototype, la feuille de route tient en trois étapes. Distinguer à voix haute ce qui est livré et ce qui est visé : les connecteurs Microsoft 365 et Google, les étiquettes de sensibilité, l’authentification et le journal persistant viennent après le hackathon.');
}

// 7. Cible et modèle
{
  const slide = pptx.addSlide();
  titre(slide,7,'Cible et modèle','Des entreprises régulées, une licence par agent supervisé','Hypothèses à valider, pas des clients.');
  bloc(slide,0.68,2.19,3.9,3.75,{fond:C.panneau2,bord:C.cyan});
  etiquette(slide,'CIBLE',0.98,2.45,1.2,C.cyan);
  texte(slide,'Finance (DORA, applicable depuis janvier 2025) et santé. 500 à 5 000 salariés, une équipe sécurité, un agent IA en production ou en pilote avancé, Microsoft 365 ou Google Workspace, un SIEM.',
        0.98,2.95,3.3,2.9,{fontSize:16,fit:'shrink',valign:'top'});
  bloc(slide,4.72,2.19,4.1,3.75,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'LES PERSONNES',5.02,2.45,2.1,C.violet);
  texte(slide,'Le RSSI achète. L’analyste SOC utilise. Le responsable IA ou data copilote. Le DPO et la conformité valident. Le CSE est consulté pour le volet poste.',
        5.02,2.95,3.6,2.9,{fontSize:16.5,fit:'shrink',valign:'top'});
  bloc(slide,8.96,2.19,3.7,3.75,{fond:C.panneau2,bord:C.cyan});
  etiquette(slide,'MODÈLE',9.26,2.45,1.4,C.cyan);
  texte(slide,'Licence annuelle par agent supervisé, poste salarié en option, pilote de 3 mois. Pas de prix affiché.',
        9.26,2.95,3.1,1.7,{fontSize:16.5,fit:'shrink',valign:'top'});
  texte(slide,'À valider en dix entretiens avec des RSSI.',
        9.26,4.8,3.1,1.0,{fontSize:15,color:C.cyan,fit:'shrink',valign:'top'});
  texte(slide,'Prospects à vérifier : fintech et paiement, assurtech et mutuelles, santé numérique ; grandes banques comme validateurs. Hors cible : moins de 250 salariés, sans équipe sécurité ni agents. Aucun n’est client ni contacté.',
        0.68,6.2,12.0,0.7,{fontSize:12,color:C.faible,fit:'shrink',valign:'top'});
  slide.addNotes(`VERSION 3 MIN : garder cette slide, en trente secondes : cible, qui achète, licence par agent supervisé, pilote de 3 mois.
Deux hypothèses à valider en dix entretiens avec des RSSI : (1) un RSSI finance la supervision d’agents IA sur un budget sécurité existant ; (2) la licence par agent supervisé reste lisible quand le nombre d’agents monte. Méthode : dix RSSI de la cible, un guide d’entretien identique, on note le budget, le décideur et le déclencheur d’achat. Aucun prix n’est affiché : l’ancienne fourchette de 5 à 30 euros par utilisateur est abandonnée.
DORA s’applique depuis le 17 janvier 2025. NIS2 est une directive européenne ; la loi française de transposition est encore attendue (texte inscrit à l’Assemblée nationale début octobre 2026, non adopté à notre connaissance) : ne pas la présenter comme applicable en France.`);
}

// 8. Équipe
{
  const slide = pptx.addSlide();
  titre(slide,8,'Équipe','Quatre personnes, un week-end','Secure Horizons, Track 2.');
  const gens=[
    ['Guilhem','Agents IA et technique',C.cyan],
    ['Paul','Mails et business',C.violet],
    ['Pierre-Antoine','',C.cyan],
    ['Théophile','',C.violet],
  ];
  gens.forEach((g,i)=>{
    const x=0.68+i*3.07;
    bloc(slide,x,2.39,2.8,2.6,{fond:C.panneau2,bord:g[2]});
    texte(slide,g[0],x+0.22,2.9,2.5,0.5,{fontSize:22,bold:true,fit:'shrink'});
    ligne(slide,x+0.22,3.6,x+2.58,3.6,C.trait,0.9);
    if (g[1]) texte(slide,g[1],x+0.22,3.8,2.36,0.9,{fontSize:15,color:C.doux,fit:'shrink'});
  });
  texte(slide,'Démo et code : entreprise fictive Orbis Pay. Dépôt et guide de démo : docs/DEMO.md',
        0.68,6.45,12.0,0.36,{fontFace:'Courier New',fontSize:11.2,color:C.faible});
  slide.addNotes('VERSION 3 MIN : sauter ou citer les noms en dix secondes.\nRôles de Pierre-Antoine et de Théophile non donnés : cases laissées vides, à remplir quand Guilhem les confirme.');
}

pptx.writeFile({fileName:sortie}).then(()=>console.log(sortie));
