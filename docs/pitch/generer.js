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

// 1. Couverture
{
  const slide = pptx.addSlide();
  slide.addImage({path:image('landing/img/gen/hero.png'),x:0,y:0,w:W,h:H});
  slide.addShape(S.rect,{x:0,y:0,w:7.65,h:H,
    line:{color:C.nuit,transparency:100},fill:{color:C.nuit,transparency:8}});
  slide.addShape(S.rect,{x:7.65,y:0,w:2.0,h:H,
    line:{color:C.nuit,transparency:100},fill:{color:C.nuit,transparency:55}});
  etiquette(slide,'TRACK 2  ·  CYBERSÉCURITÉ',0.78,0.79,3.0);
  texte(slide,'Dédale',0.77,1.74,6.5,0.95,{fontSize:54,bold:true});
  texte(slide,'Le garde du corps des salariés\net des agents IA',0.8,2.85,6.35,1.35,
        {fontSize:28,bold:true,breakLine:false,fit:'shrink'});
  ligne(slide,0.8,4.45,2.7,4.45,C.cyan,3);
  texte(slide,'Même console SOC. Deux gestes à risque.\nUne décision humaine traçable.',
        0.8,4.74,5.9,0.95,{fontSize:19,color:C.doux,breakLine:false});
  texte(slide,'Prototype local · 10 octobre 2026',0.8,6.66,5.1,0.28,
        {fontFace:'Courier New',fontSize:10,color:C.doux});
  slide.addNotes('Ouvrir sur les deux acteurs qui lisent et agissent. Le deck décrit le prototype du 10 octobre 2026. L’application native, les connexions Outlook/Gmail et le déploiement sur site sont la cible produit, pas des fonctions disponibles ici.');
}

// 2. Problème et donnée sourcée
{
  const slide = pptx.addSlide();
  titre(slide,2,'Problème','Deux lecteurs, un même piège','Un message frauduleux peut orienter un salarié ou détourner un agent qui lit à sa place.');
  bloc(slide,0.67,2.17,4.28,3.92,{fond:C.panneau2,bord:C.cyan});
  texte(slide,'33,1 %',0.95,2.48,3.7,1.0,{fontSize:58,bold:true,color:C.cyan});
  texte(slide,'Taux initial de personnes susceptibles d’interagir avec une simulation de phishing, avant formation.',
        0.99,3.51,3.62,1.29,{fontSize:18,fit:'shrink'});
  ligne(slide,0.98,5.03,4.62,5.03,C.trait,0.8);
  texte(slide,'67,7 M de tests · 62 400 organisations',0.98,5.18,3.65,0.39,
        {fontFace:'Courier New',fontSize:10.2,color:C.doux,fit:'shrink'});
  capture(slide,'landing/img/gen/mail-garde.png',5.26,2.18,7.39,4.16);
  texte(slide,'Source : KnowBe4, Phishing by Industry Benchmarking Report 2025. Illustration conceptuelle ; chiffre hors Dédale.',
        0.68,6.55,11.9,0.35,{fontSize:10.4,color:C.faible,fit:'shrink',
          hyperlink:{url:'https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report'}});
  slide.addNotes('Le benchmark KnowBe4 2025 annonce 33,1 % de Phish-prone Percentage initial, basé sur 67,7 millions de tests simulés dans 62 400 organisations. Ne pas dire que 33,1 % des salariés cliquent sur de vrais mails frauduleux. Source : https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report');
}

// 3. Angle commun
{
  const slide = pptx.addSlide();
  titre(slide,3,'Angle','Le risque apparaît au moment d’agir','Le prototype surveille deux chemins, avec des réponses adaptées à chacun.');
  bloc(slide,0.68,2.15,5.89,3.83,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.15,5.89,3.83,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'SALARIÉ',0.97,2.48,1.55,C.cyan);
  etiquette(slide,'AGENT IA',7.05,2.48,1.71,C.violet);
  texte(slide,'Un mail frauduleux arrive',0.98,3.08,5.12,0.52,{fontSize:21,bold:true});
  texte(slide,'Le garde signale le geste. Camille choisit annuler ou continuer.',
        0.98,3.78,4.93,1.0,{fontSize:17,color:C.doux,fit:'shrink'});
  texte(slide,'Annuler évite l’incident simulé. Continuer ouvre un dossier.',
        0.98,5.14,4.98,0.52,{fontSize:14.2,color:C.cyan,fit:'shrink'});
  texte(slide,'Une consigne se cache dans un mail ou un outil',7.06,3.08,5.18,0.8,
        {fontSize:21,bold:true,fit:'shrink'});
  texte(slide,'La passerelle retient l’appel. L’analyste choisit couper ou reprendre.',
        7.06,4.06,4.96,0.91,{fontSize:17,color:C.doux,fit:'shrink'});
  texte(slide,'Couper arrête l’agent. Reprendre libère l’appel retenu.',
        7.06,5.14,5.02,0.52,{fontSize:14.2,color:C.violet,fit:'shrink'});
  texte(slide,'Dans cette démo : gestes salariés simulés et agent interne scripté.',
        0.68,6.34,11.98,0.35,{fontSize:12.8,color:C.faible,fit:'shrink'});
  slide.addNotes('Faire la distinction à voix haute : le choix du salarié ne coupe jamais le poste. Pour l’agent, le contrôle humain s’applique à un appel d’outil retenu. La variante droits refuse localement un appel hors du jeton de tâche.');
}

