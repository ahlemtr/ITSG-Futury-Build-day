// Data shapes the UI expects. The backend API should send the same shapes,
// so switching from mock to api needs no screen changes.

/** Text the backend provides in both languages (e.g. explanations). */
export type Localized = { de: string; en: string };

/** Result label of a deviation or a whole submission (doc 05, section 5). */
export type Label = "exact" | "variant" | "bug" | "invalid" | "unclear";

/** How a field is compared with the model solution (doc 05, section 4). */
export type CompareMode = "compare" | "ignore" | "rule";

/** Result of one field: no deviation (identical / ignored / valid rule field) or a deviation label. */
export type FieldStatus = "identical" | "ignored" | "valid" | Exclude<Label, "exact">;

/** Which analysis step settled a deviation (doc 05, section 6). */
export type DecidedBy = "diff" | "catalogue" | "rules" | "ai_proposal" | "advisor";

/** VB = Verfahrensbeschreibung, GG = Gemeinsame Grundsätze, BP = Beispielpapier. */
export type SpecRef = {
  document: "VB" | "GG" | "BP";
  version: string;
  section: string;
  title?: string;
};

export type Deviation = {
  id: string;
  label: Exclude<Label, "exact">;
  title: Localized;
  decidedBy: DecidedBy;
  rule: { id: string; text: Localized };
  spec: SpecRef;
  criterion?: { id: string; text: Localized };
  reasoning: Localized;
};

export type FieldRow = {
  block: string;
  field: string;
  /** null = not present in that file */
  expected: string | null;
  actual: string | null;
  mode: CompareMode;
  status: FieldStatus;
  /** set when this row belongs to a deviation */
  deviationId?: string;
  /** vendor's field name when matching paired it with a differently numbered field */
  vendorField?: string;
  /** why the field is ignored or checked by rule */
  note?: Localized;
  source?: SpecRef;
};

export type SubmissionSummary = {
  id: string;
  testCaseId: string;
  vendor: string;
  round: number;
  roundsTotal: number;
  ruleSet: string;
  /** ISO date, e.g. 2026-10-21 */
  receivedOn: string;
  verdict: Label;
};

// ---------- Vendor view: test runs in rounds (06, section 5) ----------

export type RuleRef = { id: string; text: Localized };

export type ReplyDef = {
  abgabegrund: string;
  fileName: string;
  title: Localized;
  /** values "{REF}" / "{AZVU}" are filled from the vendor's own file */
  rows: { field: string; value: string; note?: Localized }[];
};

export type RoundDef = {
  nr: number;
  instruction: Localized;
  /** Abgabegründe the software must produce; [] = no message (import only) */
  expects: string[];
  rules: RuleRef[];
  reply?: ReplyDef;
};

export type RunDef = {
  testCaseId: string;
  title: Localized;
  ruleSet: string;
  /** hidden variant: the vendor gets the story only, never expected values */
  hidden: boolean;
  story: Localized;
  facts: { label: Localized; value: string }[];
  rounds: RoundDef[];
};

/** Like eVpT's processing confirmation. */
export type Receipt = {
  accepted: boolean;
  /** ISO timestamp */
  receivedAt: string;
  files: {
    name: string;
    size: number;
    sha256: string;
    records: { abgabegrund: string; datensatzId: string }[];
  }[];
  issues: { file: string; line: number; record: string; field?: string; position?: number; message: Localized }[];
};

export type RoundOutcome = {
  passed: boolean;
  label: Label;
  rules: { id: string; passed: boolean }[];
  /** shown for public tests only */
  message?: Localized;
  /** filled reply rows (public: shown, hidden runs never have replies) */
  replyValues?: { REF: string; AZVU: string };
};

/** Figures for the Overview: one catalogue, today's and next year's rule version (06, section 3). */
export type OverviewData = {
  checksNow: {
    ruleSet: string;
    /** ISO date */
    validUntil: string;
    /** ISO month, e.g. 2026-10 */
    month: string;
    submissions: number;
    passedAllRules: number;
    withOpenDeviations: number;
  };
  nextYear: {
    ruleSet: string;
    /** ISO date */
    validFrom: string;
    specChangesInScope: number;
    testsToReapprove: number;
    hiddenVariantsReady: number;
  };
  /** Who settled this month's deviations (the pitch metric, doc 05 section 6). */
  resolution: {
    catalogueAndRules: number;
    aiConfirmedByAdvisor: number;
    waitingForAdvisor: number;
  };
};

export type SubmissionResult = SubmissionSummary & {
  fileKind: "TEEL0" | "TEEK0";
  abgabegrund: string;
  fields: FieldRow[];
  deviations: Deviation[];
};
