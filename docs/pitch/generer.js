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

// 1. Problème
{
  const slide = pptx.addSlide();
  titre(slide,1,'Dédale  /  Le problème','Un salarié sur trois échoue encore aux tests de phishing','Et les agents IA lisent déjà les mêmes boîtes mail, avec des droits.');
  bloc(slide,0.67,2.17,4.28,3.92,{fond:C.panneau2,bord:C.cyan});
  texte(slide,'33,1 %',0.95,2.48,3.7,1.0,{fontSize:58,bold:true,color:C.cyan});
  texte(slide,'des personnes interagissent avec une simulation de phishing avant toute formation.',
        0.99,3.51,3.62,1.29,{fontSize:18,fit:'shrink'});
  ligne(slide,0.98,5.03,4.62,5.03,C.trait,0.8);
  texte(slide,'67 M de tests · plus de 62 000 organisations',0.98,5.18,3.65,0.39,
        {fontFace:'Courier New',fontSize:10.2,color:C.doux,fit:'shrink'});
  capture(slide,'landing/img/gen/mail-garde.png',5.26,2.18,7.39,4.16);
  texte(slide,'Source : KnowBe4, Phishing by Industry Benchmarking Report 2025. Chiffre hors Dédale ; image d’illustration.',
        0.68,6.55,11.9,0.35,{fontSize:10.4,color:C.faible,fit:'shrink',
          hyperlink:{url:'https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report'}});
  slide.addNotes('Ouvrir sur la faille humaine. KnowBe4 2025 : 33,1 % de taux initial (Phish-prone Percentage) sur environ 67 millions de tests simulés. Ce n’est pas la part de salariés qui cliquent sur de vrais mails frauduleux, et ce n’est pas une mesure de Dédale. Le taux tombe autour de 4 % après un an de formation : la formation aide, elle ne suffit pas. Source : https://www.knowbe4.com/resources/reports/2025-phishing-by-industry-benchmarking-report');
}

// 2. L'angle
{
  const slide = pptx.addSlide();
  titre(slide,2,'L’angle','La faille, c’est celui qui clique','Dans une entreprise, deux maillons lisent, cliquent et agissent.');
  bloc(slide,0.68,2.15,5.89,3.55,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.15,5.89,3.55,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'SALARIÉS',0.97,2.48,1.7,C.cyan);
  etiquette(slide,'AGENTS IA',7.05,2.48,1.85,C.violet);
  texte(slide,'Un mail de phishing',0.98,3.08,5.2,0.52,{fontSize:23,bold:true});
  texte(slide,'Un faux expéditeur, un lien piégé, et la personne clique.',
        0.98,3.8,4.95,1.2,{fontSize:18,color:C.doux,fit:'shrink'});
  texte(slide,'Une instruction cachée',7.06,3.08,5.2,0.52,{fontSize:23,bold:true});
  texte(slide,'Dans un mail ou dans la description d’un outil, et l’agent agit.',
        7.06,3.8,4.95,1.2,{fontSize:18,color:C.doux,fit:'shrink'});
  texte(slide,'Même faille, deux visages. Personne ne surveille les deux ensemble.',
        0.68,6.0,12.0,0.45,{fontSize:18,bold:true,color:C.blanc,fit:'shrink'});
  slide.addNotes('Un pare-feu protège les tuyaux ; Dédale protège ceux qui décident d’ouvrir. Phrase à dire : Dédale est le rempart entre l’extérieur et les deux seuls maillons qui, dans une entreprise, cliquent, lisent et agissent : vos salariés et vos agents IA. Référentiel pour l’agent : Top 10 OWASP des applications agentiques (empoisonnement d’outils).');
}

