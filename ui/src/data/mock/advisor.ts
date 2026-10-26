// Demo items for the advisor queue. Each one is a real open question of the plan
// (00, section 9: questions 11 and 12) or the s-no-contact seed case (02, section 7).
import type { AdvisorItem } from "../types";

export const ADVISOR_ITEMS: AdvisorItem[] = [
  {
    id: "q-dbap",
    title: { de: "DBAP fehlt auf einer 41, MM-ANSPRECH = N", en: "DBAP missing on a 41, MM-ANSPRECH = N" },
    vendor: "Abrechnung Süd Demo",
    testCaseId: "peter",
    ruleSet: "13.3",
    record: "DBAP",
    field: "*",
    kind: "block-missing",
    expected: { de: "DBAP vorhanden, MM-ANSPRECH = J", en: "DBAP present, MM-ANSPRECH = J" },
    actual: { de: "DBAP fehlt, MM-ANSPRECH = N", en: "DBAP absent, MM-ANSPRECH = N" },
    proposal: {
      label: "bug",
      confidence: 0.71,
      reasoning: {
        de: "Im Beispielpapier trägt jede 41 MM-ANSPRECH = J mit einem DBAP. Ob DBAP je Abgabegrund Pflicht ist, regelt Anlage 3 der Verfahrensbeschreibung, die nicht vorliegt. Die Herstellerdatei ist in sich stimmig (Flag N, kein Baustein), weicht aber vom Beispiel ab.",
        en: "In the Beispielpapier every 41 carries MM-ANSPRECH = J with a DBAP. Whether DBAP is mandatory per Abgabegrund is set by Anlage 3 of the Verfahrensbeschreibung, which is not available. The vendor file is consistent in itself (flag N, no block) but differs from the example.",
      },
      citations: [
        { document: "BP", version: "13.3", section: "13.1" },
        { document: "VB", version: "13.4", section: "3.18", title: "DBAP" },
      ],
      precedents: [],
    },
  },
  {
    id: "q-dban",
    title: { de: "MM-ANSCHRIFT = J mit DBAN auf einer 41", en: "MM-ANSCHRIFT = J with DBAN on a 41" },
    vendor: "Lohnservice Ost Demo",
    testCaseId: "peter",
    ruleSet: "13.3",
    record: "DSLW",
    field: "MM-ANSCHRIFT",
    kind: "flag-differs",
    expected: { de: "MM-ANSCHRIFT = N, kein DBAN", en: "MM-ANSCHRIFT = N, no DBAN" },
    actual: { de: "MM-ANSCHRIFT = J, DBAN vorhanden", en: "MM-ANSCHRIFT = J, DBAN present" },
    proposal: {
      label: "variant",
      confidence: 0.64,
      reasoning: {
        de: "Beispielpapier 13.1 setzt auf einer 41 MM-ANSCHRIFT = J und sendet DBAN, die Referenzdatei der ITSG sendet N. Beide Formen stehen in offiziellem Material; der Hersteller folgt dem Beispielpapier.",
        en: "Beispielpapier 13.1 sets MM-ANSCHRIFT = J on a 41 and sends DBAN, ITSG's reference file sends N. Both forms appear in official material; the vendor follows the Beispielpapier.",
      },
      citations: [
        { document: "BP", version: "13.3", section: "13.1" },
        { document: "VB", version: "13.4", section: "3.3", title: "DBAN" },
      ],
      precedents: [],
    },
  },
  {
    id: "q-kurz-au",
    title: { de: "Kurz-AU mit folgender AU zusammengefasst", en: "Kurz-AU merged with the following AU" },
    vendor: "Gehaltsprofi Demo",
    testCaseId: "peter-kurz-au",
    ruleSet: "13.3",
    record: "DBVO",
    field: "BEGINN-AU",
    kind: "date-earlier",
    expected: { de: "Zeitraum 01.10.2025 – 17.10.2025 (nur bescheinigter Teil)", en: "Period 01.10.2025 – 17.10.2025 (certified part only)" },
    actual: { de: "Zeitraum 29.09.2025 – 17.10.2025 (Kurz-AU 29.09. – 30.09. eingeschlossen)", en: "Period 29.09.2025 – 17.10.2025 (Kurz-AU 29.09. – 30.09. included)" },
    proposal: {
      label: "unclear",
      confidence: 0.48,
      reasoning: {
        de: "Nach VB 3.12 zählt eine Kurz-AU ohne Bescheinigung, wenn sich eine bescheinigte AU nahtlos anschließt. Offen ist, ob sie dann mit der AU zu einem Zeitraum zusammengefasst oder nur der bescheinigte Teil gemeldet wird. Keine Regel und kein Präzedenzfall entscheidet das.",
        en: "Under VB 3.12 an uncertified Kurz-AU counts when a certified AU follows seamlessly. It is open whether it is then merged with the AU into one period or only the certified part is listed. No rule or precedent settles it.",
      },
      citations: [{ document: "VB", version: "13.4", section: "3.12", title: "DBVO Vorerkrankungen" }],
      precedents: [],
    },
  },
];

/** Precedent ids continue from the ones already stored (P-001 .. P-013). */
export const NEXT_PRECEDENT_NUMBER = 14;
