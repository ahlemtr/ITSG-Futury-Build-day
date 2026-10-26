// Legal and procedure terms. They are always shown in German, in both languages.
// In English mode the fixed English meaning is shown as a tooltip.
// Keep this list in sync with glossary.md.
export const TERMS = {
  systemuntersuchung: { de: "Systemuntersuchung EEL", en: "system review of payroll software, EEL" },
  verfahrensbeschreibung: { de: "Verfahrensbeschreibung", en: "procedure description (the DTA EEL spec)" },
  vorerkrankung: { de: "Vorerkrankung", en: "prior illness" },
  abgabegrund: { de: "Abgabegrund", en: "message type code" },
  entgeltfortzahlung: { de: "Entgeltfortzahlung", en: "employer-paid sick period" },
  arbeitsunfaehigkeit: { de: "Arbeitsunfähigkeit", en: "incapacity for work" },
  vorbewertung: { de: "Vorbewertung", en: "preliminary evaluation (eVpT)" },
} as const;

export type TermId = keyof typeof TERMS;
