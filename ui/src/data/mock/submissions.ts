// Demo data, made up from the plan documents (no ITSG file content).
// Scenario: Peter Mustermann, round 1 (the 41). The vendor lists 3 of the 4 prior periods.
import type { FieldRow, SubmissionResult, SubmissionSummary } from "../types";

const same = (block: string, field: string, value: string | null): FieldRow => ({
  block,
  field,
  expected: value,
  actual: value,
  mode: "compare",
  status: "identical",
});

const ignored = (
  block: string,
  field: string,
  expected: string | null,
  actual: string | null,
  note: FieldRow["note"],
  section: string,
): FieldRow => ({
  block,
  field,
  expected,
  actual,
  mode: "ignore",
  status: "ignored",
  note,
  source: { document: "VB", version: "13.3", section },
});

const rule = (
  block: string,
  field: string,
  expected: string | null,
  actual: string | null,
  note: FieldRow["note"],
  section: string,
): FieldRow => ({
  block,
  field,
  expected,
  actual,
  mode: "rule",
  status: "valid",
  note,
  source: { document: "VB", version: "13.3", section },
});

const DBAP_NOTE = {
  de: "Ansprechpartner des Absenders. Wird nicht verglichen, nur geprüft: vorhanden, wenn MM-ANSPRECH = J (Annahme, die Spec hat keine Tabelle).",
  en: "Sender's contact person. Not compared, only checked: present when MM-ANSPRECH = J (assumption, the spec has no table).",
};

const MM_FLAGS: [string, string][] = [
  ["MM-NAME", "J"],
  ["MM-ANSCHRIFT", "N"],
  ["MM-ALLGEMEIN", "N"],
  ["MM-ENTGELT", "N"],
  ["MM-ZEITKG", "N"],
  ["MM-EELENDE", "N"],
  ["MM-FEHLZEIT", "N"],
  ["MM-FREISTELL", "N"],
  ["MM-UNFALL", "N"],
  ["MM-ENTMU", "N"],
  ["MM-VOER", "J"],
  ["MM-HOEENT", "N"],
  ["MM-BEIEIN", "N"],
  ["MM-UEGLTA", "N"],
  ["MM-ENTSEE", "N"],
  ["MM-TRAKUG", "N"],
  ["MM-ANSPRECH", "J"],
  ["MM-ID", "J"],
  ["MM-SD", "N"],
];

// Prior periods of the expected 41, newest first. The vendor left out number 2.
const PERIODS = [
  { nr: "01", start: "01.03.2026", end: "03.03.2026", vendorNr: "01" },
  { nr: "02", start: "01.12.2025", end: "03.12.2025", vendorNr: null },
  { nr: "03", start: "01.10.2025", end: "17.10.2025", vendorNr: "02" },
  { nr: "04", start: "14.07.2025", end: "15.07.2025", vendorNr: "03" },
];

function periodRows(): FieldRow[] {
  return PERIODS.flatMap((p) => {
    const values: [string, string][] = [
      ["BEGINN-AU", p.start],
      ["ENDE-AU", p.end],
      ["KZ-NACHWEIS", "0"],
      ["KZ-AU", "0"],
    ];
    return values.map(([name, value]): FieldRow => {
      const field = `${name}-${p.nr}`;
      if (p.vendorNr === null) {
        return {
          block: "DBVO",
          field,
          expected: value,
          actual: null,
          mode: "compare",
          status: "variant",
          deviationId: "d-periods",
        };
      }
      const row = same("DBVO", field, value);
      return p.vendorNr === p.nr ? row : { ...row, vendorField: `${name}-${p.vendorNr}` };
    });
  });
}