// 4. Chaîne SOC
{
  const slide = pptx.addSlide();
  titre(slide,4,'Méthode','Une enquête dans la même console','Chaque incident relie le signal, l’action tentée, la décision et son résultat.');
  const cartes = [
    {n:'01',t:'Observer',d:'Événement du poste ou de la passerelle de l’agent',c:C.cyan},
    {n:'02',t:'Reconstituer',d:'Boîte noire : source, signal, outil et conséquence',c:C.violet},
    {n:'03',t:'Décider',d:'Choix explicite du salarié ou de l’analyste SOC',c:C.cyan},
    {n:'04',t:'Exporter',d:'ECS, Sigma et brouillon NIS2 à relire',c:C.violet},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*3.17;
    bloc(slide,x,2.39,2.91,3.26,{fond:C.panneau2,bord:o.c});
    texte(slide,o.n,x+0.22,2.68,0.65,0.43,{fontFace:'Courier New',fontSize:16.5,color:o.c,bold:true});
    texte(slide,o.t,x+0.22,3.29,2.4,0.44,{fontSize:20,bold:true});
    ligne(slide,x+0.22,3.9,x+2.67,3.9,C.trait,0.9);
    texte(slide,o.d,x+0.22,4.13,2.42,1.06,{fontSize:15.1,color:C.doux,fit:'shrink'});
  });
  texte(slide,'Le brouillon NIS2 n’est ni une qualification juridique ni une notification envoyée.',
        0.68,6.15,12.0,0.4,{fontSize:13.2,color:C.faible,fit:'shrink'});
  slide.addNotes('Montrer que le dossier est consultable dans la console et que les exports sont dérivés des faits. Ne pas présenter le brouillon NIS2 comme un envoi réglementaire automatique.');
}

// 5. Démo
{
  const slide = pptx.addSlide();
  titre(slide,5,'Démo','Du mail au dossier d’incident','Un seul lancement crée les deux scènes sur le backend local.');
  bloc(slide,0.68,2.15,4.15,3.98,{fond:C.panneau2,bord:C.cyan});
  etiquette(slide,'./demo.sh',0.98,2.48,1.91,C.cyan);
  texte(slide,'1  Camille reçoit un mail frauduleux et choisit annuler ou continuer.',
        0.99,3.07,3.48,0.96,{fontSize:16.9,fit:'shrink'});
  ligne(slide,0.99,4.22,4.46,4.22,C.trait,0.9);
  texte(slide,'2  L’agent lit un mail piégé. Son appel sortant attend la décision SOC.',
        0.99,4.48,3.5,1.12,{fontSize:16.9,fit:'shrink'});
  capture(slide,'landing/img/shots/incident-boite-noire.png',5.16,2.28,7.52,3.74,
          'Capture du prototype local, 10 octobre 2026');
  texte(slide,'La démo utilise Orbis Pay, une entreprise fictive, et ne transmet aucun rapport réel.',
        0.68,6.47,12.0,0.37,{fontSize:11.5,color:C.faible,fit:'shrink'});
  slide.addNotes('Commande du guide : ./lancer.sh, puis ./demo.sh. Montrer le choix salarié ; pour voir un incident humain, choisir continuer. Dans la console, ouvrir ensuite l’incident de l’agent et décider couper. La capture représente le prototype local au 10 octobre 2026 ; la démo vivante fait foi.');
}

// 6. Preuve technique agents
{
  const slide = pptx.addSlide();
  titre(slide,6,'Preuve technique','L’appel d’outil est le point de contrôle','Canari, journal d’outil et décision humaine sont visibles dans le même incident.');
  capture(slide,'landing/img/shots/outil-mcp-piege.png',0.68,2.21,8.08,4.03,
          'Capture du scénario outil MCP piégé, données fictives');
  bloc(slide,9.03,2.21,3.63,4.03,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'OUTIL MCP PIÉGÉ',9.28,2.49,2.85,C.violet);
  texte(slide,'Une consigne suspecte se cache dans la description de l’outil.',
        9.29,3.13,2.98,0.81,{fontSize:16.5,fit:'shrink'});
  ligne(slide,9.29,4.14,12.27,4.14,C.trait,0.9);
  texte(slide,'La passerelle retient l’appel sortant. L’analyste coupe ou reprend.',
        9.29,4.37,2.98,0.95,{fontSize:16.5,fit:'shrink'});
  texte(slide,'Hors droits : l’appel est refusé localement.',
        9.29,5.55,2.98,0.45,{fontSize:12.8,color:C.violet,fit:'shrink'});
  slide.addNotes('Préciser que l’agent du parcours commun est scripté et les secrets sont faux. Un outil MCP empoisonné correspond à la variante --avec-mcp ; une tentative hors droits à --avec-droits. Ce ne sont pas des attaques sur un service réel. Ne pas affirmer une exfiltration réussie lorsque seul un appel a été tenté.');
}

