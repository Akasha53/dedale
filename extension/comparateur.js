// Comparateur de domaines : dit si un nom d'hôte imite un domaine de confiance.
//
// Module pur, sans API Chrome : le service worker l'importe, et les tests le
// font tourner sous Node (`node --test tests/`). Il ne voit que le nom d'hôte,
// jamais le chemin, la requête ou le contenu de la page.
//
// Verdicts :
//   « confiance » : le domaine est dans la liste, ou en est un sous-domaine ;
//   « sosie »     : il ressemble à un domaine de confiance sans en être un ;
//   « neutre »    : aucun rapport avec la liste.
//
// Heuristique assumée : une liste statique et cinq règles (autre extension,
// alphabet étranger ou caractères confusables, tiret ajouté, une ou deux lettres
// d'écart, nom de confiance glissé dans un autre domaine). Elle ne connaît pas la
// réputation d'un site et ne remplace pas la navigation sécurisée du navigateur.

export const NOM_PAR_DEFAUT = "Orbis Pay";
export const DOMAINES_PAR_DEFAUT = ["orbispay.example"];

// Suffixes publics à deux niveaux les plus courants. Sans la liste complète des
// suffixes publics, « orbispay.co.uk » serait lu comme le domaine « co.uk ».
const SUFFIXES_DOUBLES = new Set([
  "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk",
  "com.au", "net.au", "org.au",
  "co.nz", "co.jp", "co.kr", "co.in", "co.za", "co.il",
  "com.br", "com.cn", "com.mx", "com.tr", "com.sg", "com.hk",
  "gouv.fr", "asso.fr",
]);

// Lettres d'autres alphabets qui s'affichent comme des lettres latines.
const CONFUSABLES = {
  // cyrillique
  "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h",
  "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "ѕ": "s",
  "і": "i", "ї": "i", "ј": "j", "ԁ": "d", "һ": "h", "ӏ": "l", "ԛ": "q",
  "ԝ": "w", "ɡ": "g", "ո": "n", "ս": "u",
  // grec
  "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o",
  "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ω": "w",
  // latin étendu sans décomposition Unicode
  "ı": "i", "ł": "l", "ø": "o", "đ": "d", "ħ": "h",
};

