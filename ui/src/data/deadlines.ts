// Texts and dates for the calendar: the backend sends kind + params, the UI writes the words.
import type { TFunction } from "i18next";
import type { Deadline } from "./api";

const DAY = 86_400_000;

export const toDate = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`);

export const addDays = (d: Date, n: number) => new Date(d.getTime() + n * DAY);

export const daysBetween = (a: Date, b: Date) => Math.round((b.getTime() - a.getTime()) / DAY);

export function monthLabel(isoMonth: string, lang: string, style: "long" | "short" = "long"): string {
  const [y, m] = isoMonth.split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "de-DE", { month: style, year: "numeric" }).format(
    new Date(y, m - 1, 1),
  );
}

/** "Runde 2 von 4 · peter", "Rezertifizierung V13.4", ... */
export function deadlineTitle(t: TFunction, d: Deadline, lang: string): string {
  const p = d.params;
  switch (d.kind) {
    case "round":
      return t("calendar.kind.round", { round: p.round, rounds: p.rounds, testCase: p.test_case });
    case "permanent":
      return t("calendar.kind.permanent", { month: monthLabel(p.month ?? d.due.slice(0, 7), lang) });
    default:
      return t(`calendar.kind.${d.kind}`, { version: p.version });
  }
}

/** Short text for a mark too small to hold the title. */
export function deadlineCode(t: TFunction, d: Deadline): string {
  return d.kind === "round" ? t("calendar.code.round", { round: d.params.round }) : t(`calendar.code.${d.kind}`);
}

/** "in 4 Tagen", "heute", "seit 3 Tagen überfällig", "erledigt" */
export function dueText(t: TFunction, d: Deadline): string {
  if (d.done) return t("calendar.due.done");
  if (d.days === 0) return t("calendar.due.today");
  return d.days > 0 ? t("calendar.due.in", { count: d.days }) : t("calendar.due.overdue", { count: -d.days });
}
