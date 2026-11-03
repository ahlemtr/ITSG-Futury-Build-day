// Hand-written texts of the vendor test runs (06, section 5): stories, facts and round instructions.
// The backend runs the rounds; these texts replace its generic ones where they exist.
import type { RunDef } from "./types";

export const DEMO_VENDOR = "Lohnwerk Demo GmbH";

const R41_RULES = [
  { id: "R41-1", text: "41 nur mit bescheinigter AU und Vorerkrankung" },
  { id: "R41-2", text: "41 erforderlich, wenn die Lücke höchstens 6 Monate beträgt" },
  { id: "R41-3", text: "Vorerkrankungen verketten, möglichst viele Zeiträume" },
  { id: "R41-4", text: "mindestens 30 Tage insgesamt" },
];

export const RUNS: RunDef[] = [
  {
    testCaseId: "peter",
    title: "Vorerkrankungskette 41, 61, 01, 61, 88, 01, 62",
    ruleSet: "13.3",
    hidden: false,
    story: "Peter Mustermann, geboren 17.09.1983, ist ab 11.03.2026 arbeitsunfähig (eAU liegt vor). In den letzten Monaten war er viermal mit Bescheinigung krank: 14.07. bis 15.07.2025, 01.10. bis 17.10.2025, 01.12. bis 03.12.2025 und 01.03. bis 03.03.2026. Sein Arbeitsverhältnis endet am 31.03.2026.",
    facts: [
      { label: "AU ab", value: "11.03.2026" },
      { label: "Vorerkrankungen", value: "4" },
      { label: "Beschäftigung endet", value: "31.03.2026" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: "Erfassen Sie die AU ab 11.03.2026 und die vier Vorerkrankungen. Laden Sie die Datei hoch, die Ihre Software erzeugt.",
        expects: ["41"],
        rules: R41_RULES,
        reply: {
          abgabegrund: "61",
          fileName: "TEEK0001",
          title: "Antwort der Krankenkasse: Vorerkrankungen (61)",
        },
      },
      {
        nr: 2,
        instruction: "Importieren Sie die 61. Ihre Software muss eine Entgeltbescheinigung 01 erzeugen.",
        expects: ["01"],
        rules: [
          { id: "E-1", text: "DATUM-EGZBIS = Ende der Entgeltfortzahlung (30.03.2026)" },
          { id: "C-2", text: "gleiches AKTENZEICHEN-VERURSACHER im ganzen Fall" },
        ],
        reply: {
          abgabegrund: "61",
          fileName: "TEEK0002",
          title: "Korrigierte 61: alle vier Zeiträume zählen",
        },
      },
      {
        nr: 3,
        instruction: "Importieren Sie die korrigierte 61. Erwartet werden die Stornierung 88 der alten 01 und eine neue 01.",
        expects: ["88", "01"],
        rules: [
          { id: "E-2", text: "geändertes EFZ-Ende: 88 + neue 01 (bis 27.03.2026)" },
          { id: "C-3", text: "88 nennt die stornierte 01" },
        ],
        reply: {
          abgabegrund: "62",
          fileName: "TEEK0003",
          title: "Antwort der Krankenkasse: Ende der Leistung (62)",
        },
      },
      {
        nr: 4,
        instruction: "Importieren Sie die 62. Ihre Software darf keine weitere Meldung erzeugen.",
        expects: [],
        rules: [{ id: "import-only", text: "nach der 62 keine weitere Meldung" }],
      },
    ],
  },
  {
    testCaseId: "peter-gap-exact",
    title: "Lücke von genau 6 Monaten (Katalog 2027)",
    ruleSet: "13.4",
    hidden: false,
    story: "Peter Mustermann war vom 07.08. bis 11.09.2025 mit Bescheinigung arbeitsunfähig. Ab 11.03.2026 ist er erneut arbeitsunfähig, bis 20.03.2026 (eAU liegt vor).",
    facts: [
      { label: "Vorerkrankung endet", value: "11.09.2025" },
      { label: "Neue AU ab", value: "11.03.2026" },
      { label: "Lücke in Monaten", value: "6" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: "Erfassen Sie beide Arbeitsunfähigkeiten. Laden Sie die erzeugte Datei hoch, oder melden Sie, dass Ihre Software keine Meldung erzeugt.",
        expects: ["41"],
        rules: R41_RULES.slice(1, 3),
      },
    ],
  },
  {
    testCaseId: "peter-gap-exact-hidden",
    title: "Stichprobe (versteckte Variante)",
    ruleSet: "13.4",
    hidden: true,
    story: "Peter Mustermann war vom 27.07. bis 31.08.2025 mit Bescheinigung arbeitsunfähig. Ab 28.02.2026 ist er erneut arbeitsunfähig, bis 09.03.2026 (eAU liegt vor).",
    facts: [
      { label: "Vorerkrankung endet", value: "31.08.2025" },
      { label: "Neue AU ab", value: "28.02.2026" },
    ],
    rounds: [
      {
        nr: 1,
        instruction: "Erfassen Sie beide Arbeitsunfähigkeiten. Laden Sie die erzeugte Datei hoch, oder melden Sie, dass Ihre Software keine Meldung erzeugt.",
        expects: ["41"],
        rules: R41_RULES.slice(1, 3),
      },
    ],
  },
];
