// Page d'avertissement : affichée à la place d'un site louche.
// Les textes viennent du service worker et passent par textContent, jamais par innerHTML.

const id = decodeURIComponent(location.hash.slice(1));
const $ = (sel) => document.getElementById(sel);

function envoyer(message) {
  return chrome.runtime.sendMessage(message).catch(() => null);
}

async function revenir() {
  const historique = history.length > 1;
  await envoyer({ type: "revenir", id, historique });
  if (historique) history.back();
}

async function continuer() {
  $("continuer").disabled = true;
  const rep = await envoyer({ type: "continuer", id });
  if (rep?.url) location.replace(rep.url);
  else $("continuer").disabled = false;
}

// « d'Orbis Pay », mais « de Banque Exemple ».
function de(nom) {
  return /^[aeiouyhàâäéèêëîïôöûü]/i.test(nom) ? `d'${nom}` : `de ${nom}`;
}

function afficherExpire() {
  $("titre-imite").textContent = "Cet avertissement a expiré.";
  $("titre-suite").textContent = "Rouvrez le lien pour que sAIfe vérifie l'adresse.";
  $("adresses").hidden = true;
  $("raison").hidden = true;
  $("continuer").hidden = true;
  $("note").hidden = true;
}

async function remplir() {
  const a = id ? await envoyer({ type: "avertissement", id }) : null;
  if (!a?.trouve) return afficherExpire();

  $("titre-imite").textContent = a.titre;
  $("titre-suite").textContent = a.suite;
  $("domaine").textContent = a.affiche;
  if (a.affiche !== a.domaine) {
    $("reel").textContent = `Adresse réelle : ${a.domaine}`;
    $("reel").hidden = false;
  }
  if (a.imite) $("vrai").textContent = a.imite;
  else $("ligne-vrai").hidden = true;
  $("raison").textContent = a.explication;
  $("note").textContent =
    `Si vous continuez, l'équipe sécurité ${de(a.nom)} reçoit le nom de ce site. Rien d'autre ne sort de votre navigateur.`;
  document.title = `Avertissement : ${a.affiche}`;
}

$("revenir").addEventListener("click", revenir);
$("continuer").addEventListener("click", continuer);
remplir();
