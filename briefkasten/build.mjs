// Baut dist/worker.js: eine einzige Datei, die man im Cloudflare-Dashboard einfügen
// oder mit `npx wrangler deploy` hochladen kann.
//   node build.mjs
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const hier = dirname(fileURLToPath(import.meta.url));
const felder = readFileSync(join(hier, "..", "gemeinsam", "felder.js"), "utf8");
const formular = readFileSync(join(hier, "src", "formular.html"), "utf8")
  .replace("/*FELDER_JS*/", () => felder.replace(/<\/script/gi, "<\\/script"));
const worker = readFileSync(join(hier, "src", "worker.js"), "utf8")
  .replace('import FORMULAR_HTML from "./formular.html";', () => "const FORMULAR_HTML = " + JSON.stringify(formular) + ";");

if (worker.includes("import FORMULAR_HTML")) throw new Error("Formular nicht eingebettet");
mkdirSync(join(hier, "dist"), { recursive: true });
writeFileSync(join(hier, "dist", "worker.js"), worker);
console.log(`dist/worker.js erstellt (${Math.round(worker.length / 1024)} KB)`);