const peterRound1: SubmissionResult = {
  id: "2026-10-021",
  testCaseId: "peter",
  vendor: "Lohnwerk Demo GmbH",
  round: 1,
  roundsTotal: 4,
  ruleSet: "13.3",
  receivedOn: "2026-10-21",
  verdict: "variant",
  fileKind: "TEEL0",
  abgabegrund: "41",
  deviations: [
    {
      id: "d-periods",
      label: "variant",
      title: { de: "DBVO listet 3 von 4 Zeiträumen", en: "DBVO lists 3 of 4 periods" },
      decidedBy: "catalogue",
      rule: {
        id: "R41-3",
        text: {
          de: "mindestens ein Zeitraum, möglichst viele",
          en: "at least one period, as many as possible",
        },
      },
      spec: { document: "VB", version: "13.3", section: "3.12", title: "DBVO Vorerkrankungen" },
      criterion: {
        id: "aade0289-e8f9-4e12-9c49-464cf6cd0789",
        text: {
          de: "Eines der 4 Vorerkrankungs-Kriterien (DTA-EEL-Beispiel)",
          en: "One of the 4 Vorerkrankung criteria (DTA-EEL example)",
        },
      },
      reasoning: {
        de: "Die Musterlösung listet 4 Vorerkrankungszeiten, die Herstellerdatei 3. Es fehlt der Zeitraum 01.12.2025 bis 03.12.2025. Die Regel verlangt mindestens einen Zeitraum, alle gelisteten Zeiträume sind korrekt und neueste zuerst sortiert. Bekannte zulässige Variante aus dem Katalog.",
        en: "The model solution lists 4 prior illness periods, the vendor file 3. The period 01.12.2025 to 03.12.2025 is missing. The rule requires at least one period; all listed periods are correct and sorted newest first. Known correct variant from the catalogue.",
      },
    },
  ],
  fields: [
    // DSLW fixed part
    same("DSLW", "KENNUNG", "DSLW"),
    same("DSLW", "VERFAHREN", "LEIST"),
    rule(
      "DSLW",
      "ABSENDERNUMMER",
      "99301347",
      "99307001",
      {
        de: "Betriebsnummer des Erstellers. Jeder Hersteller hat eine eigene eVpT-Testnummer. Regel: gleich der Testnummer des Herstellers.",
        en: "Creator's company number. Each vendor has its own eVpT test number. Rule: equals the vendor's test number.",
      },
      "3.1.2",
    ),
    same("DSLW", "EMPFAENGERNUMMER", "00000000"),
    same("DSLW", "VERSION-NR", "13"),
    ignored(
      "DSLW",
      "DATUM-ERSTELLUNG",
      "20261015093000000000",
      "20261021141207000000",
      { de: "Erstellungszeitpunkt, bei jedem Lauf anders.", en: "Creation time, different on every run." },
      "3.1.5",
    ),
    same("DSLW", "FEHLER-KENNZ", "0"),
    same("DSLW", "FEHLER-ANZAHL", "0"),
    same("DSLW", "VSNR", "65170983M003"),
    same("DSLW", "GEBURTSDAT", "17.09.1983"),
    same("DSLW", "BBNR-VU", "34567890"),
    rule(
      "DSLW",
      "DATENSATZ-ID",
      "3f6c1a2e-8b4d-4e7a-9c15-2d7e0b9a4f11",
      "a91e5c07-2f3b-4d68-b0e4-7c1d9f2a6e35",
      {
        de: "UUID, vom Ersteller erzeugt. Regel: gültiges UUID-Format, nie wiederverwendet.",
        en: "UUID generated by the creator. Rule: valid UUID format, never reused.",
      },
      "3.1.11",
    ),
    rule(
      "DSLW",
      "PRODUKT-IDENTIFIER",
      "P000001",
      "L204711",
      {
        de: "Von der ITSG je zertifiziertem Programm vergeben. Regel: gleich dem geprüften Produkt.",
        en: "Assigned by ITSG per certified program. Rule: equals the product under test.",
      },
      "3.1.12",
    ),
    rule(
      "DSLW",
      "MODIFIKATIONS-IDENTIFIER",
      "00000001",
      "26100300",
      {
        de: "Produktversion. Regel: passt zur eingereichten Version.",
        en: "Product version. Rule: matches the submitted version.",
      },
      "3.1.13",
    ),
    ignored(
      "DSLW",
      "DATUM-VERARBEITUNG",
      null,
      null,
      {
        de: "Wird von der Datenannahmestelle beim Weiterleiten gesetzt.",
        en: "Set by the data acceptance point when forwarding.",
      },
      "3.1.14",
    ),
    same("DSLW", "BBNR-KK", "99300660"),
    same("DSLW", "BBNR-ABRECHNUNGSSTELLE", null),
    same("DSLW", "ABGABEGRUND", "41"),
    same("DSLW", "KORR-ABGABEGRUND", "00"),
    rule(
      "DSLW",
      "ABRECHNUNGSPROGRAMM",
      "1",
      "1",
      {
        de: "1 Entgeltabrechnung, 2 Ausfüllhilfe, 3 Zeiterfassung. Regel: passt zur Produktart.",
        en: "1 payroll, 2 filling aid, 3 time recording. Rule: matches the product type.",
      },
      "3.1.20",
    ),
    ...MM_FLAGS.map(([field, value]) => same("DSLW", field, value)),

    // DBNA
    same("DBNA", "FAMILIENNAME", "Mustermann"),
    same("DBNA", "VORNAME", "Peter"),

    // DBVO header
    same("DBVO", "GRUNDAV", "1"),
    same("DBVO", "AU-AB-AG", "11.03.2026"),
    same("DBVO", "AU-AB-SV", null),
    same("DBVO", "KZ-AK-AU", "0"),
    same("DBVO", "12-MONATSFRIST-AB", null),
    {
      block: "DBVO",
      field: "ANZAHL-AU",
      expected: "04",
      actual: "03",
      mode: "compare",
      status: "variant",
      deviationId: "d-periods",
    },
    ...periodRows(),

    // DBAP
    rule("DBAP", "NAME", "Max Prüfer", "Lena Beispiel", DBAP_NOTE, "3.18"),
    rule("DBAP", "TELEFON", "030 0000000", "0201 1234567", DBAP_NOTE, "3.18"),
    rule("DBAP", "EMAIL", "pruefung@testfirma.example", "lohn@lohnwerk-demo.example", DBAP_NOTE, "3.18"),
    rule("DBAP", "FIRMA-1", "Testfirma Systemprüfung", "Lohnwerk Demo GmbH", DBAP_NOTE, "3.18"),
    rule("DBAP", "PLZ", "10115", "45127", DBAP_NOTE, "3.18"),
    rule("DBAP", "ORT", "Berlin", "Essen", DBAP_NOTE, "3.18"),

    // DBID
    ignored(
      "DBID",
      "AKTENZEICHEN-SV",
      null,
      null,
      { de: "Frei für die Einzugsstelle (Kassenseite).", en: "Free for the collecting agency (insurer side)." },
      "3.19.1",
    ),
    rule(
      "DBID",
      "AKTENZEICHEN-VERURSACHER",
      "PN-000001",
      "PN-004711",
      {
        de: "Frei für den Ersteller, z. B. Personalnummer. Regel: im ganzen Fall gleich, von der Kasse zurückgegeben.",
        en: "Free for the creator, e.g. personnel number. Rule: identical across the case, echoed by the insurer.",
      },
      "3.19.2",
    ),
    rule(
      "DBID",
      "REFERENZ-ID",
      null,
      null,
      {
        de: "Verweist auf die beantwortete Meldung. Die 41 beantwortet keine Meldung, also leer.",
        en: "Points to the message answered. The 41 answers no message, so it is empty.",
      },
      "3.19.3",
    ),
  ],
};

export const SUBMISSION_RESULTS: SubmissionResult[] = [peterRound1];

export const SUBMISSIONS: SubmissionSummary[] = SUBMISSION_RESULTS.map((s) => ({
  id: s.id,
  testCaseId: s.testCaseId,
  vendor: s.vendor,
  round: s.round,
  roundsTotal: s.roundsTotal,
  ruleSet: s.ruleSet,
  receivedOn: s.receivedOn,
  verdict: s.verdict,
}));