// 3. La solution
{
  const slide = pptx.addSlide();
  titre(slide,3,'La solution','Un garde du corps, une seconde avant le geste','Dédale tourne en local, sur chaque poste et chaque agent.');
  const lignes = [
    ['01','Il repère le geste à risque : mail frauduleux, lien piégé, outil empoisonné.'],
    ['02','Il le retient avant qu’il parte.'],
    ['03','La personne tranche : annuler ou continuer.'],
    ['04','La SOC voit tout dans une seule console.'],
  ];
  lignes.forEach((l,i)=>{
    texte(slide,l[0],0.72,2.3+i*1.0,0.6,0.5,{fontFace:'Courier New',fontSize:15,color:i%2?C.violet:C.cyan,bold:true});
    texte(slide,l[1],1.4,2.2+i*1.0,4.7,0.75,{fontSize:17.5,fit:'shrink'});
  });
  capture(slide,'landing/img/gen/salarie-garde.png',6.45,2.18,6.2,3.49,'Image d’illustration');
  texte(slide,'Un pare-feu protège les tuyaux. Dédale protège ceux qui décident d’ouvrir.',
        0.68,6.35,12.0,0.4,{fontSize:15,color:C.doux,fit:'shrink'});
  slide.addNotes('Le garde du poste ne coupe jamais le poste du salarié : il avertit, la personne choisit. Pour l’agent, c’est l’appel d’outil qui est retenu.');
}

// 4. Le même moteur
{
  const slide = pptx.addSlide();
  titre(slide,4,'Le même moteur','Un seul moteur pour l’humain et pour l’agent','Chaque incident suit la même chaîne, du signal à l’export.');
  const cartes = [
    {n:'01',t:'Détecter',d:'Le geste à risque, au poste ou à la passerelle de l’agent.',c:C.cyan},
    {n:'02',t:'Boîte noire',d:'Source, consigne, outil appelé, décision, résultat.',c:C.violet},
    {n:'03',t:'L’humain tranche',d:'Le salarié ou l’analyste SOC choisit. Rien ne se bloque tout seul.',c:C.cyan},
    {n:'04',t:'NIS2 et SIEM',d:'Brouillon de notification et export ECS / Sigma.',c:C.violet},
  ];
  cartes.forEach((o,i)=>{
    const x=0.68+i*3.07;
    bloc(slide,x,2.39,2.8,3.26,{fond:C.panneau2,bord:o.c});
    texte(slide,o.n,x+0.22,2.68,0.65,0.43,{fontFace:'Courier New',fontSize:16.5,color:o.c,bold:true});
    texte(slide,o.t,x+0.22,3.29,2.5,0.44,{fontSize:20,bold:true,fit:'shrink'});
    ligne(slide,x+0.22,3.9,x+2.58,3.9,C.trait,0.9);
    texte(slide,o.d,x+0.22,4.13,2.36,1.2,{fontSize:15.1,color:C.doux,fit:'shrink'});
  });
  texte(slide,'Le brouillon NIS2 est à relire : ce n’est ni une qualification juridique ni une notification envoyée.',
        0.68,6.15,12.0,0.4,{fontSize:13.2,color:C.faible,fit:'shrink'});
  slide.addNotes('Référentiels de lecture, sans prétendre à une certification : NIST CSF 2.0 (Détecter, Répondre), MITRE ATT&CK et ATLAS, OWASP agentique. Aucun taux du banc synthétique n’est annoncé comme performance produit.');
}

// 5. La démo
{
  const slide = pptx.addSlide();
  titre(slide,5,'La démo','Ce que vous allez voir en direct','Une commande, trois minutes, hors ligne.');
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
  slide.addNotes('Lancer ./lancer.sh puis ./demo.sh. Pour voir un incident côté salarié, choisir continuer. Dans la console, ouvrir l’incident de l’agent et décider couper. Dire clairement : une tentative retenue n’est pas une fuite réussie, et nous ne revendiquons aucun taux de réussite d’attaque sur des modèles réels.');
}

