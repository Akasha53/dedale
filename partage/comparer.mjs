// Passe le corpus partagé dans le moteur de l'extension et compare, adresse par
// adresse, avec la sortie du moteur Swift de l'app Mac.
//
//   node partage/comparer.mjs <sortie-swift.jsonl>
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";

import { analyser } from "../extension/comparateur.js";

const ICI = path.dirname(fileURLToPath(import.meta.url));
const regles = JSON.parse(readFileSync(path.join(ICI, "regles-sites.json"), "utf8"));
const corpus = JSON.parse(readFileSync(path.join(ICI, "corpus-sites.json"), "utf8"));
const swift = readFileSync(process.argv[2], "utf8").trim().split("\n").map((l) => JSON.parse(l));

const adresses = [
  ...corpus.legitimes, ...corpus.louches.map((l) => l.adresse), ...corpus.raccourcis, ...corpus.comparaison_seule,
];
let ecarts = 0;
if (swift.length !== adresses.length) {
  console.log(`ÉCART : ${swift.length} résultats Swift pour ${adresses.length} adresses`);
  ecarts += 1;
}
adresses.forEach((a, i) => {
  const js = analyser(a, regles);
  const sw = swift[i];
  if (!sw || sw.adresse !== a || !isDeepStrictEqual(js, sw.resultat)) {
    ecarts += 1;
    console.log(`ÉCART sur ${JSON.stringify(a)}\n  extension : ${JSON.stringify(js)}\n  app Mac   : ${JSON.stringify(sw?.resultat)}`);
  }
});
console.log(ecarts ? `${ecarts} écart(s) entre l'extension et l'app Mac.`
  : `Extension et app Mac : résultats identiques sur ${adresses.length} adresses.`);
process.exit(ecarts ? 1 : 0);
