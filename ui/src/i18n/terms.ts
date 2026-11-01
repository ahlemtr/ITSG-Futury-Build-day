// Legal and procedure terms, always written this way. Keep this list in sync with glossary.md.
export const TERMS = {
  systemuntersuchung: "Systemuntersuchung EEL",
  verfahrensbeschreibung: "Verfahrensbeschreibung",
  vorerkrankung: "Vorerkrankung",
  abgabegrund: "Abgabegrund",
  entgeltfortzahlung: "Entgeltfortzahlung",
  arbeitsunfaehigkeit: "Arbeitsunfähigkeit",
  vorbewertung: "Vorbewertung",
} as const;

export type TermId = keyof typeof TERMS;
