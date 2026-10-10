// Tests du comparateur de domaines. Lancer : `node --test tests/` depuis extension/.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  analyserDomaine, decoderPunycode, decouper, distance, normaliserHote, seuil, squelette,
} from "../comparateur.js";

const LISTE = ["orbispay.example"];
const verdict = (h, liste = LISTE) => analyserDomaine(h, liste);

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

test("adresses IP, localhost et entrées vides restent neutres", () => {
  for (const h of ["127.0.0.1", "[::1]", "localhost", "", "   ", null, "http://"]) {
    assert.equal(verdict(h).verdict, "neutre", String(h));
  }
});

test("même nom, autre extension", () => {
  for (const h of ["orbispay.com", "www.orbispay.fr", "orbispay.co.uk"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "sosie", h);
    assert.equal(r.raison, "autre_extension", h);
    assert.equal(r.imite, "orbispay.example");
  }
});

test("une lettre d'écart : remplacement, ajout, retrait, inversion", () => {
  for (const h of ["orbispai.example", "orbisspay.example", "orbspay.example", "orbispya.example", "orbsipay.com"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "sosie", h);
    assert.equal(r.raison, "distance", h);
  }
});

test("chiffres et lettres qui se ressemblent", () => {
  for (const h of ["0rbispay.example", "orb1spay.example", "orbi5pay.example"]) {
    const r = verdict(h);
    assert.equal(r.verdict, "sosie", h);
    assert.equal(r.raison, "confusables", h);
  }
  // « rn » se lit « m » : le squelette de « rnarque » est celui de « marque ».
  assert.equal(squelette("rnarque"), squelette("marque"));
  assert.equal(verdict("rnonbanque.example", ["monbanque.example"]).raison, "confusables");
});

test("tiret ajouté", () => {
  const r = verdict("orbis-pay.example");
  assert.equal(r.verdict, "sosie");
  assert.equal(r.raison, "tiret");
});

test("alphabet étranger : o cyrillique et alpha grec, en Unicode ou en punycode", () => {
  const cyrillique = "оrbispay.example"; // о cyrillique
  const r = verdict(cyrillique);
  assert.equal(r.verdict, "sosie");
  assert.equal(r.raison, "punycode");
  assert.ok(r.domaine.startsWith("xn--"), "le domaine envoyé reste en ASCII");
  assert.equal(r.affiche, cyrillique);
  assert.match(r.explication, /autre alphabet/);

  // Même nom passé directement en punycode, comme Chrome le donne à l'extension.
  const enAscii = normaliserHote(cyrillique);
  assert.equal(verdict(enAscii).raison, "punycode");

  assert.equal(verdict("orbispαy.example").raison, "punycode"); // α grec
});

test("accents ajoutés", () => {
  const r = verdict("orbíspay.example"); // í
  assert.equal(r.verdict, "sosie");
  assert.equal(r.raison, "punycode");
  assert.match(r.explication, /accents/);
});

test("nom de confiance glissé dans un autre domaine", () => {
  const cas = {
    "orbispay-verification.example": "orbispay-verification.example",
    "verification-orbispay.com": "verification-orbispay.com",
    "orbispay.example.secure-login.com": "secure-login.com",
    "login.orbispay.example.evil.co.uk": "evil.co.uk",
    "0rbispay-support.net": "0rbispay-support.net",
  };
  for (const [h, proprio] of Object.entries(cas)) {
    const r = verdict(h);
    assert.equal(r.verdict, "sosie", h);
    assert.equal(r.raison, "nom_noye", h);
    assert.ok(r.explication.includes(proprio), `${h} : ${r.explication}`);
  }
});

test("mot proche du nom de confiance, accolé à un autre", () => {
  const r = verdict("orbispey-securite.com");
  assert.equal(r.verdict, "sosie");
  assert.equal(r.raison, "nom_proche");
});

test("l'URL complète est réduite au nom d'hôte", () => {
  const r = verdict("https://ORBISPAY-verification.example:8443/connexion?compte=42#x");
  assert.equal(r.domaine, "orbispay-verification.example");
  assert.equal(r.verdict, "sosie");
});

test("plusieurs domaines de confiance : chacun protège son nom", () => {
  const liste = ["orbispay.example", "orbis-paie.example"];
  assert.equal(verdict("orbis-paie.example", liste).verdict, "confiance");
  const r = verdict("orbispaie.example", liste);
  assert.equal(r.imite, "orbis-paie.example");
  assert.equal(r.raison, "tiret");
  assert.match(r.explication, /retire le tiret/);
  assert.equal(verdict("0rbispay.example", liste).imite, "orbispay.example");
});

test("un nom court ne déclenche pas l'écart d'une lettre", () => {
  assert.equal(seuil("ab"), 0);
  assert.equal(seuil("orbis"), 1);
  assert.equal(seuil("orbispaiement"), 2);
  assert.equal(verdict("abd.example", ["abc.example"]).verdict, "neutre");
});

test("liste vide : rien n'est sosie", () => {
  assert.equal(verdict("orbispay-verification.example", []).verdict, "neutre");
});

test("outils : distance, découpage, punycode", () => {
  assert.equal(distance("orbispay", "orbispay"), 0);
  assert.equal(distance("orbispay", "orbispya"), 1);
  assert.equal(distance("orbispay", "rnorbispay"), 2);
  assert.deepEqual(decouper("a.orbispay.co.uk"), { nom: "orbispay", suffixe: "co.uk", sous: ["a"] });
  assert.deepEqual(decouper("orbispay.example"), { nom: "orbispay", suffixe: "example", sous: [] });
  assert.equal(decoderPunycode("bcher-kva"), "bücher");
  assert.equal(decoderPunycode("rbispay-8ig"), "оrbispay");
  assert.equal(decoderPunycode("!!"), null);
});
