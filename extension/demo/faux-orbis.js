// Sosie d'Orbis Pay de démonstration : la page est inerte. Le formulaire n'a pas
// d'action, rien n'est soumis, rien n'est stocké. « Se connecter » montre seulement
// ce qu'un vrai site d'hameçonnage ferait de ce que vous tapez.

const form = document.getElementById("form");
const note = document.getElementById("note");

form.addEventListener("submit", (ev) => {
  ev.preventDefault();
  note.hidden = false;
  note.scrollIntoView({ block: "nearest", behavior: "smooth" });
});
