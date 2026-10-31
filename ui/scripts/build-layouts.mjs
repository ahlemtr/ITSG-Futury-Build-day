// Converts the record layouts (layouts/*.yaml) into one JSON file the browser can read.
// Usage: npm run build:layouts   (run again when the YAML layouts change)
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import yaml from "js-yaml";

const SRC = new URL("../../layouts/", import.meta.url);
const OUT = new URL("../src/records/layouts.generated.json", import.meta.url);

const pickField = (f) => ({
  name: f.name,
  start: f.start,
  end: f.end,
  type: f.type,
  ...(f.format ? { format: f.format } : {}),
});

const layouts = {};
for (const file of readdirSync(SRC).filter((f) => f.endsWith(".yaml")).sort()) {
  const y = yaml.load(readFileSync(new URL(file, SRC), "utf-8"));
  const rg = y.repeating_group;
  layouts[y.record] = {
    record: y.record,
    title: y.title ?? "",
    status: y.status,
    fixedLength: y.fixed_length,
    fields: y.fields.map(pickField),
    ...(y.block_order ? { blockOrder: y.block_order } : {}),
    ...(rg
      ? {
          repeatingGroup: {
            countField: rg.count_field,
            startsAt: rg.starts_at,
            groupLength: rg.group_length,
            fields: rg.fields.map((f) => ({ ...pickField(f), offset: f.offset_in_group, length: f.length })),
          },
        }
      : {}),
  };
}

writeFileSync(OUT, JSON.stringify(layouts, null, 1) + "\n");
console.log(`wrote ${Object.keys(layouts).length} layouts to src/records/layouts.generated.json`);
