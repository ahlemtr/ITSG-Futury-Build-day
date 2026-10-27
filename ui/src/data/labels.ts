// Readable names for the platform's technical identifiers: engine parameters and their values, deviation
// kinds, precedent signatures, graph node types. Every screen shows identifiers through these functions, so a
// new parameter, kind or node type gets a readable name by default (`humanize`) and a proper one by adding a
// key under `labels` in i18n/*.json. Field and block names of the Verfahrensbeschreibung (DBVO, BEGINN-AU)
// are legal terms and stay as they are.
import type { TFunction } from "i18next";

/** gap_inclusive -> "Gap inclusive", MissingBlock -> "Missing block": the fallback for names without a label. */
export function humanize(id: string): string {
  const words = id
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_]+/g, " ")
    .trim()
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** "Lücke von genau 6 Monaten verkettet" for gap_inclusive. */
export const paramLabel = (t: TFunction, name: string) => t(`labels.param.${name}`, { defaultValue: humanize(name) });

/** A parameter value in words: true -> "ja", 6 -> "6 Monate" (with the parameter's unit when it has one). */
export function paramValue(t: TFunction, name: string, value: unknown): string {
  if (value === undefined || value === null) return "–";
  if (typeof value === "boolean") return t(value ? "labels.yes" : "labels.no");
  return t(`labels.unit.${name}`, { value: String(value), defaultValue: String(value) });
}

/** "Lücke von genau 6 Monaten verkettet: nein → ja" */
export const paramChange = (t: TFunction, name: string, before: unknown, after: unknown) =>
  `${paramLabel(t, name)}: ${paramValue(t, name, before)} → ${paramValue(t, name, after)}`;

/** missing_block -> "Block fehlt" */
export const deviationKind = (t: TFunction, kind: string) => t(`labels.kind.${kind}`, { defaultValue: humanize(kind) });

/** correct_variant -> "Zulässige Variante" (the result labels of the checker and the advisor). */
export function outcomeLabel(t: TFunction, label: string): string {
  const key = { exact_match: "exact", correct_variant: "variant", likely_variant: "variant", likely_bug: "bug" }[label] ?? label;
  return t(`status.${key}`, { defaultValue: humanize(label) });
}

/** "41|DSLW.MM-ANSPRECH|missing_block" -> "Meldung 41 · DSLW.MM-ANSPRECH · Block fehlt" */
export function signatureLabel(t: TFunction, signature: string): string {
  const [abgabegrund, where, kind] = signature.split("|");
  if (!kind) return signature;
  return [t("labels.message", { code: abgabegrund }), where && where !== "*" ? where : null, deviationKind(t, kind)]
    .filter(Boolean)
    .join(" · ");
}

/** Rule, Passage, ParamValue -> "Regel", "Passage", "Parameterwert" (graph node types). */
export const nodeType = (t: TFunction, label: string) => t(`labels.node.${label}`, { defaultValue: humanize(label) });
