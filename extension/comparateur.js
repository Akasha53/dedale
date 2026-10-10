// Moteur d'analyse des adresses : dit si un site est louche, et pourquoi.
//
// Module pur, sans API Chrome : le service worker l'importe, et les tests le font
// tourner sous Node. Les règles (marques, mots d'appât, extensions à risque, textes)
// viennent de `regles-sites.json`, copie de `partage/regles-sites.json`, que l'app
// Mac lit aussi. `app-mac/Sources/Dedale/SitesRegles.swift` applique le même
// algorithme : `partage/verifier.sh` compare les deux sur le corpus partagé.
//
// Il ne voit que l'hôte et la partie placée avant « @ » ; jamais le chemin, la
// requête ou le contenu de la page.
//
// Verdicts :
//   « louche »    : alerte (sosie, marque détournée, @, adresse IP, alphabets mêlés…) ;
//   « raccourci » : raccourcisseur de liens, signalé sans alarme ;
//   « confiance » : domaine de l'organisation, d'une marque connue, ou déclaré sûr ;
//   « neutre »    : rien à signaler.
//
// Heuristique assumée : elle ne connaît pas la réputation d'un site et ne remplace
// pas la navigation sécurisée du navigateur.

export const NOM_PAR_DEFAUT = "Orbis Pay";
export const DOMAINES_PAR_DEFAUT = ["orbispay.example"];

const ALPHABETS = ["latin", "grec", "cyrillique", "armenien"];

// ---------------------------------------------------------------- punycode (RFC 3492)

const BASE = 36, TMIN = 1, TMAX = 26, SKEW = 38, DAMP = 700, BIAS0 = 72, N0 = 128;

