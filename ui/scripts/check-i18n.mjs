// Checks the German UI texts: de.json is the only language file, no text is empty,
// and every translation key the code names literally exists in de.json.
// Keys built at run time (t(`calc.how.${key}`)) cannot be checked here and are skipped.
// Usage: npm run check:i18n
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const i18nDir = new URL("../src/i18n/", import.meta.url);
const srcDir = fileURLToPath(new URL("../src/", import.meta.url));
const problems = [];

const other = readdirSync(i18nDir).filter((f) => f.endsWith(".json") && f !== "de.json");
for (const f of other) problems.push(`only de.json is allowed, found ${f}`);

const de = JSON.parse(readFileSync(new URL("de.json", i18nDir), "utf-8"));

const leaves = new Map();
const groups = new Set();
(function walk(obj, prefix) {
  for (const [k, v] of Object.entries(obj)) {
    const key = `${prefix}${k}`;
    if (typeof v === "object" && v !== null) {
      groups.add(key);
      walk(v, `${key}.`);
    } else leaves.set(key, v);
  }
})(de, "");

for (const [key, value] of leaves) {
  if (typeof value !== "string" || value.trim() === "") problems.push(`empty text: ${key}`);
}

const PLURALS = ["zero", "one", "two", "few", "many", "other"];
const known = (key) => leaves.has(key) || groups.has(key) || PLURALS.some((p) => leaves.has(`${key}_${p}`));

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return files(path);
    return /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

// t("a.b"), i18n.t("a.b"), t(`a.b`) without ${...}, i18nKey="a.b"
const USES = [/\bt\(\s*"([^"]+)"/g, /\bt\(\s*'([^']+)'/g, /\bt\(\s*`([^`$]+)`/g, /i18nKey="([^"]+)"/g];
let used = 0;
for (const file of files(srcDir)) {
  const code = readFileSync(file, "utf-8");
  for (const re of USES) {
    for (const [, key] of code.matchAll(re)) {
      used++;
      if (!known(key)) problems.push(`missing in de.json: ${key} (${file.slice(srcDir.length)})`);
    }
  }
}

for (const p of problems) console.log(p);
if (problems.length) process.exit(1);
console.log(`OK: ${leaves.size} German texts, ${used} literal key uses all found`);
