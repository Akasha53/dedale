// Mise en forme inerte d'une preuve avant affichage. Le backend neutralise
// déjà les champs piégés (préfixe « [leurre, neutralisé] », HTML échappé) ;
// la console va plus loin pour l'œil de l'analyste : liens désarmés, domaines
// coupés, secrets canaris masqués. Le texte reste rendu comme du texte par
// React, jamais comme du HTML, et aucun lien n'est cliquable.

const ENTITES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
  "&#39;": "'",
  "&#x2F;": "/",
};

// Décode les quelques entités qu'échappe le backend. Le résultat est rendu en
// nœud texte : décoder ne réveille rien.
export function decoderEntites(texte: string): string {
  return texte.replace(/&(amp|lt|gt|quot|#x27|#39|#x2F);/g, (m) => ENTITES[m] ?? m);
}

const PREFIXES = /^\s*\[(leurre|preuve), neutralisée?\]\s*/i;

// Retire le préfixe de neutralisation : la console l'affiche en étiquette.
export function sansPrefixe(texte: string): { texte: string; neutralise: boolean } {
  const neutralise = PREFIXES.test(texte);
  return { texte: texte.replace(PREFIXES, ""), neutralise };
}

// Coupe un domaine pour qu'il ne soit ni cliquable ni copiable tel quel.
function couperDomaine(hote: string): string {
  return hote.replace(/\./g, "[.]");
}

// Masque la valeur d'un secret : on garde le début pour l'identifier.
function masquer(valeur: string): string {
  if (valeur.length <= 6) return "••••";
  return `${valeur.slice(0, 4)}••••`;
}

// Hôtes internes de l'entreprise fictive : laissés lisibles.
const HOTES_INTERNES = new Set(["orbispay.example", "intranet.orbispay.example"]);

const CLES_SECRETES = /^(cle|cl[ée]|key|api_?key|token|jeton|secret|mdp|password|pwd)$/i;

function desarmerUrl(url: string): string {
  const m = /^(https?):\/\/([^/?#\s]+)([^\s]*)$/i.exec(url);
  if (!m) return url;
  const [, proto, hote, reste] = m;
  const resteMasque = reste.replace(/([?&])([^=&#\s]+)=([^&#\s]*)/g, (_t, sep, cle, val) =>
    CLES_SECRETES.test(cle) ? `${sep}${cle}=${masquer(val)}` : `${sep}${cle}=${val}`
  );
  return `${proto.toLowerCase() === "https" ? "hxxps" : "hxxp"}://${couperDomaine(hote)}${resteMasque}`;
}

// Forme inerte d'une preuve : entités décodées, image markdown décrite,
// liens désarmés, jetons canaris masqués, longueur bornée.
export function preuveInerte(brut: unknown, max = 320): string {
  if (brut == null) return "";
  let t = typeof brut === "string" ? brut : JSON.stringify(brut);
  t = sansPrefixe(decoderEntites(t)).texte;
  // ![alt](url) : une image markdown est le vecteur de sortie, on la décrit.
  t = t.replace(/!\[[^\]]*\]\(([^)\s]+)\)/g, (_m, url) => `[image → ${desarmerUrl(url)}]`);
  t = t.replace(/https?:\/\/[^\s)"'\]]+/gi, (url) => desarmerUrl(url));
  // Domaines nus (hors adresses mail et hôtes internes d'Orbis Pay) : coupés.
  t = t.replace(
    /(?<![@\w.[\]-])((?:[a-z0-9-]+\.)+(?:example|com|net|org|io|fr|ru|xyz|info|biz|co|app|dev))\b/gi,
    (d) => (HOTES_INTERNES.has(d.toLowerCase()) ? d : couperDomaine(d))
  );
  // Jetons canaris (faux secrets d'Orbis Pay) : jamais affichés en entier.
  t = t.replace(/\b([A-Z]{3,}-CANARY-[A-Z0-9]{4})-[A-Za-z0-9]+/g, "$1-••••");
  t = t.replace(/\s+/g, " ").trim();
  return t.length > max ? `${t.slice(0, max).trimEnd()} […]` : t;
}

// Domaine externe cité dans un constat de la passerelle, déjà coupé.
export function domaineExterne(texte: string): string | null {
  const m = /domaine externe\s+([a-z0-9.-]+\.[a-z]{2,})/i.exec(texte) ??
    /https?:\/\/([a-z0-9.-]+\.[a-z]{2,})/i.exec(texte);
  return m ? couperDomaine(m[1]) : null;
}

// Appel d'outil rendu comme une ligne de code inerte : outil(param="…").
export function appelInerte(outil: string, parametres: unknown, max = 360): string {
  const p = parametres && typeof parametres === "object" ? (parametres as Record<string, unknown>) : {};
  const morceaux = Object.entries(p).map(([k, v]) => {
    const val = typeof v === "string" ? `"${preuveInerte(v, 140)}"` : preuveInerte(v, 80);
    return `${k}=${val}`;
  });
  const t = `${outil}(${morceaux.join(", ")})`;
  return t.length > max ? `${t.slice(0, max).trimEnd()} […]` : t;
}