// 7. État et déploiement
{
  const slide = pptx.addSlide();
  titre(slide,7,'Déploiement','Ce qui tourne. Ce qu’il reste à intégrer.','Le prototype local prouve le flux de défense, pas une surveillance native des postes.');
  bloc(slide,0.68,2.19,5.91,3.96,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.19,5.89,3.96,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'AUJOURD’HUI',0.98,2.49,2.22,C.cyan);
  etiquette(slide,'CIBLE PRODUIT',7.07,2.49,2.55,C.violet);
  const actuel=[
    'Gestes salariés simulés et avertissement',
    'Agent fictif et appels d’outils locaux',
    'Backend, console SOC, incidents et exports',
  ];
  const futur=[
    'Application de poste discrète',
    'Connexions messagerie et navigateur autorisées',
    'Passerelle pour les agents déployés sur site',
  ];
  actuel.forEach((t,i)=>{
    texte(slide,`${i+1}.`,0.99,3.22+i*0.77,0.42,0.39,
          {fontFace:'Courier New',fontSize:14,color:C.cyan});
    texte(slide,t,1.48,3.16+i*0.77,4.77,0.58,
          {fontSize:16.0,fit:'shrink'});
  });
  futur.forEach((t,i)=>{
    texte(slide,`${i+1}.`,7.08,3.22+i*0.77,0.42,0.39,
          {fontFace:'Courier New',fontSize:14,color:C.violet});
    texte(slide,t,7.57,3.16+i*0.77,4.72,0.58,
          {fontSize:16.0,fit:'shrink'});
  });
  texte(slide,'Mesures du banc : trafic synthétique. Aucune performance en production annoncée.',
        0.68,6.45,12.0,0.37,{fontSize:12.3,color:C.faible,fit:'shrink'});
  slide.addNotes('Le produit visé fonctionnerait dans l’environnement de l’entreprise. Aucune intégration native Mac, Outlook ou Gmail n’est actuellement livrée. Les taux du banc ne peuvent pas être extrapolés à la production.');
}

// 8. Marché, équipe, suite
{
  const slide = pptx.addSlide();
  titre(slide,8,'Suite','Prouver la valeur chez un client cible','Notre hypothèse : organisations avec beaucoup de salariés, données sensibles et agents IA en déploiement.');
  bloc(slide,0.68,2.18,6.01,3.96,{fond:C.panneau2,bord:C.cyan});
  texte(slide,'Première validation',0.99,2.52,5.36,0.52,{fontSize:22,bold:true});
  texte(slide,'Un pilote instrumenté : scénarios indépendants, erreurs du détecteur, temps de traitement par l’analyste et limites documentées.',
        0.99,3.29,5.17,1.47,{fontSize:18,fit:'shrink'});
  ligne(slide,0.99,5.12,6.35,5.12,C.trait,0.9);
  texte(slide,'Aucun prospect cité comme client acquis.',0.99,5.39,5.16,0.37,
        {fontSize:12.9,color:C.cyan,fit:'shrink'});
  bloc(slide,6.91,2.18,5.75,3.96,{fond:C.panneau2,bord:C.violet});
  texte(slide,'Équipe du hackathon',7.23,2.52,5.0,0.52,{fontSize:22,bold:true});
  texte(slide,'Guilhem · Paul\nPierre-Antoine · Théophile',7.23,3.41,4.92,1.26,
        {fontSize:24,breakLine:false,fit:'shrink'});
  ligne(slide,7.23,5.12,12.31,5.12,C.trait,0.9);
  texte(slide,'Démo et code : entreprise fictive Orbis Pay',7.23,5.39,5.08,0.38,
        {fontSize:12.9,color:C.violet,fit:'shrink'});
  texte(slide,'Voir le parcours et ses limites : docs/DEMO.md',0.68,6.45,12.0,0.36,
        {fontFace:'Courier New',fontSize:11.2,color:C.faible});
  slide.addNotes('Les secteurs fintech, santé, SaaS et marketplace sont des terrains de recherche, pas une validation commerciale. Les noms de prospects évoqués dans le cadrage ne figurent pas ici faute de preuve d’adoption d’agents et de contact commercial. Présenter les quatre membres de l’équipe sans attribuer de rôle non confirmé.');
}

pptx.writeFile({fileName:sortie}).then(()=>console.log(sortie));
