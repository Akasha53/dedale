"use strict";
// Banc d'essai sAIfe : pilote la page. Tout passe par les endpoints du serveur du banc
// (/api/...), qui lancent les vraies commandes. Le jeton analyste reste côté serveur.

const $ = (s) => document.querySelector(s);
const ech = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function appel(methode, url) {
  try {
    const r = await fetch(url, { method: methode });
    return await r.json();
  } catch (e) {
    return { ok: false, message: "banc injoignable : " + e };
  }
}

const LIBELLE_CAS = {
  sosie: "Sosie du domaine",
  lien_menteur: "Lien menteur",
  piece_exe: "Pièce piégée (.exe)",
  piece_macro: "Macro piégée",
  fraude_president: "Fraude au président",
};
const LIBELLE_VERDICT = { sur: "sûr", suspect: "suspect", frauduleux: "frauduleux" };
const CLASSE_VERDICT = { sur: "autorise", suspect: "suspect", frauduleux: "retenu" };

// --- État des services + modèles + boutons mail ----------------------------------------
async function chargerEtat() {
  const d = await appel("GET", "/api/etat");
  if (!d || !d.services) return;

  const voyants = $("#voyants");
  voyants.innerHTML = Object.values(d.services).map((s) => `
    <div class="voyant">
      <span class="pastille ${s.debout ? "vert" : "rouge"}"></span>
      <span class="nom">${ech(s.nom)}</span>
      <span class="meta">:${s.port} · ${s.debout ? "en marche" : (s.lancable ? "arrêté" : "non lu")}</span>
    </div>`).join("");

  const p = d.app_mac || {};
  $("#poste").innerHTML = p.debout ? `
    <div class="voyant"><span class="pastille ${p.source === "reel" ? "vert" : "rouge"}"></span>
      <span class="nom">Config lue</span>
      <span class="meta">${p.source === "reel" ? "vraie config du poste" : "config " + ech(p.source)}</span></div>
    <div class="voyant"><span class="pastille vert"></span>
      <span class="nom">Serveurs MCP vus</span><span class="meta">${ech(p.serveurs)}</span></div>
    <div class="voyant"><span class="pastille ${p.risques ? "rouge" : "vert"}"></span>
      <span class="nom">À risque</span><span class="meta">${ech(p.risques)}</span></div>
    <div class="voyant"><span class="pastille ${p.soc === "connecte" ? "vert" : "rouge"}"></span>
      <span class="nom">Lien console SOC</span><span class="meta">${ech(p.soc)}</span></div>
  ` : `<div class="voyant"><span class="pastille rouge"></span>
      <span class="nom">App Mac</span><span class="meta">pas de réponse sur 8712</span></div>`;

  if (d.modeles && !$("#modele").dataset.pret) {
    $("#modele").innerHTML = d.modeles.map((m, i) =>
      `<option value="${ech(m)}" ${i === 0 ? "selected" : ""}>${ech(m)}</option>`).join("");
    $("#modele").dataset.pret = "1";
  }
  if (d.cas && !$("#mails").dataset.pret) {
    $("#mails").innerHTML = d.cas.map((c) =>
      `<button data-cas="${ech(c)}">${ech(LIBELLE_CAS[c] || c)}</button>`).join("");
    $("#mails").dataset.pret = "1";
    $("#mails").querySelectorAll("button").forEach((b) =>
      b.addEventListener("click", () => envoyerMail(b.dataset.cas, b)));
  }
}

// --- Démarrer tout ----------------------------------------------------------------------
$("#btn-demarrer").addEventListener("click", async () => {
  const b = $("#btn-demarrer");
  b.disabled = true;
  b.firstChild.textContent = " Démarrage en cours… ";
  await appel("POST", "/api/demarrer");
  b.firstChild.textContent = "Démarrer tout ";
  b.disabled = false;
  chargerEtat();
});
$("#btn-rafraichir").addEventListener("click", () => { chargerEtat(); chargerBoite(); chargerJournal(); });

// --- Mails de test ----------------------------------------------------------------------
async function envoyerMail(cas, bouton) {
  bouton.disabled = true;
  const out = $("#sortie-mail");
  out.classList.remove("vide");
  out.textContent = "Envoi de « " + (LIBELLE_CAS[cas] || cas) + " »…";
  const d = await appel("POST", "/api/mail?cas=" + encodeURIComponent(cas));
  out.textContent = (d.ok ? "Envoyé. " : "Échec. ") + (d.sortie || d.message || "");
  bouton.disabled = false;
  setTimeout(chargerBoite, 600);
}

// --- Boîte d'Orbis ----------------------------------------------------------------------
async function chargerBoite() {
  const d = await appel("GET", "/api/boite");
  const boite = $("#boite");
  const n = (d.mails || []).length;
  $("#etat-boite").textContent = n ? n + " mail" + (n > 1 ? "s" : "") : "vide";
  if (!n) {
    boite.innerHTML = `<div class="evt"><span class="d">La boîte est vide. Envoyez un mail de test.</span></div>`;
    return;
  }
  boite.innerHTML = d.mails.map((m) => {
    const v = m.verdict;
    const badge = v ? `<span class="badge ${CLASSE_VERDICT[v] || "neutre"}">${ech(LIBELLE_VERDICT[v] || v)}</span>`
                    : `<span class="badge neutre">en attente</span>`;
    return `<div class="evt mail"><span class="h">${badge}</span>
      <span><strong>${ech(m.objet)}</strong><br><span class="d">${ech(m.de)}</span></span></div>`;
  }).join("");
}

