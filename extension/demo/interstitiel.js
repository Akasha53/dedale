// Interstitiel de démonstration. Le domaine visé arrive dans le fragment d'URL,
// posé par le service worker. Les deux boutons mènent à des pages servies par
// l'extension : rien ne sort du navigateur, aucune adresse réelle n'est ouverte.

const domaine = decodeURIComponent(location.hash.slice(1));
const $ = (sel) => document.getElementById(sel);

if (domaine) {
  $("domaine").textContent = domaine;
  document.title = `Lien piégé arrêté : ${domaine} — sAIfe`;
}

$("arreter").addEventListener("click", () => location.replace("bloquee.html"));
$("continuer").addEventListener("click", () => location.replace("faux-orbis.html"));

// Le clavier arrive sur l'action sûre, même si l'autofocus n'a pas pris.
$("arreter").focus();
