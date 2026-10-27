// Hand-written texts of the vendor test runs (06, section 5): stories, facts and round instructions in both
// languages. The backend runs the rounds; these texts replace its generic ones where they exist.
import type { RunDef } from "./types";

export const DEMO_VENDOR = "Lohnwerk Demo GmbH";

const R41_RULES = [
  { id: "R41-1", text: { de: "41 nur mit bescheinigter AU und Vorerkrankung", en: "41 only with certified AU and prior illness" } },
  { id: "R41-2", text: { de: "41 erforderlich, wenn die Lücke höchstens 6 Monate beträgt", en: "41 required when the gap is at most 6 months" } },
  { id: "R41-3", text: { de: "Vorerkrankungen verketten, möglichst viele Zeiträume", en: "chain prior illnesses, as many periods as possible" } },
  { id: "R41-4", text: { de: "mindestens 30 Tage insgesamt", en: "at least 30 days in total" } },
];

export const RUNS: RunDef[] = [
  {
    testCaseId: "peter",
    title: { de: "Vorerkrankungskette 41, 61, 01, 61, 88, 01, 62", en: "Prior illness chain 41, 61, 01, 61, 88, 01, 62" },
    ruleSet: "13.3",
    hidden: false,
    story: {
      de: "Peter Mustermann, geboren 17.09.1983, ist ab 11.03.2026 arbeitsunfähig (eAU liegt vor). In den letzten Monaten war er viermal mit Bescheinigung krank: 14.07. bis 15.07.2025, 01.10. bis 17.10.2025, 01.12. bis 03.12.2025 und 01.03. bis 03.03.2026. Sein Arbeitsverhältnis endet am 31.03.2026.",
      en: "Peter Mustermann, born 17.09.1983, is unfit for work from 11.03.2026 (eAU available). In recent months he was ill four times with a sick note: 14.07. to 15.07.2025, 01.10. to 17.10.2025, 01.12. to 03.12.2025 and 01.03. to 03.03.2026. His employment ends on 31.03.2026.",
    },
    facts: [
      { label: { de: "AU ab", en: "AU from" }, value: "11.03.2026" },
      { label: { de: "Vorerkrankungen", en: "Prior illnesses" }, value: "4" },
      { label: { de: "Beschäftigung endet", en: "Employment ends" }, value: "31.03.2026" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: {
          de: "Erfassen Sie die AU ab 11.03.2026 und die vier Vorerkrankungen. Laden Sie die Datei hoch, die Ihre Software erzeugt.",
          en: "Enter the AU from 11.03.2026 and the four prior illnesses. Upload the file your software produces.",
        },
        expects: ["41"],
        rules: R41_RULES,
        reply: {
          abgabegrund: "61",
          fileName: "TEEK0001",
          title: { de: "Antwort der Krankenkasse: Vorerkrankungen (61)", en: "Insurer reply: prior illnesses (61)" },
        },
      },
      {
        nr: 2,
        instruction: {
          de: "Importieren Sie die 61. Ihre Software muss eine Entgeltbescheinigung 01 erzeugen.",
          en: "Import the 61. Your software must produce a benefit certificate 01.",
        },
        expects: ["01"],
        rules: [
          { id: "E-1", text: { de: "DATUM-EGZBIS = Ende der Entgeltfortzahlung (30.03.2026)", en: "DATUM-EGZBIS = end of employer-paid period (30.03.2026)" } },
          { id: "C-2", text: { de: "gleiches AKTENZEICHEN-VERURSACHER im ganzen Fall", en: "same AKTENZEICHEN-VERURSACHER across the case" } },
        ],
        reply: {
          abgabegrund: "61",
          fileName: "TEEK0002",
          title: { de: "Korrigierte 61: alle vier Zeiträume zählen", en: "Corrected 61: all four periods count" },
        },
      },
      {
        nr: 3,
        instruction: {
          de: "Importieren Sie die korrigierte 61. Erwartet werden die Stornierung 88 der alten 01 und eine neue 01.",
          en: "Import the corrected 61. Expected: cancellation 88 of the old 01 and a new 01.",
        },
        expects: ["88", "01"],
        rules: [
          { id: "E-2", text: { de: "geändertes EFZ-Ende: 88 + neue 01 (bis 27.03.2026)", en: "changed EFZ end: 88 + new 01 (until 27.03.2026)" } },
          { id: "C-3", text: { de: "88 storniert die alte 01", en: "88 cancels the old 01" } },
          { id: "C-5", text: { de: "neue 01 nach der 88", en: "new 01 after the 88" } },
        ],
        reply: {
          abgabegrund: "62",
          fileName: "TEEK0003",
          title: { de: "Antwort der Krankenkasse: Ende der Leistung (62)", en: "Insurer reply: end of benefit (62)" },
        },
      },
      {
        nr: 4,
        instruction: {
          de: "Importieren Sie die 62. Ihre Software darf keine weitere Meldung erzeugen.",
          en: "Import the 62. Your software must not produce another message.",
        },
        expects: [],
        rules: [{ id: "C-6", text: { de: "nach der 62 keine weitere Meldung", en: "no further message after the 62" } }],
      },
    ],
  },
  {
    testCaseId: "peter-gap-exact",
    title: { de: "Lücke von genau 6 Monaten (Katalog 2027)", en: "Gap of exactly 6 months (catalogue 2027)" },
    ruleSet: "13.4",
    hidden: false,
    story: {
      de: "Peter Mustermann war vom 07.08. bis 11.09.2025 mit Bescheinigung arbeitsunfähig. Ab 11.03.2026 ist er erneut arbeitsunfähig, bis 20.03.2026 (eAU liegt vor).",
      en: "Peter Mustermann was unfit for work with a sick note from 07.08. to 11.09.2025. From 11.03.2026 he is unfit for work again, until 20.03.2026 (eAU available).",
    },
    facts: [
      { label: { de: "Vorerkrankung endet", en: "Prior illness ends" }, value: "11.09.2025" },
      { label: { de: "Neue AU ab", en: "New AU from" }, value: "11.03.2026" },
      { label: { de: "Lücke in Monaten", en: "Gap in months" }, value: "6" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: {
          de: "Erfassen Sie beide Arbeitsunfähigkeiten. Laden Sie die erzeugte Datei hoch, oder melden Sie, dass Ihre Software keine Meldung erzeugt.",
          en: "Enter both periods of incapacity. Upload the file produced, or report that your software produces no message.",
        },
        expects: ["41"],
        rules: R41_RULES.slice(1, 3),
      },
    ],
  },
  {
    testCaseId: "peter-gap-exact-hidden",
    title: { de: "Stichprobe (versteckte Variante)", en: "Spot check (hidden variant)" },
    ruleSet: "13.4",
    hidden: true,
    story: {
      de: "Peter Mustermann war vom 27.07. bis 31.08.2025 mit Bescheinigung arbeitsunfähig. Ab 28.02.2026 ist er erneut arbeitsunfähig, bis 09.03.2026 (eAU liegt vor).",
      en: "Peter Mustermann was unfit for work with a sick note from 27.07. to 31.08.2025. From 28.02.2026 he is unfit for work again, until 09.03.2026 (eAU available).",
    },
    facts: [
      { label: { de: "Vorerkrankung endet", en: "Prior illness ends" }, value: "31.08.2025" },
      { label: { de: "Neue AU ab", en: "New AU from" }, value: "28.02.2026" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: {
          de: "Erfassen Sie beide Arbeitsunfähigkeiten. Laden Sie die erzeugte Datei hoch, oder melden Sie, dass Ihre Software keine Meldung erzeugt.",
          en: "Enter both periods of incapacity. Upload the file produced, or report that your software produces no message.",
        },
        expects: ["41"],
        rules: R41_RULES.slice(1, 3),
      },
    ],
  },
];
