// Page d'options : nom affiché, domaines de confiance, adresse du backend.

import { analyser, titres } from "./comparateur.js";
import {
  adresseBackend, backendLocal, ecrireReglages, lireListeDomaines, lireReglages, motifOrigine,
} from "./reglages.js";

const $ = (sel) => document.getElementById(sel);
let regles = null;

function statut(texte, erreur = false) {
  $("statut").textContent = texte;
  $("statut").classList.toggle("ko", erreur);
}

async function charger() {
  regles = await fetch(chrome.runtime.getURL("regles-sites.json")).then((r) => r.json()).catch(() => null);
  const r = await lireReglages();
  $("nom").value = r.nom;
  $("domaines").value = r.domaines.join("\n");
  $("backend").value = r.backend;
  tester();
  compteur();
}

async function enregistrer(ev) {
  ev.preventDefault();
  const backend = adresseBackend($("backend").value);
  if (!backend) {
    statut("Adresse du backend invalide : elle doit commencer par http:// ou https://.", true);
    return;
  }
  const { domaines, rejetes } = lireListeDomaines($("domaines").value);

  // Un backend hors de cette machine demande l'accord de Chrome. La demande doit
  // partir du clic, avant tout appel asynchrone.
  let accesRefuse = false;
  if (!backendLocal(backend)) {
    const origine = motifOrigine(backend);
    accesRefuse = !(await chrome.permissions.request({ origins: [origine] }).catch(() => false));
  }

  const r = await ecrireReglages({ nom: $("nom").value, domaines, backend });
  $("nom").value = r.nom;
  $("domaines").value = r.domaines.join("\n");
  $("backend").value = r.backend;

  const notes = ["Enregistré."];
  if (rejetes.length) notes.push(`Lignes ignorées : ${rejetes.join(", ")}.`);
  if (!r.domaines.length) notes.push("La liste est vide : aucun site ne sera signalé.");
  if (accesRefuse) notes.push("Chrome n'a pas donné accès à ce backend : les signalements n'y arriveront pas.");
  statut(notes.join(" "), accesRefuse || !r.domaines.length);
  tester();
}

function tester() {
  const zone = $("resultat");
  const saisie = $("essai").value.trim();
  zone.className = "resultat";
  if (!saisie || !regles) { zone.replaceChildren(); return; }

  const { domaines } = lireListeDomaines($("domaines").value);
  const r = analyser(saisie, regles, { nom: $("nom").value.trim() || "Orbis Pay", domaines });
  const verdict = document.createElement("span");
  verdict.className = "verdict";
  const lignes = [verdict];

  if (r.verdict === "louche") {
    verdict.textContent = titres(r, regles).titre;
    const pourquoi = document.createElement("span");
    pourquoi.className = "explication";
    pourquoi.textContent = r.explication;
    lignes.push(pourquoi);
  } else if (r.verdict === "raccourci") {
    verdict.textContent = "Lien raccourci.";
    const pourquoi = document.createElement("span");
    pourquoi.className = "explication";
    pourquoi.textContent = r.explication;
    lignes.push(pourquoi);
  } else if (r.verdict === "confiance") {
    verdict.textContent = r.marque ? `Site officiel : ${r.marque}.` : "Domaine de confiance.";
  } else {
    verdict.textContent = r.domaine ? "Rien à signaler pour ce domaine." : "Adresse illisible.";
  }
  zone.classList.add(r.verdict);
  zone.replaceChildren(...lignes);
}

async function compteur() {
  const e = await chrome.runtime.sendMessage({ type: "etat" }).catch(() => null);
  if (!e) return;
  const evites = e.evites > 1 ? `${e.evites} sites louches évités` : `${e.evites} site louche évité`;
  const passes = e.passes > 1 ? `${e.passes} avertissements ignorés` : `${e.passes} avertissement ignoré`;
  $("compteur").textContent = `${evites}, ${passes}.`;
}

$("formulaire").addEventListener("submit", enregistrer);
$("essai").addEventListener("input", tester);
$("domaines").addEventListener("input", tester);
$("zero").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "remise_a_zero" }).catch(() => null);
  compteur();
});
charger();
