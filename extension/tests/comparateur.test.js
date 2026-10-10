// Tests du moteur d'analyse des adresses. Lancer : `node --test tests/` depuis extension/.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  analyser, conseil, decoderPunycode, decomposer, decouper, distance, encoderPunycode, motifBlocage,
  normaliserHote, seuil, squelette, titres,
} from "../comparateur.js";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const lire = (chemin) => readFileSync(path.resolve(ICI, chemin), "utf8");
const REGLES = JSON.parse(lire("../regles-sites.json"));
const CORPUS = JSON.parse(lire("../../partage/corpus-sites.json"));

const ORG = { nom: "Orbis Pay", domaines: ["orbispay.example"] };
const verdict = (h, domaines = ORG.domaines) => analyser(h, REGLES, { nom: "Orbis Pay", domaines });

test("la copie des règles dans l'extension est identique à partage/", () => {
  assert.equal(lire("../regles-sites.json"), lire("../../partage/regles-sites.json"),
    "lancer partage/synchroniser.sh");
});

test("corpus partagé : aucune alerte sur les domaines légitimes", () => {
  const alertes = CORPUS.legitimes
    .map((a) => [a, analyser(a, REGLES)])
    .filter(([, r]) => r.verdict === "louche" || r.verdict === "raccourci")
    .map(([a, r]) => `${a} : ${r.raison}`);
  assert.ok(CORPUS.legitimes.length >= 60, "au moins 60 domaines légitimes");
  assert.deepEqual(alertes, []);
});

test("corpus partagé : chaque site louche est repéré, avec sa catégorie et la marque imitée", () => {
  for (const { adresse, categorie, marque } of CORPUS.louches) {
    const r = analyser(adresse, REGLES);
    assert.equal(r.verdict, "louche", adresse);
    assert.equal(r.categorie, categorie, adresse);
    assert.equal(r.marque, marque, adresse);
    assert.ok(r.explication && !r.explication.includes("{"), `${adresse} : ${r.explication}`);
    assert.ok(conseil(r, REGLES), `${adresse} : conseil`);
  }
});

test("corpus partagé : les raccourcisseurs sont signalés sans alarme", () => {
  for (const a of CORPUS.raccourcis) {
    const r = analyser(a, REGLES);
    assert.equal(r.verdict, "raccourci", a);
    assert.match(r.explication, /raccourcit les liens/);
  }
});

test("les domaines de confiance et leurs sous-domaines passent", () => {
  for (const h of ["orbispay.example", "paiement.orbispay.example", "a.b.orbispay.example", "ORBISPAY.example."]) {
    assert.equal(verdict(h).verdict, "confiance", h);
  }
});

test("un domaine sans rapport reste neutre", () => {
  for (const h of ["fleuriste.example", "exemple.fr", "orbistravel.com", "wikipedia.org", "orbis.com", "pay.example"]) {
    assert.equal(verdict(h).verdict, "neutre", h);
  }
});

test("adresses IP privées, localhost et entrées vides restent neutres", () => {
  for (const h of ["127.0.0.1", "[::1]", "localhost", "10.0.0.4", "192.168.1.20:8080", "", "   ", null, "http://"]) {
    assert.equal(verdict(h).verdict, "neutre", String(h));
  }
});

