// Fenêtre de l'icône : compteur des sites louches évités, dernier envoi au backend et
// dernier lien raccourci ouvert.

const $ = (sel) => document.getElementById(sel);

function heure(ms) {
  return new Date(ms).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
}

function etatSignalement(etat) {
  if (etat === "recu") return ["reçu par Dédale", "ok"];
  if (etat === "injoignable") return ["Dédale ne répond pas", "ko"];
  const code = String(etat).replace("refuse_", "");
  return [`refusé par Dédale (code ${code})`, "ko"];
}

async function afficher() {
  const e = await chrome.runtime.sendMessage({ type: "etat" }).catch(() => null);
  if (!e) return;

  $("evites").textContent = String(e.evites);
  $("libelle").textContent = e.evites > 1 ? "sites louches évités" : "site louche évité";
  $("passes").textContent = e.passes === 0
    ? "Aucun avertissement ignoré."
    : e.passes === 1 ? "1 avertissement ignoré." : `${e.passes} avertissements ignorés.`;

  const s = e.dernierSignalement;
  if (s) {
    const [texte, classe] = etatSignalement(s.etat);
    const zone = $("signalement");
    zone.replaceChildren(
      `Dernier signalement (${heure(s.heure)}) : `,
      Object.assign(document.createElement("span"), { className: classe, textContent: texte }),
      ".",
    );
    zone.hidden = false;
  }
  afficherRaccourci(e.dernierRaccourci);
}

function afficherRaccourci(r) {
  if (!r) return;
  const zone = $("raccourci");
  zone.textContent = `Lien raccourci (${r.domaine}, ${heure(r.heure)}) : sa destination n'apparaît `
    + "qu'après la redirection, et Dédale l'examine à ce moment-là.";
  zone.hidden = false;
}

$("reglages").addEventListener("click", () => chrome.runtime.openOptionsPage());
afficher();
