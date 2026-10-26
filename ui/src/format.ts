import type { Localized } from "./data/types";

/** 2026-10-21 -> 21.10.2026 (same in both languages). */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

export function pick(text: Localized, lang: string): string {
  return lang === "en" ? text.en : text.de;
}