test("même nom, autre extension", () => {
  for (const h of ["orbispay.com", "www.orbispay.fr", "orbispay.co.uk"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "louche", h);
    assert.equal(r.raison, "autre_extension", h);
    assert.equal(r.imite, "orbispay.example");
    assert.match(r.explication, /celui d'Orbis Pay/);
  }
});

test("une lettre d'écart : remplacement, ajout, retrait, inversion", () => {
  for (const h of ["orbispai.example", "orbisspay.example", "orbspay.example", "orbispya.example", "orbsipay.com"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "louche", h);
    assert.equal(r.raison, "distance", h);
  }
});

test("chiffres et lettres qui se ressemblent", () => {
  for (const h of ["0rbispay.example", "orb1spay.example", "orbi5pay.example"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "louche", h);
    assert.equal(r.raison, "confusables", h);
  }
  assert.equal(squelette("rnarque", REGLES), squelette("marque", REGLES));
  assert.equal(verdict("rnonbanque.example", ["monbanque.example"]).raison, "confusables");
});

test("tiret ajouté", () => {
  const r = verdict("orbis-pay.example");
  assert.equal(r.verdict, "louche");
  assert.equal(r.raison, "tiret_ajoute");
});

test("alphabet étranger : o cyrillique et alpha grec, en Unicode ou en punycode", () => {
  const cyrillique = "оrbispay.example"; // о cyrillique
  const r = verdict(cyrillique);
  assert.equal(r.verdict, "louche");
  assert.equal(r.raison, "punycode_etranger");
  assert.equal(r.domaine, "xn--rbispay-8ig.example", "le domaine envoyé reste en ASCII");
  assert.equal(r.affiche, cyrillique);
  assert.match(r.explication, /autre alphabet/);
  assert.equal(verdict(normaliserHote(cyrillique)).raison, "punycode_etranger");
  assert.equal(verdict("orbispαy.example").raison, "punycode_etranger"); // α grec
});

test("accents ajoutés", () => {
  const r = verdict("orbíspay.example"); // í
  assert.equal(r.verdict, "louche");
  assert.equal(r.raison, "punycode_accents");
  assert.match(r.explication, /accents/);
});

test("nom de l'organisation glissé dans un autre domaine", () => {
  const cas = {
    "orbispay-verification.example": ["nom_noye", "orbispay-verification.example"],
    "verification-orbispay.com": ["nom_noye", "verification-orbispay.com"],
    "orbispay.example.secure-login.com": ["marque_sous_domaine", "secure-login.com"],
    "login.orbispay.example.evil.co.uk": ["marque_sous_domaine", "evil.co.uk"],
    "0rbispay-support.net": ["nom_noye", "0rbispay-support.net"],
    "orbispay-partenaires.fr": ["nom_noye", "orbispay-partenaires.fr"],
  };
  for (const [h, [raison, proprio]] of Object.entries(cas)) {
    const r = verdict(h);
    assert.equal(r.verdict, "louche", h);
    assert.equal(r.categorie, "marque_detournee", h);
    assert.equal(r.raison, raison, h);
    assert.ok(r.explication.includes(proprio), `${h} : ${r.explication}`);
  }
});

test("mot proche du nom de l'organisation, accolé à un autre", () => {
  const r = verdict("orbispey-securite.com");
  assert.equal(r.verdict, "louche");
  assert.equal(r.raison, "nom_proche");
});

test("marque connue : il faut un second signal pour la voir dans un autre domaine", () => {
  // Le nom seul ne suffit pas : ces sites ne sont pas à la marque, mais n'imitent rien.
  for (const h of ["big-apple-pizza.com", "outlookindia.com", "paypal-community.com", "amazonia.org"]) {
    assert.notEqual(analyser(h, REGLES).verdict, "louche", h);
  }
  // Avec un mot d'appât, une extension à risque ou un vrai domaine en sous-domaine, si.
  assert.equal(analyser("apple-support.com", REGLES).raison, "marque_appat");
  assert.equal(analyser("apple-music.xyz", REGLES).raison, "marque_extension");
  assert.equal(analyser("apple.com.musique.example", REGLES).raison, "marque_sous_domaine");
});

test("une extension à risque seule ne déclenche rien", () => {
  for (const h of ["abc.xyz", "fleuriste.top", "photos.online"]) {
    assert.equal(analyser(h, REGLES).verdict, "neutre", h);
  }
});

test("l'astuce de l'arobase, avec ou sans marque", () => {
  const r = analyser("https://www.paypal.com@verif.example/connexion", REGLES);
  assert.equal(r.categorie, "arobase");
  assert.equal(r.marque, "PayPal");
  assert.equal(r.domaine, "verif.example");
  const s = analyser("http://compte.securise.fr@203.0.113.9/", REGLES);
  assert.equal(s.categorie, "arobase");
  assert.equal(s.marque, null);
  // Un simple identifiant sans point ni marque n'est pas une ruse.
  assert.equal(analyser("https://camille@orbispay.example/", REGLES).verdict, "confiance");
});

test("l'URL complète est réduite au nom d'hôte", () => {
  const r = verdict("https://ORBISPAY-verification.example:8443/connexion?compte=42#x");
  assert.equal(r.domaine, "orbispay-verification.example");
  assert.equal(r.verdict, "louche");
  assert.deepEqual(decomposer("https://a:b@Exemple.FR.:443/x?y#z"), { identifiant: "a:b", hote: "exemple.fr" });
});

test("plusieurs domaines de confiance : chacun protège son nom", () => {
  const liste = ["orbispay.example", "orbis-paie.example"];
  assert.equal(verdict("orbis-paie.example", liste).verdict, "confiance");
  const r = verdict("orbispaie.example", liste);
  assert.equal(r.imite, "orbis-paie.example");
  assert.equal(r.raison, "tiret_retire");
  assert.match(r.explication, /retire le tiret/);
  assert.equal(verdict("0rbispay.example", liste).imite, "orbispay.example");
});

test("un nom court ne déclenche pas l'écart d'une lettre", () => {
  const palier = REGLES.seuils.ecart_organisation;
  assert.equal(seuil("ab", palier), 0);
  assert.equal(seuil("orbis", palier), 1);
  assert.equal(seuil("orbispaiement", palier), 2);
  assert.equal(verdict("abd.example", ["abc.example"]).verdict, "neutre");
});

test("liste de l'organisation vide : son nom n'est plus protégé", () => {
  assert.equal(verdict("orbispay-verification.example", []).verdict, "neutre");
});

test("titres de l'alerte : avec ou sans marque", () => {
  assert.deepEqual(titres(verdict("0rbispay.example"), REGLES),
    { titre: "Ce site imite Orbis Pay.", suite: "Ce n'est pas le vrai site." });
  assert.equal(titres(analyser("203.0.113.5", REGLES), REGLES).titre, "Ce site n'a pas l'air sûr.");
});

test("outils : distance, découpage, punycode", () => {
  assert.equal(distance("orbispay", "orbispay"), 0);
  assert.equal(distance("orbispay", "orbispya"), 1);
  assert.equal(distance("orbispay", "rnorbispay"), 2);
  assert.deepEqual(decouper("a.orbispay.co.uk", REGLES), { nom: "orbispay", suffixe: "co.uk", sous: ["a"] });
  assert.deepEqual(decouper("orbispay.example", REGLES), { nom: "orbispay", suffixe: "example", sous: [] });
  assert.equal(decoderPunycode("bcher-kva"), "bücher");
  assert.equal(decoderPunycode("rbispay-8ig"), "оrbispay");
  assert.equal(decoderPunycode("!!"), null);
  for (const mot of ["bücher", "оrbispay", "аррӏе", "mаgasin", "société"]) {
    assert.equal(decoderPunycode(encoderPunycode(mot)), mot, mot);
    assert.equal(`xn--${encoderPunycode(mot)}`, new URL(`http://${mot}`).hostname, mot);
  }
});

test("règle de blocage : elle attrape les sosies évidents de l'organisation avant toute requête", () => {
  const motif = new RegExp(motifBlocage("orbispay.example", REGLES), "i");
  const bloques = [
    "orbispay-verification.example", "0rbispay.example", "orbis-pay.example", "orb1spay.com",
    "orbispay.example.secure-login.com", "connexion.orbispay.fr", "orbispay.com",
  ];
  for (const h of bloques) assert.ok(motif.test(`http://${h}/chemin`), h);

  const libres = ["fleuriste.example", "orbistravel.com", "exemple.fr", "orbis.com"];
  for (const h of libres) assert.ok(!motif.test(`http://${h}/orbispay`), h);
  assert.ok(!motif.test("http://exemple.fr/?r=orbispay.example"));
});

test("règle de blocage : tout ce qu'elle bloque est louche pour l'analyse", () => {
  const motif = new RegExp(motifBlocage("orbispay.example", REGLES), "i");
  const hotes = [
    "orbispay-verification.example", "0rbispay.example", "orbis-pay.example", "orb1spay.com",
    "orbispay.example.secure-login.com", "connexion.orbispay.fr", "orbispay.com", "o-r-b-i-s-p-a-y.net",
    "verif.0rb1spay.example", "orbispay.example", "paiement.orbispay.example",
  ];
  for (const h of hotes) {
    if (!motif.test(`https://${h}/`)) continue;
    const v = verdict(h).verdict;
    assert.ok(v === "louche" || v === "confiance", `${h} : ${v}`);
  }
  assert.equal(motifBlocage("abc.example", REGLES), null);
  assert.match(motifBlocage("monbanque.example", REGLES), /\(\?:m\|rn\)/);
});
