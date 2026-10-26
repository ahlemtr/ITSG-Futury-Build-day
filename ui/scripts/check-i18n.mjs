// Lists translation keys that exist in one language file but not the other.
// Usage: npm run check:i18n
import { readFileSync } from "node:fs";

const load = (lang) => JSON.parse(readFileSync(new URL(`../src/i18n/${lang}.json`, import.meta.url), "utf-8"));

function keys(obj, prefix = "") {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

const de = new Set(keys(load("de")));
const en = new Set(keys(load("en")));
const missingInEn = [...de].filter((k) => !en.has(k));
const missingInDe = [...en].filter((k) => !de.has(k));

for (const k of missingInEn) console.log(`missing in en.json: ${k}`);
for (const k of missingInDe) console.log(`missing in de.json: ${k}`);

if (missingInEn.length || missingInDe.length) {
  process.exit(1);
}
console.log(`OK: ${de.size} keys, both languages complete`);