function adapter(delta, nbPoints, premier) {
  delta = premier ? Math.floor(delta / DAMP) : Math.floor(delta / 2);
  delta += Math.floor(delta / nbPoints);
  let k = 0;
  while (delta > Math.floor(((BASE - TMIN) * TMAX) / 2)) {
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

function chiffreVersCar(d) {
  return String.fromCharCode(d < 26 ? 97 + d : 22 + d);
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

/** Encode un libellé Unicode (sans le préfixe « xn-- »). */
export function encoderPunycode(texte) {
  const points = Array.from(texte, (c) => c.codePointAt(0));
  let sortie = points.filter((p) => p < 0x80).map((p) => String.fromCharCode(p)).join("");
  const nbBase = sortie.length;
  let h = nbBase;
  if (nbBase > 0) sortie += "-";
  let n = N0, delta = 0, biais = BIAS0;
  while (h < points.length) {
    const m = Math.min(...points.filter((p) => p >= n));
    delta += (m - n) * (h + 1);
    n = m;
    for (const p of points) {
      if (p < n) delta++;
      if (p === n) {
        let q = delta;
        for (let k = BASE; ; k += BASE) {
          const t = k <= biais ? TMIN : k >= biais + TMAX ? TMAX : k - biais;
          if (q < t) break;
          sortie += chiffreVersCar(t + ((q - t) % (BASE - t)));
          q = Math.floor((q - t) / (BASE - t));
        }
        sortie += chiffreVersCar(q);
        biais = adapter(delta, h + 1, h === nbBase);
        delta = 0;
        h++;
      }
    }
    delta++;
    n++;
  }
  return sortie;
}

/** Libellé lisible : « xn--rbispay-8ig » devient « оrbispay » (o cyrillique). */
export function libelleUnicode(libelle) {
  if (!libelle.startsWith("xn--")) return libelle;
  return decoderPunycode(libelle.slice(4)) ?? libelle;
}

// ---------------------------------------------------------------- lecture de l'adresse

const HOTE_ASCII = /^[a-z0-9.\-_]+$/;

function versAscii(hote) {
  return hote.split(".").map((l) => {
    if (/^[\x00-\x7f]*$/.test(l)) return l;
    return "xn--" + encoderPunycode(l);
  }).join(".");
}

/**
 * Sépare une adresse en { identifiant, hote }. L'identifiant est ce qui précède
 * « @ » dans la partie hôte. L'hôte sort en minuscules, sans port ni point final,
 * en ASCII (un nom Unicode passe en punycode, comme le navigateur l'envoie).
 * Chemin, requête et fragment sont jetés. Un hôte illisible donne "".
 */
export function decomposer(entree) {
  let s = String(entree ?? "").trim();
  const schema = /^[a-z][a-z0-9+.-]*:\/\//i.exec(s);
  if (schema) s = s.slice(schema[0].length);
  const fin = s.search(/[/?#\\]/);
  const autorite = fin >= 0 ? s.slice(0, fin) : s;
  const arobase = autorite.lastIndexOf("@");
  const identifiant = arobase >= 0 ? autorite.slice(0, arobase) : "";
  let hote = arobase >= 0 ? autorite.slice(arobase + 1) : autorite;
  if (hote.startsWith("[")) {
    const ferme = hote.indexOf("]");
    hote = ferme > 0 ? hote.slice(0, ferme + 1) : "";
    return { identifiant: identifiant.toLowerCase(), hote: /^\[[0-9a-f:.]+\]$/i.test(hote) ? hote.toLowerCase() : "" };
  }
  const deuxPoints = hote.indexOf(":");
  if (deuxPoints >= 0) hote = hote.slice(0, deuxPoints);
  hote = hote.normalize("NFC").toLowerCase().replace(/\.+$/, "");
  if (!hote || hote.startsWith(".")) return { identifiant: identifiant.toLowerCase(), hote: "" };
  hote = versAscii(hote);
  if (!HOTE_ASCII.test(hote) || hote.includes("..")) hote = "";
  return { identifiant: identifiant.toLowerCase(), hote };
}

/** Nom d'hôte nettoyé (voir `decomposer`), ou "" si illisible. */
export function normaliserHote(entree) {
  return decomposer(entree).hote;
}

function ipv4(hote) {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(hote);
  if (!m) return null;
  const o = m.slice(1).map(Number);
  return o.every((x) => x <= 255) ? o : null;
}

function ipPrivee(hote) {
  if (hote.startsWith("[")) {
    const h = hote.slice(1, -1);
    return h === "::1" || h === "::" || /^f[cd]/.test(h) || /^fe[89ab]/.test(h);
  }
  const [a, b] = ipv4(hote);
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31)
    || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127);
}

// ---------------------------------------------------------------- outils

/** Sépare « a.b.orbispay.co.uk » en { nom: "orbispay", suffixe: "co.uk", sous: ["a","b"] }. */
export function decouper(hote, regles = null) {
  const doubles = regles ? preparer(regles).doubles : DOUBLES_MINIMUM;
  const e = hote.split(".");
  if (e.length < 2) return { nom: "", suffixe: e[0] ?? "", sous: [] };
  const deux = e.slice(-2).join(".");
  if (e.length >= 3 && doubles.has(deux)) {
    return { nom: e[e.length - 3], suffixe: deux, sous: e.slice(0, -3) };
  }
  return { nom: e[e.length - 2], suffixe: e[e.length - 1], sous: e.slice(0, -2) };
}
const DOUBLES_MINIMUM = new Set(["co.uk", "gouv.fr"]);

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

function longueur(texte) {
  return Array.from(texte).length;
}

/** Écart toléré pour un nom : 0, 1 ou 2 lettres selon sa longueur. */
export function seuil(nom, palier) {
  const n = longueur(nom);
  if (n < palier.une_lettre_des) return 0;
  return n < palier.deux_lettres_des ? 1 : 2;
}

function remplir(modele, valeurs) {
  return modele.replace(/\{(\w+)\}/g, (tout, cle) => (cle in valeurs ? String(valeurs[cle]) : tout));
}

/** « de PayPal », mais « d'Apple » ; « que Google », mais « qu'Orbis Pay ». */
export function elider(mot, nom) {
  const voyelle = /^[aeiouyhàâäéèêëîïôöûü]/i.test(nom);
  return voyelle ? `${mot.slice(0, -1)}'${nom}` : `${mot} ${nom}`;
}

function alphabet(point) {
  if ((point >= 0x41 && point <= 0x5a) || (point >= 0x61 && point <= 0x7a)) return "latin";
  if (point >= 0xc0 && point <= 0x2af && point !== 0xd7 && point !== 0xf7) return "latin";
  if (point >= 0x1e00 && point <= 0x1eff) return "latin";
  if ((point >= 0x370 && point <= 0x3ff) || (point >= 0x1f00 && point <= 0x1fff)) return "grec";
  if (point >= 0x400 && point <= 0x52f) return "cyrillique";
  if (point >= 0x530 && point <= 0x58f) return "armenien";
  return null;
}

// ---------------------------------------------------------------- règles préparées

const cache = new WeakMap();

/** Tables tirées des règles une fois pour toutes (ensembles, squelettes des mots). */
export function preparer(regles) {
  let p = cache.get(regles);
  if (p) return p;
  const confusables = regles.confusables ?? {};
  const sequences = regles.sequences ?? [];
  const chiffres = regles.chiffres ?? {};
  const sq = (texte) => {
    let s = texte.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
    s = Array.from(s, (c) => confusables[c] ?? c).join("");
    for (const [de, vers] of sequences) s = s.split(de).join(vers);
    s = Array.from(s, (c) => chiffres[c] ?? c).join("");
    return s.replace(/[-_]/g, "");
  };
  const appats = (regles.appats ?? []).map((mot) => ({ mot, sq: sq(mot) }));
  p = {
    sq,
    confusables,
    doubles: new Set(regles.suffixes_doubles ?? []),
    risque: new Set(regles.extensions_risque ?? []),
    raccourcisseurs: regles.raccourcisseurs ?? [],
    surs: regles.domaines_surs ?? [],
    appats,
    appatParSq: new Map([...appats].reverse().map((a) => [a.sq, a.mot])), // le premier de la liste l'emporte
    marques: (regles.marques ?? []).map((m) => ({ ...m, strict: false })),
    seuils: regles.seuils,
    textes: regles.textes,
  };
  cache.set(regles, p);
  return p;
}

/** Squelette visuel selon les règles : ce que l'œil lit, déguisements retirés. */
export function squelette(texte, regles) {
  return preparer(regles).sq(texte);
}

function couvre(hote, domaine) {
  return hote === domaine || hote.endsWith("." + domaine);
}

// ---------------------------------------------------------------- analyse

/**
 * Analyse une adresse (URL complète ou nom d'hôte).
 * `organisation` : { nom, domaines } ; à défaut, celle des règles.
 * Renvoie { verdict, categorie, raison, marque, imite, domaine, affiche, explication }.
 */
export function analyser(adresse, regles, organisation = null) {
  const p = preparer(regles);
  const org = organisation ?? regles.organisation ?? { nom: NOM_PAR_DEFAUT, domaines: [] };
  const orgDomaines = [...new Set((org.domaines ?? []).map(normaliserHote).filter((d) => d.includes(".")))];
  const orgMarque = {
    nom: org.nom || NOM_PAR_DEFAUT,
    domaines: orgDomaines,
    mots: [...new Set(orgDomaines.map((d) => decouper(d, regles).nom).filter(Boolean))],
    strict: true,
  };

  const { identifiant, hote } = decomposer(adresse);
  const affiche = hote.startsWith("[") ? hote : hote.split(".").map(libelleUnicode).join(".");
  const base = {
    verdict: "neutre", categorie: null, raison: null, marque: null, imite: null,
    domaine: hote, affiche, explication: null,
  };
  if (!hote) return base;

  const t = p.textes.raisons;
  const louche = (categorie, raison, marque, imite, valeurs) => ({
    ...base, verdict: "louche", categorie, raison,
    marque: marque ?? null, imite: imite ?? null,
    explication: remplir(t[raison], {
      marque: marque ?? "", de_marque: elider("de", marque ?? ""), que_marque: elider("que", marque ?? ""),
      hote: affiche, ...valeurs,
    }),
  });

  // 1. Astuce « marque@vrai-hôte » : le navigateur ignore tout ce qui précède @.
  if (identifiant) {
    const leurre = identifiant.split(":")[0];
    const trouve = marqueDansTexte(leurre, [orgMarque, ...p.marques], p);
    if (leurre.includes(".") || trouve) {
      return louche("arobase", "arobase", trouve?.nom, trouve?.domaines[0], { leurre });
    }
  }

  // 2. Adresse IP ou nom sans point.
  const estIP = hote.startsWith("[") || ipv4(hote) !== null;
  if (estIP) {
    return ipPrivee(hote) ? base : louche("ip_brute", "ip_brute", null, null, {});
  }
  if (!hote.includes(".")) return base;

  // 3. Domaines connus : déclarés sûrs, organisation, marques.
  if (p.surs.some((d) => couvre(hote, d))) return { ...base, verdict: "confiance" };
  const vraiOrg = orgDomaines.find((d) => couvre(hote, d));
  if (vraiOrg) return { ...base, verdict: "confiance", marque: orgMarque.nom, imite: vraiOrg };
  for (const m of p.marques) {
    const d = m.domaines.find((x) => couvre(hote, x));
    if (d) return { ...base, verdict: "confiance", marque: m.nom, imite: d };
  }

  // 4. Raccourcisseurs : signalés, sans alarme.
  if (p.raccourcisseurs.some((d) => couvre(hote, d))) {
    return { ...base, verdict: "raccourci", categorie: "raccourci", raison: "raccourci",
      explication: remplir(t.raccourci, { hote: affiche }) };
  }

  // 5. Marques : l'organisation d'abord (règles strictes), puis les marques connues.
  const lu = decouper(hote, regles);
  const ctx = {
    hote, affiche, lu, p, regles,
    nomUni: libelleUnicode(lu.nom),
    proprietaire: `${lu.nom}.${lu.suffixe}`,
    libelles: [...lu.sous, lu.nom],
  };
  ctx.appats = appatsDans(ctx.libelles, p);
  for (const m of [orgMarque, ...p.marques]) {
    const r = comparerMarque(m, ctx);
    if (r) return louche(r.categorie, r.raison, m.nom, r.imite, r.valeurs);
  }

  // 6. Signaux sans marque.
  const r = signauxGeneriques(ctx);
  if (r) return louche(r.categorie, r.raison, null, null, r.valeurs);
  return base;
}

/** Marque reconnue dans un texte libre (ce qui précède @) : domaine ou mot. */
function marqueDansTexte(texte, marques, p) {
  const libelles = texte.split(".").filter(Boolean);
  for (const m of marques) {
    if (m.domaines.some((d) => texte === d || texte.endsWith("." + d) || texte.startsWith(d + ".")
      || texte.includes("." + d + "."))) return m;
    if (m.mots.some((mot) => libelles.some((l) => contient(l, mot, p)))) return m;
  }
  return null;
}

/** Le libellé contient-il le mot ? Sous-chaîne pour un mot long, mot entier sinon. */
function contient(libelle, mot, p) {
  const skm = p.sq(mot);
  if (!skm) return false;
  const u = libelleUnicode(libelle);
  if (longueur(skm) >= p.seuils.sous_chaine_des) return p.sq(u).includes(skm);
  return u.split(/[-_]/).some((jeton) => p.sq(jeton) === skm);
}

/** Mots d'appât présents, dans leur ordre d'apparition dans l'adresse, sans doublon. */
function appatsDans(libelles, p) {
  const vus = [];
  for (const l of libelles) {
    for (const jeton of libelleUnicode(l).split(/[-_]/)) {
      const mot = p.appatParSq.get(p.sq(jeton));
      if (mot && !vus.includes(mot)) vus.push(mot);
    }
  }
  return vus;
}

/** Appât collé à la marque dans un même libellé : « paypalsecure ». */
function appatColle(libelles, mot, p) {
  const skm = p.sq(mot);
  if (longueur(skm) < p.seuils.sous_chaine_des) return null;
  for (const l of libelles) {
    const s = p.sq(libelleUnicode(l));
    if (!s.includes(skm)) continue;
    const reste = s.split(skm).join(" ");
    const a = p.appats.find((x) => longueur(x.sq) >= 4 && reste.includes(x.sq));
    if (a) return a.mot;
  }
  return null;
}

function comparerMarque(m, ctx) {
  const { lu, nomUni, p, proprietaire, libelles } = ctx;
  const palier = m.strict ? p.seuils.ecart_organisation : p.seuils.ecart_marques;
  const r = (categorie, raison, imite, valeurs) => ({ categorie, raison, imite, valeurs });
  const domainePour = (mot) => m.domaines.find((d) => decouper(d, ctx.regles).nom === mot) ?? m.domaines[0];

  for (const mot of m.mots) {
    const skm = p.sq(mot);
    const court = longueur(mot) < p.seuils.nom_court;
    const vrai = domainePour(mot);
    // a. Même nom, autre extension : paypal.xyz pour paypal.com.
    if (lu.nom === mot && (m.strict || !court)) {
      return r("sosie", "autre_extension", vrai, {
        nom: lu.nom, suffixe: lu.suffixe, vrai_suffixe: decouper(vrai, ctx.regles).suffixe,
      });
    }
    // b. Même squelette : autre alphabet, accents, chiffres déguisés, tiret.
    if (lu.nom !== mot && p.sq(nomUni) === skm) {
      const deguise = /\d/.test(lu.nom) || lu.nom.startsWith("xn--");
      if (m.strict || !court || deguise) {
        if (lu.nom.startsWith("xn--")) {
          const intrus = [...new Set(Array.from(nomUni).filter((c) => c.codePointAt(0) > 0x7f))].join(" ");
          const etranger = Array.from(nomUni).some((c) => c in p.confusables);
          return r("sosie", etranger ? "punycode_etranger" : "punycode_accents", vrai, { mot, intrus });
        }
        const sansTiret = (x) => x.replace(/[-_]/g, "");
        if (sansTiret(lu.nom) === sansTiret(mot)) {
          return r("sosie", longueur(lu.nom) > longueur(mot) ? "tiret_ajoute" : "tiret_retire", vrai,
            { nom: lu.nom, mot });
        }
        return r("sosie", "confusables", vrai, { nom: lu.nom, mot });
      }
    }
    // c. Une ou deux lettres d'écart.
    const max = m.ecart ?? seuil(mot, palier);
    const ecart = distance(p.sq(nomUni), skm);
    if (ecart > 0 && ecart <= max) {
      const n = distance(nomUni, mot);
      const texte = n === 1 ? p.textes.ecart_un : remplir(p.textes.ecart_plusieurs, { n });
      return r("sosie", "distance", vrai, { nom: nomUni, mot, ecart: texte });
    }
  }

  // d. Un vrai domaine de la marque placé en sous-domaine : paypal.com.verif-compte.xyz.
  const sous = lu.sous.join(".");
  for (const d of m.domaines) {
    if (d.includes(".") && (sous === d || sous.endsWith("." + d) || sous.startsWith(d + ".")
      || sous.includes("." + d + "."))) {
      return r("marque_detournee", "marque_sous_domaine", d, { leurre: d, proprietaire });
    }
  }

  if (m.strict) {
    // e. Organisation : son nom n'a rien à faire dans un autre domaine.
    const morceaux = ctx.affiche.split(".").flatMap((l) => [l, ...l.split(/[-_]/)]).filter(Boolean);
    for (const mot of m.mots) {
      if (longueur(mot) < 4) continue;
      const skm = p.sq(mot);
      const dedans = morceaux.some((x) => x.includes(mot) || p.sq(x).includes(skm))
        || (longueur(mot) >= 6 && p.sq(ctx.affiche.replace(/\./g, "")).includes(skm));
      if (dedans) return r("marque_detournee", "nom_noye", domainePour(mot), { mot, proprietaire });
    }
    // f. Un mot proche du nom, accolé à un autre : orbispey-securite.com.
    for (const mot of m.mots) {
      if (longueur(mot) < 4) continue;
      const skm = p.sq(mot);
      const max = m.ecart ?? seuil(mot, palier);
      const proche = morceaux.find((x) => {
        const e = distance(p.sq(x), skm);
        return e > 0 && e <= max;
      });
      if (proche) return r("sosie", "nom_proche", domainePour(mot), { proche, mot, proprietaire });
    }
    return null;
  }

  // e. Marque connue accolée à un mot d'appât, ou posée sur une extension à risque.
  for (const mot of m.mots) {
    if (!libelles.some((l) => contient(l, mot, p))) continue;
    const appat = ctx.appats[0] ?? appatColle(libelles, mot, p);
    if (appat) return r("marque_detournee", "marque_appat", domainePour(mot), { mot, appat, proprietaire });
    if (p.risque.has(lu.suffixe)) {
      return r("marque_detournee", "marque_extension", domainePour(mot), { mot, suffixe: lu.suffixe });
    }
  }
  // f. Un mot proche de la marque, accompagné d'un mot d'appât : paypai-login.com.
  if (ctx.appats.length) {
    const jetons = libelles.flatMap((l) => libelleUnicode(l).split(/[-_]/)).filter(Boolean);
    for (const mot of m.mots) {
      const max = m.ecart ?? seuil(mot, palier);
      const skm = p.sq(mot);
      const proche = jetons.find((x) => {
        const e = distance(p.sq(x), skm);
        return e > 0 && e <= max;
      });
      if (proche) return r("sosie", "nom_proche", domainePour(mot), { proche, mot, proprietaire });
    }
  }
  return null;
}

function signauxGeneriques(ctx) {
  const { lu, p, affiche, proprietaire } = ctx;
  const s = p.seuils;
  // Plusieurs alphabets dans un même libellé : « mаgasin » avec un а cyrillique.
  for (const l of affiche.split(".")) {
    const vus = new Set();
    for (const c of l) {
      const a = alphabet(c.codePointAt(0));
      if (a) vus.add(a);
    }
    if (vus.size >= 2) {
      const noms = ALPHABETS.filter((a) => vus.has(a)).map((a) => p.textes.alphabets[a]).join(", ");
      return { categorie: "alphabets_melanges", raison: "alphabets_melanges", valeurs: { nom: l, alphabets: noms } };
    }
  }
  const risque = p.risque.has(lu.suffixe);
  const n = lu.sous.length;
  if (n >= s.sous_domaines_seuls || (n >= s.sous_domaines_avec_signal && (risque || ctx.appats.length))) {
    return { categorie: "adresse_louche", raison: "sous_domaines", valeurs: { n, proprietaire } };
  }
  if (risque && ctx.appats.length) {
    return { categorie: "adresse_louche", raison: "appat_extension",
      valeurs: { appats: ctx.appats.join(", "), suffixe: lu.suffixe } };
  }
  const appatsNom = appatsDans([lu.nom], p);
  const tirets = (lu.nom.match(/-/g) ?? []).length;
  if (appatsNom.length >= s.appats_multiples && tirets >= s.tirets_appats_multiples) {
    return { categorie: "adresse_louche", raison: "appats_multiples",
      valeurs: { nom: libelleUnicode(lu.nom), appats: appatsNom.join(", ") } };
  }
  return null;
}

// ---------------------------------------------------------------- textes de l'alerte

/** Titre et sous-titre de l'alerte, communs à l'extension et à l'app Mac. */
export function titres(resultat, regles) {
  const t = regles.textes;
  if (resultat.marque) {
    return { titre: remplir(t.titre_marque, { marque: resultat.marque }), suite: t.suite_marque };
  }
  return { titre: t.titre_sans_marque, suite: t.suite_sans_marque };
}

/** Conseil à retenir pour la prochaine fois, selon la catégorie. */
export function conseil(resultat, regles) {
  return regles.textes.conseils[resultat.categorie] ?? null;
}

// ---------------------------------------------------------------- règle de blocage

/**
 * Expression régulière (RE2, pour declarativeNetRequest) qui reconnaît une URL
 * dont le nom d'hôte contient le nom d'un domaine de l'organisation, éventuellement
 * déguisé (0 pour o, 1 pour l, rn pour m, tiret entre deux lettres). Chrome
 * l'applique avant d'envoyer la requête : ces sosies-là n'atteignent jamais le
 * réseau. Toute URL reconnue est aussi « louche » pour `analyser`, sauf les domaines
 * de l'organisation, que la règle d'autorisation fait passer avant.
 * Renvoie null pour un nom trop court (moins de 5 lettres), trop risqué à bloquer.
 */
export function motifBlocage(domaine, regles) {
  const p = preparer(regles);
  const { nom } = decouper(normaliserHote(domaine), regles);
  const lettresNom = Array.from(nom.replace(/[-_]/g, ""));
  if (lettresNom.length < 5 || !lettresNom.every((c) => /[a-z0-9]/.test(c))) return null;
  const classes = {};
  for (const c of "abcdefghijklmnopqrstuvwxyz0123456789") {
    (classes[p.sq(c)] ??= []).push(c);
  }
  const multiples = Object.fromEntries((regles.sequences ?? []).map(([de, vers]) => [vers, de]));
  const corps = lettresNom.map((c) => {
    const s = p.sq(c);
    const simples = classes[s].length > 1 ? `[${classes[s].join("")}]` : c;
    return multiples[s] ? `(?:${simples}|${multiples[s]})` : simples;
  });
  return `^https?://[^/?#]*${corps.join("-?")}`;
}
