// The backend API (api mode). Vite proxies /api/* to FastAPI (see vite.config.ts).
// Every function maps the backend JSON to the UI types in ./types, so the screens do not change.
import type {
  CompareMode,
  DecidedBy,
  Deviation,
  FieldRow,
  FieldStatus,
  Label,
  Localized,
  OverviewData,
  SpecRef,
  SubmissionResult,
  SubmissionSummary,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      // not JSON: keep the text
    }
    throw new ApiError(res.status, `${res.status} ${path}: ${detail}`);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export const getJson = <T>(path: string) => request<T>(path);

export const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function postForm<T>(path: string, fields: Record<string, string | undefined>, files: File[] = []) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined) form.append(k, v);
  for (const f of files) form.append("files", f, f.name);
  return request<T>(path, { method: "POST", body: form });
}

// ---------- shared mapping helpers ----------

/** Backend explanations are English only; shown as is in both languages. */
export const same = (text: string): Localized => ({ de: text, en: text });

/** Backend labels (05 section 5) to UI labels. */
export function toLabel(label: string | null | undefined): Label {
  switch (label) {
    case "exact_match":
      return "exact";
    case "correct_variant":
      return "variant";
    case "bug":
    case "invalid":
    case "unclear":
      return label;
    default:
      return "unclear";
  }
}

/** "VB@13.4#3.12/chaining" -> { document: VB, version: 13.4, section: 3.12/chaining }. */
export function toSpecRef(key: string): SpecRef {
  const [docVersion, section = ""] = key.split("#");
  const [document, version = ""] = docVersion.split("@");
  return { document: document as SpecRef["document"], version, section };
}

/** Spec passages first (VB, GG, BP), ITSG criteria (BVORERK) last; within VB a section part
 * ("3.12/chaining") before a field passage ("3.12.7"), as the report does (HANDOUT decision 20). */
export function mainSource(sources: string[]): string | undefined {
  const rank = (k: string) =>
    (k.startsWith("VB@") ? 0 : k.startsWith("GG@") ? 2 : k.startsWith("BP@") ? 3 : 4) + (k.startsWith("VB@") && !k.includes("/") ? 1 : 0);
  return [...sources].sort((a, b) => rank(a) - rank(b))[0];
}

// ---------- Overview ----------

export async function getOverview(): Promise<OverviewData> {
  type Api = Omit<OverviewData, "nextYear"> & { nextYear: OverviewData["nextYear"] | null };
  const o = await getJson<Api>("/overview");
  return {
    ...o,
    nextYear: o.nextYear ?? {
      ruleSet: "–",
      validFrom: o.checksNow.validUntil,
      specChangesInScope: 0,
      testsToReapprove: 0,
      hiddenVariantsReady: 0,
    },
  };
}

export async function getNavCounts(): Promise<{ specChanges: number; advisorQueue: number }> {
  const [o, queue] = await Promise.all([getOverview(), getJson<unknown[]>("/advisor/queue")]);
  return { specChanges: o.nextYear.specChangesInScope > 0 ? 1 : 0, advisorQueue: queue.length };
}

// ---------- Rules (titles for rule ids) ----------

type ApiRule = { id: string; title: string; description: string; sources: string[] };
const rulesCache = new Map<string, Promise<Map<string, ApiRule>>>();

export function getRules(version: string): Promise<Map<string, ApiRule>> {
  if (!rulesCache.has(version)) {
    const load = getJson<{ rules: ApiRule[] }>(`/rules?version=${encodeURIComponent(version)}`).then(
      (r) => new Map(r.rules.map((x) => [x.id, x])),
    );
    load.catch(() => rulesCache.delete(version));
    rulesCache.set(version, load);
  }
  return rulesCache.get(version)!;
}

// ---------- Submissions ----------

type ApiSubmission = {
  id: string;
  test_case_id: string;
  vendor: string | null;
  valid_on: string | null;
  rule_set_version: string | null;
  status: string;
  created: string;
  files: string[];
  label: string | null;
  rounds_total: number;
};

function toSummary(s: ApiSubmission): SubmissionSummary {
  return {
    id: s.id,
    testCaseId: s.test_case_id,
    vendor: s.vendor ?? "–",
    round: s.files.length,
    roundsTotal: Math.max(s.rounds_total, s.files.length),
    ruleSet: s.rule_set_version ?? "–",
    receivedOn: s.created.slice(0, 10),
    verdict: s.status === "rejected" ? "invalid" : toLabel(s.label),
  };
}

const listSubmissions = () => getJson<ApiSubmission[]>("/submissions");

export async function getSubmissions(): Promise<SubmissionSummary[]> {
  return (await listSubmissions()).map(toSummary);
}

// ---------- Submission result (screen 4) ----------

export type ApiDeviation = {
  id: string;
  step: number | null;
  abgabegrund: string | null;
  record: string | null;
  field: string | null;
  expected: unknown;
  actual: unknown;
  kind: string;
  label: string;
  rule: string | null;
  criterion: string | null;
  sources: string[];
  explanation: string;
  resolved_by: DecidedBy | null;
  precedent_key: string | null;
  ai_proposal: { proposal: string; reasoning: string; citations: string[]; confidence: number } | null;
};

type ApiDiffRow = {
  record: string;
  field: string;
  mode: CompareMode;
  expected: string | null;
  actual: string | null;
  same: boolean;
  label: string | null;
};

type ApiDiff = {
  submission_id: string;
  version: string;
  label: string;
  steps: { step: number; abgabegrund: string; fields: ApiDiffRow[] }[];
};