// 6. Déploiement
{
  const slide = pptx.addSlide();
  titre(slide,6,'Déploiement','Rien ne sort de l’entreprise','La cible produit d’un côté, ce qui tourne aujourd’hui de l’autre.');
  bloc(slide,0.68,2.19,5.91,3.96,{fond:C.panneau2,bord:C.cyan});
  bloc(slide,6.77,2.19,5.89,3.96,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'CIBLE PRODUIT',0.98,2.49,2.55,C.cyan);
  etiquette(slide,'PROTOTYPE AUJOURD’HUI',7.07,2.49,3.1,C.violet);
  const futur=[
    'Une appli de poste, discrète, en arrière-plan',
    'Un serveur sur site : les données restent chez le client',
    'Un tableau de bord pour la SOC',
  ];
  const actuel=[
    'Gestes salariés simulés, pop-up d\u2019avertissement',
    'Agent scripté, passerelle et outils locaux',
    'Console SOC, boîte noire, exports',
  ];
  futur.forEach((t,i)=>{
    texte(slide,`${i+1}.`,0.99,3.22+i*0.77,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.cyan});
    texte(slide,t,1.48,3.16+i*0.77,4.77,0.58,{fontSize:16.0,fit:'shrink'});
  });
  actuel.forEach((t,i)=>{
    texte(slide,`${i+1}.`,7.08,3.22+i*0.77,0.42,0.39,{fontFace:'Courier New',fontSize:14,color:C.violet});
    texte(slide,t,7.57,3.16+i*0.77,4.72,0.58,{fontSize:16.0,fit:'shrink'});
  });
  texte(slide,'Pas de surveillance native du Mac ni de connexion Outlook ou Gmail dans cette démo.',
        0.68,6.45,12.0,0.37,{fontSize:12.3,color:C.faible,fit:'shrink'});
  slide.addNotes('Distinguer à voix haute ce qui est livré et ce qui est visé. Les intégrations messagerie et navigateur, la gestion des identités et la rétention viennent après le hackathon.');
}

// 7. Marché et modèle
{
  const slide = pptx.addSlide();
  titre(slide,7,'Marché et modèle','Des entreprises à la fois nombreuses et outillées en agents','Hypothèses à valider, pas des clients.');
  bloc(slide,0.68,2.19,3.9,3.96,{fond:C.panneau2,bord:C.cyan});
  etiquette(slide,'CLIENT IDÉAL',0.98,2.49,1.95,C.cyan);
  texte(slide,'Beaucoup de salariés, des agents IA déjà en production, des données sensibles.',
        0.98,3.1,3.3,1.7,{fontSize:16.5,fit:'shrink'});
  texte(slide,'Soumis à NIS2, DORA ou l’AI Act.',0.98,5.05,3.3,0.6,{fontSize:13.5,color:C.cyan,fit:'shrink'});
  bloc(slide,4.72,2.19,4.1,3.96,{fond:C.panneau2,bord:C.violet});
  etiquette(slide,'5 COMPTES À VÉRIFIER',5.02,2.49,2.75,C.violet);
  ['Revolut','Qonto','Doctolib','Alan','Back Market'].forEach((n,i)=>{
    texte(slide,n,5.02,3.1+i*0.52,3.5,0.4,{fontSize:18,bold:i===0});
  });
  texte(slide,'Adoption réelle d’agents non confirmée.',5.02,5.75,3.6,0.3,{fontSize:11.5,color:C.violet,fit:'shrink'});
  bloc(slide,8.96,2.19,3.7,3.96,{fond:C.panneau2,bord:C.cyan});
  etiquette(slide,'PRIX (HYPOTHÈSE)',9.26,2.49,2.4,C.cyan);
  texte(slide,'5 à 30 €',9.26,3.2,3.2,0.9,{fontSize:38,bold:true,color:C.cyan,fit:'shrink'});
  texte(slide,'par utilisateur et par mois, selon que l’entreprise ajoute la supervision des agents.',
        9.26,4.2,3.1,1.4,{fontSize:15,color:C.doux,fit:'shrink'});
  texte(slide,'Aucun de ces comptes n’est client, ni même contacté. À éviter en premier client : les spécialistes d’infra, qui le font en interne.',
        0.68,6.38,12.0,0.5,{fontSize:12,color:C.faible,fit:'shrink'});
  slide.addNotes('Volet mails : presque toutes les grandes entreprises. Volet agents, plus cher : fintech, SaaS, santé, marketplaces. Les cinq noms sont des candidats plausibles, pas une validation commerciale. La fourchette 5 à 30 euros est un ordre de grandeur à tester, pas une grille tarifaire.');
}

// 8. Équipe
{
  const slide = pptx.addSlide();
  titre(slide,8,'Équipe','Quatre personnes, un week-end','Secure Horizons, Track 2.');
  const gens=[
    ['Guilhem','Capteurs, passerelle, boîte noire',C.cyan],
    ['Paul','Scénario, modèle économique, pitch',C.violet],
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
  slide.addNotes('Rôles de Pierre-Antoine et de Théophile à confirmer par eux avant dimanche 12 h ; ne rien écrire qu’ils n’ont pas validé.');
}

pptx.writeFile({fileName:sortie}).then(()=>console.log(sortie));