// Rapprochements visuels dans l'alphabet latin, appliqués des deux côtés de la
// comparaison : « 0rbispay » et « orbispay » ont alors le même squelette.
const SEQUENCES = [["rn", "m"], ["vv", "w"], ["cl", "d"]];
const CHIFFRES_ET_LETTRES = { "0": "o", "1": "l", "i": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b" };

// ---------------------------------------------------------------- punycode
// Décodage RFC 3492, réduit au nécessaire : un libellé « xn--… » vers Unicode.

const BASE = 36, TMIN = 1, TMAX = 26, SKEW = 38, DAMP = 700, BIAS0 = 72, N0 = 128;

function adapter(delta, nbPoints, premier) {
  delta = premier ? Math.floor(delta / DAMP) : delta >> 1;
  delta += Math.floor(delta / nbPoints);
  let k = 0;
  while (delta > ((BASE - TMIN) * TMAX) >> 1) {
    delta = Math.floor(delta / (BASE - TMIN));
    k += BASE;
  }
  return k + Math.floor(((BASE - TMIN + 1) * delta) / (delta + SKEW));
}

function valeurChiffre(c) {
  if (c >= 48 && c <= 57) return c - 22;   // 0-9 → 26-35
  if (c >= 65 && c <= 90) return c - 65;   // A-Z
  if (c >= 97 && c <= 122) return c - 97;  // a-z
  return BASE;
}

/** Décode la partie qui suit « xn-- ». Renvoie null si l'entrée est invalide. */
export function decoderPunycode(entree) {
  const sortie = [];
  const delim = entree.lastIndexOf("-");
  for (let j = 0; j < Math.max(delim, 0); j++) {
    if (entree.charCodeAt(j) >= 0x80) return null;
    sortie.push(entree.charCodeAt(j));
  }
  let n = N0, biais = BIAS0, i = 0;
  for (let idx = delim > 0 ? delim + 1 : 0; idx < entree.length;) {
    const ancienI = i;
    for (let w = 1, k = BASE; ; k += BASE) {
      if (idx >= entree.length) return null;
      const chiffre = valeurChiffre(entree.charCodeAt(idx++));
      if (chiffre >= BASE) return null;
      i += chiffre * w;
      const t = k <= biais ? TMIN : k >= biais + TMAX ? TMAX : k - biais;
      if (chiffre < t) break;
      w *= BASE - t;
    }
    biais = adapter(i - ancienI, sortie.length + 1, ancienI === 0);
    n += Math.floor(i / (sortie.length + 1));
    i %= sortie.length + 1;
    if (n > 0x10ffff) return null;
    sortie.splice(i++, 0, n);
  }
  return String.fromCodePoint(...sortie);
}

/** Libellé lisible : « xn--rbispay-2og » devient « оrbispay » (o cyrillique). */
export function libelleUnicode(libelle) {
  if (!libelle.startsWith("xn--")) return libelle;
  return decoderPunycode(libelle.slice(4)) ?? libelle;
}

// ---------------------------------------------------------------- outils

/**
 * Nom d'hôte nettoyé, ou "" si illisible. Le parseur d'URL standard met en
 * minuscules, retire le port et le chemin, et convertit un nom Unicode en
 * punycode, comme le fait Chrome avant de le passer à l'extension.
 */
export function normaliserHote(entree) {
  const brut = String(entree ?? "").trim();
  if (!brut) return "";
  try {
    const url = new URL(brut.includes("://") ? brut : `http://${brut}`);
    return url.hostname.toLowerCase().replace(/\.+$/, "");
  } catch {
    return "";
  }
}

function estAdresseIP(hote) {
  return hote.startsWith("[") || /^\d{1,3}(\.\d{1,3}){3}$/.test(hote);
}

/** Sépare « a.b.orbispay.co.uk » en { nom: "orbispay", suffixe: "co.uk", sous: ["a","b"] }. */
export function decouper(hote) {
  const e = hote.split(".");
  if (e.length < 2) return { nom: "", suffixe: e[0] ?? "", sous: [] };
  const deux = e.slice(-2).join(".");
  if (e.length >= 3 && SUFFIXES_DOUBLES.has(deux)) {
    return { nom: e[e.length - 3], suffixe: deux, sous: e.slice(0, -3) };
  }
  return { nom: e[e.length - 2], suffixe: e[e.length - 1], sous: e.slice(0, -2) };
}

/** Squelette visuel : ce que l'œil lit, une fois les déguisements retirés. */
export function squelette(texte) {
  let s = texte.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  s = Array.from(s, (c) => CONFUSABLES[c] ?? c).join("");
  for (const [de, vers] of SEQUENCES) s = s.split(de).join(vers);
  s = Array.from(s, (c) => CHIFFRES_ET_LETTRES[c] ?? c).join("");
  return s.replace(/[-_]/g, "");
}

/** Distance de Damerau-Levenshtein restreinte (une inversion de deux lettres compte pour 1). */
export function distance(a, b) {
  const A = Array.from(a), B = Array.from(b);
  const d = Array.from({ length: A.length + 1 }, (_, i) => [i, ...new Array(B.length).fill(0)]);
  for (let j = 1; j <= B.length; j++) d[0][j] = j;
  for (let i = 1; i <= A.length; i++) {
    for (let j = 1; j <= B.length; j++) {
      const cout = A[i - 1] === B[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cout);
      if (i > 1 && j > 1 && A[i - 1] === B[j - 2] && A[i - 2] === B[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[A.length][B.length];
}

/** Écart toléré selon la longueur du nom : rien sous 5 lettres, 1 jusqu'à 9, 2 au-delà. */
export function seuil(nom) {
  const n = Array.from(nom).length;
  if (n < 5) return 0;
  return n < 10 ? 1 : 2;
}

function lettres(n) {
  return n === 1 ? "d'une seule lettre" : `de ${n} lettres`;
}

// ---------------------------------------------------------------- analyse

function confiance(hote, domaines) {
  return domaines.find((t) => hote === t || hote.endsWith("." + t)) ?? null;
}

function comparerA(hote, unicode, cible) {
  const vrai = decouper(cible);
  const marque = vrai.nom;
  if (!marque) return null;
  const sq = squelette(marque);
  const lu = decouper(hote);
  const nomUni = libelleUnicode(lu.nom);
  const proprietaire = lu.suffixe ? `${lu.nom}.${lu.suffixe}` : lu.nom;
  const resultat = (raison, explication) => ({ raison, explication, imite: cible });

  if (lu.nom) {
    // 1. Même nom, autre extension : orbispay.com pour orbispay.example.
    if (lu.nom === marque && lu.suffixe !== vrai.suffixe) {
      return resultat("autre_extension",
        `Le nom « ${marque} » est le bon, mais l'extension change : .${lu.suffixe} au lieu de .${vrai.suffixe}.`);
    }
    // 2. Même squelette : alphabet étranger, chiffres déguisés ou tiret ajouté.
    if (lu.nom !== marque && squelette(nomUni) === sq) {
      if (lu.nom.startsWith("xn--")) {
        const intrus = [...new Set(Array.from(nomUni).filter((c) => c.charCodeAt(0) > 0x7f))].join(" ");
        const etranger = Array.from(nomUni).some((c) => c in CONFUSABLES);
        return resultat("punycode", etranger
          ? `Le nom ressemble à « ${marque} », mais certaines lettres (${intrus}) viennent d'un autre alphabet.`
          : `Le nom ressemble à « ${marque} », mais avec des accents (${intrus}).`);
      }
      const sansTiret = (x) => x.replace(/[-_]/g, "");
      if (sansTiret(lu.nom) === sansTiret(marque)) {
        return resultat("tiret", lu.nom.length > marque.length
          ? `« ${lu.nom} » ajoute un tiret à « ${marque} ».`
          : `« ${lu.nom} » retire le tiret de « ${marque} ».`);
      }
      return resultat("confusables",
        `« ${lu.nom} » remplace des lettres de « ${marque} » par des caractères qui leur ressemblent.`);
    }
    // 3. Une ou deux lettres d'écart.
    const ecart = distance(squelette(nomUni), sq);
    if (ecart > 0 && ecart <= seuil(marque)) {
      return resultat("distance",
        `« ${nomUni} » diffère de « ${marque} » ${lettres(distance(nomUni, marque))}.`);
    }
  }

  // 4. Nom de confiance glissé dans un autre domaine, en sous-domaine ou accolé
  //    à un autre mot : orbispay-verification.example, orbispay.example.secure.com.
  if (Array.from(marque).length >= 4) {
    const morceaux = unicode.split(".").flatMap((l) => [l, ...l.split(/[-_]/)]).filter(Boolean);
    const contient = morceaux.some((m) => m.includes(marque) || squelette(m).includes(sq))
      || (Array.from(marque).length >= 6 && squelette(unicode.replace(/\./g, "")).includes(sq));
    if (contient) {
      return resultat("nom_noye",
        `« ${marque} » apparaît dans l'adresse, mais le site appartient à ${proprietaire}.`);
    }
    // 5. Un mot proche du nom de confiance, accolé à un autre : orbispey-securite.com.
    const proche = morceaux.find((m) => {
      const e = distance(squelette(m), sq);
      return e > 0 && e <= seuil(marque);
    });
    if (proche) {
      return resultat("nom_proche",
        `« ${proche} » ressemble à « ${marque} », mais le site appartient à ${proprietaire}.`);
    }
  }
  return null;
}

/**
 * Analyse un nom d'hôte (ou une URL) face à la liste de confiance.
 * Renvoie { verdict, domaine, affiche, imite, raison, explication }.
 */
export function analyserDomaine(entree, domainesConfiance = DOMAINES_PAR_DEFAUT) {
  const hote = normaliserHote(entree);
  const affiche = hote.split(".").map(libelleUnicode).join(".");
  const base = { domaine: hote, affiche, imite: null, raison: null, explication: null };
  const domaines = [...new Set((domainesConfiance ?? []).map(normaliserHote).filter(Boolean))];

  if (!hote || estAdresseIP(hote) || !hote.includes(".")) return { ...base, verdict: "neutre" };

  const vrai = confiance(hote, domaines);
  if (vrai) return { ...base, verdict: "confiance", imite: vrai };

  for (const cible of domaines) {
    const r = comparerA(hote, affiche, cible);
    if (r) return { ...base, ...r, verdict: "sosie" };
  }
  return { ...base, verdict: "neutre" };
}

// ---------------------------------------------------------------- règle de blocage

/**
 * Expression régulière (RE2, pour declarativeNetRequest) qui reconnaît une URL
 * dont le nom d'hôte contient le nom de confiance, éventuellement déguisé
 * (0 pour o, 1 pour l, rn pour m, tiret entre deux lettres). Chrome l'applique
 * avant d'envoyer la requête : ces sosies-là n'atteignent jamais le réseau.
 * Toute URL reconnue est aussi un « sosie » pour analyserDomaine (règles 2 et 4),
 * sauf les domaines de confiance, que la règle d'autorisation fait passer avant.
 * Renvoie null pour un nom trop court (moins de 5 lettres), trop risqué à bloquer.
 */
export function motifBlocage(domaine) {
  const { nom } = decouper(normaliserHote(domaine));
  const lettresNom = Array.from(nom.replace(/[-_]/g, ""));
  if (lettresNom.length < 5 || !lettresNom.every((c) => /[a-z0-9]/.test(c))) return null;
  const classes = {};
  for (const c of "abcdefghijklmnopqrstuvwxyz0123456789") {
    const sq = squelette(c);
    (classes[sq] ??= []).push(c);
  }
  const multiples = { m: "rn", w: "vv", d: "cl" };
  const corps = lettresNom.map((c) => {
    const sq = squelette(c);
    const simples = classes[sq].length > 1 ? `[${classes[sq].join("")}]` : c;
    return multiples[sq] ? `(?:${simples}|${multiples[sq]})` : simples;
  });
  return `^https?://[^/?#]*${corps.join("-?")}`;
}
