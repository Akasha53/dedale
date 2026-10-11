// Page de repli : compte à rebours visible, puis fermeture de l'onglet. Un
// navigateur refuse souvent de fermer un onglet qu'un script n'a pas ouvert :
// dans ce cas, on montre le bouton « Fermer » et le message de repli.

const $ = (sel) => document.getElementById(sel);
const reste = $("reste");
let n = 3;

function fermer() {
  window.__saifeFermetureTentee = true;
  window.close();
  // Si l'onglet est toujours là une fraction de seconde plus tard, la fermeture a
  // été refusée : on bascule sur le repli manuel.
  setTimeout(() => { $("repli").hidden = false; }, 250);
}

const minuterie = setInterval(() => {
  n -= 1;
  reste.textContent = String(Math.max(0, n));
  if (n <= 0) {
    clearInterval(minuterie);
    fermer();
  }
}, 1000);

$("fermer").addEventListener("click", () => window.close());
