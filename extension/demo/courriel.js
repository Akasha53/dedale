// Lanceur de la démonstration. En ouvrant cette page, le mode démonstration
// s'arme tout seul : le service worker interceptera le clic sur le lien piégé.
// Le lien reste désactivé tant que le mode n'est pas confirmé armé.

const etat = document.getElementById("etat");
const piege = document.getElementById("piege");

piege.addEventListener("click", (ev) => {
  if (piege.dataset.pret !== "1") ev.preventDefault();
});

chrome.storage.local.set({ demo: true }).then(() => {
  piege.dataset.pret = "1";
  etat.textContent = "Mode démonstration actif. Cliquez « Confirmer mon compte ».";
}).catch(() => {
  etat.textContent = "Activez le mode démonstration dans les réglages de l'extension.";
});