const KIND_TITLE: Record<string, Localized> = {
  value_differs: { de: "Wert weicht ab", en: "Value differs" },
  missing_block: { de: "Datenbaustein fehlt", en: "Data block missing" },
  extra_block: { de: "Zusätzlicher Datenbaustein", en: "Extra data block" },
  missing_message: { de: "Meldung fehlt", en: "Message missing" },
  extra_message: { de: "Zusätzliche Meldung", en: "Extra message" },
  missing_group: { de: "Zeitraum fehlt", en: "Period missing" },
  extra_group: { de: "Zusätzlicher Zeitraum", en: "Extra period" },
  order_differs: { de: "Reihenfolge weicht ab", en: "Order differs" },
};

export function deviationTitle(d: Pick<ApiDeviation, "kind" | "record" | "field" | "abgabegrund">): Localized {
  const base = KIND_TITLE[d.kind] ?? same(d.kind);
  const field = d.record && d.field ? `${d.record}.${d.field}` : d.record;
  const where = [d.abgabegrund, field].filter(Boolean).join(" · ");
  return where ? { de: `${base.de}: ${where}`, en: `${base.en}: ${where}` } : base;
}

const show = (v: unknown): string | null => (v === null || v === undefined ? null : String(v));

type DeviationLabel = Deviation["label"];

const devLabel = (label: string): DeviationLabel => {
  const l = toLabel(label);
  return l === "exact" ? "variant" : l;
};

function toDeviation(d: ApiDeviation, rules: Map<string, ApiRule>): Deviation {
  const rule = d.rule ? rules.get(d.rule) : undefined;
  const source = mainSource(d.sources.filter((s) => !s.startsWith("BVORERK@")));
  return {
    id: d.id,
    label: devLabel(d.label),
    title: deviationTitle(d),
    // an AI proposal alone settles nothing: the label stays unclear until the advisor decides (HANDOUT 16)
    decidedBy: d.label === "unclear" || !d.resolved_by ? "open" : d.resolved_by,
    rule: d.rule
      ? { id: d.rule, text: same(rule?.title ?? "") }
      : { id: "–", text: { de: "keine Regel deckt diese Abweichung ab", en: "no rule covers this deviation" } },
    spec: source ? toSpecRef(source) : undefined,
    criterion: d.criterion
      ? {
          id: d.criterion,
          text: { de: "ITSG-Kriterium (DTA-EEL-Beispiel Vorerkrankung)", en: "ITSG criterion (DTA-EEL-Beispiel Vorerkrankung)" },
        }
      : undefined,
    reasoning: same(d.explanation),
  };
}

/** Group fields "BEGINN-AU-2" belong to the deviation on "BEGINN-AU". */
const baseField = (field: string) => field.replace(/-\d+$/, "");

const GROUP_KINDS = new Set(["missing_group", "extra_group", "order_differs"]);

function rowStatus(row: ApiDiffRow, label: DeviationLabel | undefined): FieldStatus {
  if (label) return label;
  if (row.mode === "ignore") return "ignored";
  if (row.mode === "rule") return "valid";
  return row.same ? "identical" : "variant";
}

export async function getSubmissionResult(id: string): Promise<SubmissionResult | null> {
  const subs = await listSubmissions();
  const sub = subs.find((s) => s.id === id);
  if (!sub) return null;
  const validOn = sub.valid_on ?? new Date().toISOString().slice(0, 10);
  const q = encodeURIComponent(id);
  const [diff, check] = await Promise.all([
    getJson<ApiDiff>(`/submissions/${q}/diff?valid_on=${validOn}`),
    getJson<{ deviations: ApiDeviation[] }>(`/submissions/${q}/check`),
  ]);
  const rules = await getRules(diff.version);
  const summary = toSummary(sub);
  const deviations = check.deviations.map((d) => toDeviation(d, rules));
  const labelOf = new Map(deviations.map((d) => [d.id, d.label]));
  const used = new Set<string>();

  const fields: FieldRow[] = [];
  for (const step of diff.steps) {
    for (const row of step.fields) {
      const inStep = check.deviations.filter((d) => d.step === step.step && d.record === row.record);
      // a missing, extra or reordered period shifts the following periods and changes the count
      const dev = row.same
        ? undefined
        : (inStep.find((d) => d.field !== null && baseField(row.field) === d.field) ??
          inStep.find((d) => GROUP_KINDS.has(d.kind)));
      if (dev) used.add(dev.id);
      fields.push({
        block: `${step.abgabegrund} ${row.record}`,
        field: row.field,
        expected: row.expected?.trimEnd() ?? null,
        actual: row.actual?.trimEnd() ?? null,
        mode: row.mode,
        status: rowStatus(row, dev ? labelOf.get(dev.id) : undefined),
        deviationId: dev?.id,
      });
    }
  }
  // Deviations without a differing field row (missing message, missing block): one row each, on top.
  const extra = check.deviations
    .filter((d) => !used.has(d.id))
    .map<FieldRow>((d) => ({
      block: [d.abgabegrund, d.record].filter(Boolean).join(" ") || "–",
      field: d.field ?? KIND_TITLE[d.kind]?.en ?? d.kind,
      expected: show(d.expected),
      actual: show(d.actual),
      mode: "compare",
      status: labelOf.get(d.id)!,
      deviationId: d.id,
    }));

  return {
    ...summary,
    ruleSet: diff.version,
    verdict: toLabel(diff.label),
    fileKind: "TEEL0",
    abgabegrund: diff.steps.map((s) => s.abgabegrund).join(", "),
    fields: [...extra, ...fields],
    deviations,
  };
}