// --- Agent IA ---------------------------------------------------------------------------
let sondeAgent = null;
$("#btn-agent").addEventListener("click", async () => {
  const modele = $("#modele").value;
  const essais = $("#essais").value;
  const b = $("#btn-agent");
  b.disabled = true;
  const d = await appel("POST", `/api/agent?modele=${encodeURIComponent(modele)}&essais=${essais}`);
  if (!d.ok) {
    $("#etat-agent").textContent = d.message || "refus";
    b.disabled = false;
    return;
  }
  if (sondeAgent) clearInterval(sondeAgent);
  sondeAgent = setInterval(sonderAgent, 1500);
  sonderAgent();
});

function rendreLignes(lignes) {
  return lignes.map((l) => {
    let cl = "";
    if (/retenu|RETENU/.test(l)) cl = "retenu";
    else if (/coupé|coupe=True|COUPÉ|couper/.test(l)) cl = "coupe";
    return `<span class="${cl}">${ech(l)}</span>`;
  }).join("\n");
}

async function sonderAgent() {
  const d = await appel("GET", "/api/agent/flux");
  const flux = $("#flux-agent");
  if (d.lignes && d.lignes.length) {
    flux.classList.remove("vide");
    flux.innerHTML = rendreLignes(d.lignes);
    flux.scrollTop = flux.scrollHeight;
  }
  const libelle = { en_cours: "en cours", fini: "terminé", erreur: "erreur", repos: "" }[d.etat] || "";
  $("#etat-agent").textContent = d.modele ? `modèle ${d.modele} · ${libelle}` : "";
  if (!d.en_cours) {
    if (sondeAgent) { clearInterval(sondeAgent); sondeAgent = null; }
    $("#btn-agent").disabled = false;
    chargerJournal();
  }
}

// --- Virements --------------------------------------------------------------------------
async function virement(genre, bouton) {
  bouton.disabled = true;
  const out = $("#sortie-virement");
  out.classList.remove("vide");
  out.textContent = "Envoi au bouclier…";
  const d = await appel("POST", "/api/virement?genre=" + genre);
  out.textContent = genre === "rib"
    ? "RIB changé → l'app Mac doit afficher « Retenu ». Réponse " + (d.code || "?") + " : " + (d.reponse || "")
    : "Virement habituel → rien ne s'affiche, c'est normal. Réponse " + (d.code || "?") + " : " + (d.reponse || "");
  bouton.disabled = false;
}
$("#vir-normal").addEventListener("click", (e) => virement("normal", e.currentTarget));
$("#vir-rib").addEventListener("click", (e) => virement("rib", e.currentTarget));

// --- Repartir propre --------------------------------------------------------------------
$("#btn-repartir").addEventListener("click", async (e) => {
  const b = e.currentTarget;
  if (!confirm("Sauvegarder la base puis repartir d'une base vide ? Le backend redémarre.")) return;
  b.disabled = true;
  const out = $("#sortie-repartir");
  out.classList.remove("vide");
  out.textContent = "Sauvegarde et relance du backend…";
  const d = await appel("POST", "/api/repartir");
  out.textContent = (d.message || "") + (d.sauvegarde ? "\nSauvegarde : " + d.sauvegarde : "");
  b.disabled = false;
  chargerEtat(); chargerJournal();
});

// --- Journal ----------------------------------------------------------------------------
async function chargerJournal() {
  const d = await appel("GET", "/api/journal");
  const back = $("#journal-backend");
  const inc = (d.incidents || []).slice(0, 6).map((i) =>
    `<div class="evt"><span class="h"><span class="badge ouvert">${ech(i.statut || "")}</span></span>
      <span><strong>${ech(i.id)}</strong> — ${ech(i.titre || i.type)}<br>
      <span class="d">${ech(i.source)} · ${ech(i.gravite || "")}</span></span></div>`).join("");
  const act = (d.activite || []).slice(0, 8).map((a) => {
    const cl = a.verdict === "retenu" ? "retenu" : (a.verdict === "autorise" ? "autorise" : "neutre");
    return `<div class="evt"><span class="h"><span class="badge ${cl}">${ech(a.verdict || "")}</span></span>
      <span>${ech(a.outil || "")} <span class="d">${ech(a.raison || "")}</span></span></div>`;
  }).join("");
  back.innerHTML = (inc + act) || `<div class="evt"><span class="d">Rien pour l'instant.</span></div>`;

  $("#journal-actions").innerHTML = (d.actions || []).map((a) =>
    `<div class="evt"><span class="h">${ech(a.heure)}</span>
      <span><strong>${ech(a.texte)}</strong>${a.detail ? `<br><span class="d">${ech(a.detail)}</span>` : ""}</span></div>`
  ).join("") || `<div class="evt"><span class="d">Aucune action encore.</span></div>`;

  $("#note-jeton").textContent = d.jeton_present
    ? "Le banc parle au backend avec le jeton analyste, lu côté serveur."
    : "Jeton analyste introuvable : le journal du backend restera vide.";
  $("#note-jeton").className = d.jeton_present ? "note" : "note alerte";
}

// --- Boucles ----------------------------------------------------------------------------
chargerEtat(); chargerBoite(); chargerJournal();
setInterval(chargerEtat, 5000);
setInterval(chargerBoite, 3500);
setInterval(chargerJournal, 3500);
