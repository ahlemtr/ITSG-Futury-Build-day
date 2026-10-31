// The backend API (api mode). Vite proxies /api/* to FastAPI (see vite.config.ts).
// Every function maps the backend JSON to the UI types in ./types, so the screens do not change.
import type {
  AdvisorItem,
  CompareMode,
  DecidedBy,
  Deviation,
  FieldRow,
  FieldStatus,
  Label,
  Localized,
  OverviewData,
  Precedent,
  Receipt,
  RoundOutcome,
  RunDef,
  SpecRef,
  SubmissionResult,
  SubmissionSummary,
} from "./types";
import i18n from "../i18n";
import { parseText } from "../records/parse";
import { upsertActivity, withAi, type ActivityStage } from "./aiActivity";
import type { NavCounts } from "./dataSource";
import type { ReplyFile, RoundState, RunState } from "./runStore";

const BASE = "/api";

// Screens load in effects, which React StrictMode runs twice in development. An AI call made while an identical
// one is still running joins it instead of reaching the model (and the overlay) a second time.
const inflight = new Map<string, Promise<unknown>>();
function shared<T>(key: string, start: () => Promise<T>): Promise<T> {
  let p = inflight.get(key) as Promise<T> | undefined;
  if (!p) {
    p = start().finally(() => inflight.delete(key));
    inflight.set(key, p);
  }
  return p;
}

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

/** A UI text in both languages (the AI overlay keeps it and follows the language switch). */
export function both(key: string, values?: Record<string, unknown>): Localized {
  return { de: i18n.getFixedT("de")(key, values), en: i18n.getFixedT("en")(key, values) };
}

/** Backend explanations are English only; shown as is in both languages. */
export const same = (text: string): Localized => ({ de: text, en: text });

/** Backend labels to UI labels. */
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
 * ("3.12/chaining") before a field passage ("3.12.7"), as the report does. */
export function mainSource(sources: string[]): string | undefined {
  const rank = (k: string) =>
    (k.startsWith("VB@") ? 0 : k.startsWith("GG@") ? 2 : k.startsWith("BP@") ? 3 : 4) + (k.startsWith("VB@") && !k.includes("/") ? 1 : 0);
  return [...sources].sort((a, b) => rank(a) - rank(b))[0];
}

// ---------- Overview ----------

export const getOverview = () => getJson<OverviewData>("/overview");

export async function getNavCounts(vendor: string): Promise<NavCounts> {
  const [o, queue, all, own] = await Promise.all([
    getOverview(),
    getJson<unknown[]>("/advisor/queue"),
    getCalendar(),
    getCalendar(vendor),
  ]);
  return {
    specChanges: o.nextYear && o.nextYear.specChangesInScope > 0 ? 1 : 0,
    advisorQueue: queue.length,
    // ITSG: its own pressing deadlines and every overdue one of a vendor; vendor: its own pressing ones
    calendar: all.deadlines.filter((d) => d.status === "overdue" || (d.company_id === null && isPressing(d))).length,
    vendorCalendar: own.deadlines.filter(isPressing).length,
  };
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
    // an AI proposal alone settles nothing: the label stays unclear until the advisor decides
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

/** "Step 1 · 41": one tab per message of the chain on the result screen. */
const messageLabel = (step: number, abgabegrund: string) => `${step} · ${abgabegrund}`;

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
        message: messageLabel(step.step, step.abgabegrund),
        block: row.record,
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
      message: d.step !== null ? messageLabel(d.step, d.abgabegrund ?? "") : undefined,
      block: d.record ?? "–",
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

// ---------- Advisor queue (screen 5) ----------

type ApiQueueItem = ApiDeviation & { submission_id: string; test_case_id: string; signature: string };

const PROPOSAL_LABEL: Record<string, DeviationLabel> = {
  likely_variant: "variant",
  likely_bug: "bug",
  unclear: "unclear",
};

export async function getAdvisorQueue(): Promise<AdvisorItem[]> {
  const [queue, subs] = await Promise.all([getJson<ApiQueueItem[]>("/advisor/queue"), listSubmissions()]);
  return queue.map((d) => {
    const sub = subs.find((s) => s.id === d.submission_id);
    const p = d.ai_proposal;
    return {
      id: d.id,
      title: deviationTitle(d),
      vendor: sub?.vendor ?? "–",
      testCaseId: d.test_case_id,
      ruleSet: sub?.rule_set_version ?? "–",
      record: d.record ?? "–",
      field: d.field ?? "*",
      kind: d.kind,
      expected: same(show(d.expected) ?? "–"),
      actual: same(show(d.actual) ?? "–"),
      proposal: p
        ? {
            label: PROPOSAL_LABEL[p.proposal] ?? "unclear",
            confidence: p.confidence,
            reasoning: same(p.reasoning),
            citations: p.citations.map(toSpecRef),
            precedents: [],
          }
        : undefined,
    };
  });
}

const DECISION_LABEL: Record<Precedent["label"], string> = { variant: "correct_variant", bug: "bug", invalid: "invalid" };

export async function decideDeviation(
  item: AdvisorItem,
  label: Precedent["label"],
  reason: string,
  advisor: string,
): Promise<Precedent> {
  const r = await postJson<{ precedent: { key: string; decided: string } }>(
    `/deviations/${encodeURIComponent(item.id)}/decide`,
    { label: DECISION_LABEL[label], reason, advisor },
  );
  return {
    id: r.precedent.key,
    signature: r.precedent.key,
    label,
    reason,
    advisor,
    at: new Date().toISOString(),
    itemTitle: item.title,
  };
}

// ---------- Vendor test runs ----------

type ApiOutcome = { rule: string; outcome: "pass" | "fail" | "review"; message?: string };

export type ApiRoundResult = {
  round: number;
  outcomes: ApiOutcome[];
  reply_name?: string | null;
  reply?: string | null;
  ended: boolean;
};

export type ApiRun = {
  run_id: string;
  test_case_id: string;
  hidden: boolean;
  version: string;
  valid_on: string;
  vendor: string | null;
  story: string;
  round: number;
  last_round: number;
  status: "open" | "passed" | "failed";
  plan: { round: number; expects?: string[]; replies?: string[] }[];
  results: ApiRoundResult[];
};

type ApiReceipt = {
  submission_id: string;
  status: string;
  files: { name: string; sha256: string; messages: string[] }[];
  issues: { file: string; record: string; field?: string | null; pos?: number | null; line?: number | null; message: string }[];
};

export const startRun = (testCaseId: string, validOn: string, vendor: string) =>
  withAi(both("ai.title.story"), postJson<ApiRun>("/runs", { test_case_id: testCaseId, valid_on: validOn, vendor }));

export const getRun = (runId: string) => getJson<ApiRun>(`/runs/${encodeURIComponent(runId)}`);

export const submitRun = (runId: string, files: File[]) =>
  withAi(both("ai.title.check"), postForm<{ status: string; receipt: ApiReceipt | null; rejected?: boolean }>(
    `/runs/${encodeURIComponent(runId)}/submit`,
    {},
    files,
  ));

const codes = (list: string[]) => list.join(" + ");

function genericInstruction(expects: string[] | undefined, hidden: boolean): Localized {
  if (hidden || expects === undefined)
    return {
      de: "Erfassen Sie den Fall laut Aufgabe. Laden Sie die erzeugte Datei hoch, oder melden Sie, dass Ihre Software keine Meldung erzeugt.",
      en: "Enter the case as described. Upload the file your software produces, or report that it produces no message.",
    };
  if (expects.length === 0)
    return {
      de: "Importieren Sie die Antwort der Krankenkasse. Ihre Software darf keine weitere Meldung erzeugen.",
      en: "Import the insurer's reply. Your software must not produce another message.",
    };
  return {
    de: `Erfassen Sie den Fall in Ihrer Software und laden Sie die erzeugte Datei hoch (erwartet: ${codes(expects)}).`,
    en: `Enter the case in your software and upload the file it produces (expected: ${codes(expects)}).`,
  };
}

/** The run as the screens know it: curated texts (runTexts.ts) where they exist, backend plan and rules otherwise. */
export async function runDef(run: ApiRun, curated?: RunDef): Promise<RunDef> {
  const rules = [...(await getRules(run.version)).values()].map((r) => ({ id: r.id, text: same(r.title) }));
  return {
    testCaseId: run.test_case_id,
    title: curated?.title ?? { de: `Testfall ${run.test_case_id}`, en: `Test case ${run.test_case_id}` },
    ruleSet: run.version,
    hidden: run.hidden,
    story: curated?.story ?? same(run.story),
    facts: curated?.facts ?? [],
    rounds: run.plan.map((p) => {
      const c = curated?.rounds[p.round - 1];
      const own = c?.rules ?? [];
      const replies = p.replies ?? [];
      return {
        nr: p.round,
        instruction: c?.instruction ?? genericInstruction(p.expects, run.hidden),
        expects: p.expects ?? c?.expects ?? [],
        rules: [...own, ...rules.filter((r) => !own.some((o) => o.id === r.id))],
        reply:
          run.hidden || replies.length === 0
            ? undefined
            : (c?.reply ?? {
                abgabegrund: codes(replies),
                fileName: `TEEK0-r${p.round}`,
                title: { de: `Antwort der Krankenkasse (${codes(replies)})`, en: `Insurer reply (${codes(replies)})` },
              }),
      };
    }),
  };
}

export const toRunStatus = (s: ApiRun["status"]): RunState["status"] => (s === "open" ? "running" : s);

export function toReply(r: ApiRoundResult): ReplyFile | undefined {
  if (!r.reply || !r.reply_name) return undefined;
  return { name: r.reply_name, text: r.reply, parsed: parseText(r.reply) };
}

export function toOutcome(r: ApiRoundResult, hidden: boolean): RoundOutcome {
  const failedOnes = r.outcomes.filter((o) => o.outcome === "fail");
  const review = r.outcomes.some((o) => o.outcome === "review");
  return {
    passed: failedOnes.length === 0,
    label: failedOnes.length ? "bug" : review ? "unclear" : "exact",
    rules: r.outcomes.map((o) => ({ id: o.rule, passed: o.outcome !== "fail" })),
    message: hidden
      ? undefined
      : failedOnes.length
        ? same(failedOnes.map((o) => `${o.rule}: ${o.message || "failed"}`).join(" · "))
        : { de: "Alle geprüften Regeln erfüllt.", en: "All checked rules passed." },
  };
}

/** Backend receipt; sizes and DATENSATZ-IDs from the browser's own reading of the same files. */
export function toReceipt(r: ApiReceipt, local?: Receipt): Receipt {
  return {
    accepted: r.status === "accepted",
    receivedAt: new Date().toISOString(),
    files: r.files.map((f) => {
      const mine = local?.files.find((x) => x.name === f.name);
      return {
        name: f.name,
        size: mine?.size ?? 0,
        sha256: f.sha256,
        records: mine?.records ?? f.messages.map((m) => ({ abgabegrund: m, datensatzId: "" })),
      };
    }),
    issues: r.issues.map((i) => ({
      file: i.file,
      line: i.line ?? 0,
      record: i.record,
      field: i.field ?? undefined,
      position: i.pos ?? undefined,
      message: same(i.message),
    })),
  };
}

/** Backend run -> screen state; receipts of this browser are kept (the backend does not return them). */
export function runState(run: ApiRun, def: RunDef, prev?: RunState): RunState {
  const rounds: RoundState[] = def.rounds.map((_, i) => {
    const result = run.results[i];
    const ui = prev?.rounds[i] ?? {};
    if (!result) return { receipt: ui.receipt };
    const reply = toReply(result);
    return { ...ui, files: undefined, outcome: toOutcome(result, run.hidden), reply };
  });
  const last = def.rounds.length - 1;
  const current =
    prev !== undefined
      ? Math.min(prev.current, last)
      : run.status === "open"
        ? Math.min(run.round, last)
        : Math.max(run.round - 1, 0);
  return { runId: run.run_id, current, rounds, status: toRunStatus(run.status) };
}

// ---------- Test catalogue ----------

export type ApiTestCase = {
  id: string;
  kind: "reference" | "clone" | "hidden";
  origin: string;
  status: "draft" | "approved" | "rejected";
  hidden: boolean;
  parent: string | null;
  targets: string[];
  steps: "single" | "chain";
  /** rule-set versions whose expected result differs from the version before */
  result_changes: string[];
};

export const getTestCases = () => getJson<ApiTestCase[]>("/test-cases");

/** Test runs the vendor can start: approved cases, curated texts where they exist. The PTA exam tasks
 * (TA 167, 168) carry inputs only and are not runnable yet (P10). */
export async function getVendorRuns(curated: RunDef[]): Promise<RunDef[]> {
  const cases = (await getTestCases()).filter((t) => t.status === "approved" && t.origin !== "pta");
  return cases.map(
    (t) =>
      curated.find((r) => r.testCaseId === t.id) ?? {
        testCaseId: t.id,
        title: { de: `Testfall ${t.id}`, en: `Test case ${t.id}` },
        ruleSet: "13.4",
        hidden: t.hidden,
        story: { de: "", en: "" },
        facts: [],
        rounds: [],
      },
  );
}

// ---------- Signed reports (screen 6) ----------

export type ReportListItem = {
  id: string;
  testCaseId: string;
  vendor: string;
  ruleSet: string;
  verdict: Label;
  receivedOn: string;
  /** ISO timestamp of the last signature, null when not signed yet */
  signed: string | null;
};

export async function getReports(vendor?: string): Promise<ReportListItem[]> {
  const q = vendor ? `?vendor=${encodeURIComponent(vendor)}` : "";
  const rows = await getJson<
    { submission_id: string; test_case_id: string; vendor: string | null; rule_set_version: string; label: string; created: string; signed: string | null }[]
  >(`/reports${q}`);
  return rows.map((r) => ({
    id: r.submission_id,
    testCaseId: r.test_case_id,
    vendor: r.vendor ?? "–",
    ruleSet: r.rule_set_version,
    verdict: toLabel(r.label),
    receivedOn: r.created.slice(0, 10),
    signed: r.signed,
  }));
}

export type ReportCheck = {
  step: number | null;
  abgabegrund: string | null;
  record: string;
  field: string | null;
  kind: string;
  outcome: string;
  expected: string | null;
  actual: string | null;
  rule: string | null;
  sources: string[];
  explanation: string;
};

export type SignedReport = {
  report: {
    submission_id: string;
    test_case_id: string;
    vendor: string | null;
    product_id: string | null;
    rule_set_version: string;
    valid_on: string;
    created: string;
    label: string;
    counts: Record<string, number>;
    expected_messages: number;
    actual_messages: number;
    files: { name: string; sha256: string }[];
    checks: ReportCheck[];
    chain: string[];
  };
  signature: { algorithm: string; json_sha256: string; value: string; public_key: string };
};

export type RuleLine = { id: string; text: string; result: "pass" | "fail" | "open"; source?: SpecRef };

export type ReportView = {
  signed: SignedReport;
  valid: boolean;
  hidden: boolean;
  rules: RuleLine[];
};

const reportPath = (id: string) => `/submissions/${encodeURIComponent(id)}/report`;
export const reportHtmlUrl = (id: string) => `${BASE}${reportPath(id)}?format=html`;

/** Signs the report (backend), verifies the signature and lists every target rule of the test case. */
export async function getReport(id: string): Promise<ReportView | null> {
  let signed: SignedReport;
  try {
    signed = await shared(`report:${id}`, () => withAi(both("ai.title.report"), getJson<SignedReport>(reportPath(id))));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
  const r = signed.report;
  const [verify, cases, rules] = await Promise.all([
    request<{ valid: boolean }>("/reports/verify", { method: "POST", body: JSON.stringify(signed) }),
    getTestCases(),
    getRules(r.rule_set_version),
  ]);
  const tc = cases.find((t) => t.id === r.test_case_id);
  const ids = [...new Set([...(tc?.targets ?? []), ...r.checks.map((c) => c.rule).filter((x): x is string => !!x)])];
  const lines: RuleLine[] = ids.map((ruleId) => {
    const checks = r.checks.filter((c) => c.rule === ruleId);
    const result = checks.some((c) => c.outcome === "bug" || c.outcome === "invalid")
      ? "fail"
      : checks.some((c) => c.outcome === "unclear")
        ? "open"
        : "pass";
    const src = mainSource(checks.flatMap((c) => c.sources).concat(rules.get(ruleId)?.sources ?? []));
    return { id: ruleId, text: rules.get(ruleId)?.title ?? "", result, source: src ? toSpecRef(src) : undefined };
  });
  // deviations no rule covers (unclear, or settled by a precedent)
  for (const c of r.checks.filter((c) => !c.rule))
    lines.push({
      id: "–",
      text: deviationTitle(c).en,
      result: c.outcome === "bug" || c.outcome === "invalid" ? "fail" : c.outcome === "unclear" ? "open" : "pass",
    });
  return { signed, valid: verify.valid, hidden: tc?.hidden ?? false, rules: lines };
}

export function downloadJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------- Spec changes (screen 2) ----------

export type SpecChange = {
  key: string;
  block: string | null;
  field: string | null;
  old: string | null;
  new: string | null;
  label: string;
  summary: string | null;
  changes_param: string[];
  modifies_old: string[];
  modifies_new: string[];
  recompute: string[];
  review: string[];
};

export type Recomputed = {
  id: string;
  old: { send_41: boolean; periods: [string, string][]; total_days: number | null };
  new: { send_41: boolean; periods: [string, string][]; total_days: number | null };
  differs: boolean;
};

export type AgentDecision = {
  change_key: string;
  test_case_id: string | null;
  decision: "no_change" | "update_test" | "new_test";
  reasoning: string;
  citations: string[];
};

export type SpecDiff = {
  oldVersion: string;
  newVersion: string;
  changes: SpecChange[];
  recomputed: Recomputed[];
  changedTests: string[];
  params: { old: Record<string, unknown>; new: Record<string, unknown> };
  agent: AgentDecision[] | null;
};

/** 13.3 vs 13.4: in-scope changes, rules and tests they touch, and the spec-update agent's drafts. */
export async function getSpecDiff(oldVersion = "13.3", newVersion = "13.4"): Promise<SpecDiff> {
  const [d, oldRules, newRules] = await Promise.all([
    shared(`specdiff:${oldVersion}:${newVersion}`, () =>
      withAi(both("ai.title.specDiff"), postJson<{
        changes: SpecChange[];
        recomputed: Recomputed[];
        changed_tests: string[];
        agent?: { decisions: AgentDecision[] } | null;
      }>("/specdiff", { document: "VB", old_version: oldVersion, new_version: newVersion })),
    ),
    getJson<{ params: Record<string, unknown> }>(`/rules?version=${oldVersion}`),
    getJson<{ params: Record<string, unknown> }>(`/rules?version=${newVersion}`),
  ]);
  return {
    oldVersion,
    newVersion,
    changes: d.changes,
    recomputed: d.recomputed,
    changedTests: d.changed_tests,
    params: { old: oldRules.params, new: newRules.params },
    agent: d.agent?.decisions ?? null,
  };
}

export type Expected = { send_41: boolean; periods: [string, string][]; total_days: number | null };

export type ChainStep = { step: number; round: number; actor: "employer" | "insurer"; abgabegrund: string; note: string | null };

export type TestCaseDetail = {
  test_case: ApiTestCase & {
    inputs: {
      report_date: string;
      employment_end: string | null;
      current: { start: string; end: string | null; certified: boolean };
      priors: { start: string; end: string; certified: boolean }[];
    };
    expected: Record<string, Expected>;
    sources: string[];
  };
  chains: Record<string, ChainStep[]>;
  submissions: string[];
};

export const getTestCase = (id: string) => getJson<TestCaseDetail>(`/test-cases/${encodeURIComponent(id)}`);

export const approveTestCase = (id: string, decision: "approved" | "rejected", approver = "ITSG") =>
  postJson<{ id: string; status: string }>(`/test-cases/${encodeURIComponent(id)}/approve`, { approver, decision });

export const draftHidden = (id: string) => postJson<{ id: string }>("/builder/hidden", { test_case_id: id, seed: 0 });


// ---------- Spec upload ----------

export type ApiJob = {
  id: string;
  document: string;
  version: string;
  valid_from: string;
  previous?: string | null;
  file: string;
  status: "running" | "done" | "failed";
  created: string;
  stages: { name: string; title: string; status: ActivityStage["status"]; counts: Record<string, unknown> }[];
  result: {
    flipped?: string[];
    drafts?: string[];
    rules?: string[];
    rechecked?: number;
    track?: "now" | "next";
    /** Rundschreiben: calculation rules found (drafts: need implementation) and proposals for engine parameters */
    calculation_rules?: string[];
    parameter_proposals?: { parameter: string; current: unknown; proposed: unknown; rule: string }[];
  };
  error: string | null;
};

export type SpecVersion = { document: string; version: string; valid_from: string | null; succeeds: string | null };

export const getVersions = (document = "VB") => getJson<SpecVersion[]>(`/versions?document=${encodeURIComponent(document)}`);
export const getJobs = () => getJson<ApiJob[]>("/jobs");

export function uploadSpec(file: File, fields: { document: string; version?: string; validFrom?: string }) {
  const form = new FormData();
  form.append("file", file, file.name);
  form.append("document", fields.document);
  if (fields.version) form.append("version", fields.version);
  if (fields.validFrom) form.append("valid_from", fields.validFrom);
  return request<ApiJob>("/spec-versions", { method: "POST", body: form });
}

const STAGE_KEYS: Record<string, string> = {
  store: "spec.stage.store", chunk: "spec.stage.chunk", embed: "spec.stage.embed", diff: "spec.stage.diff",
  map: "spec.stage.map", analyse: "spec.stage.analyse", apply: "spec.stage.apply", catalogue: "spec.stage.catalogue",
};

/** Polls the job and mirrors it in the AI overlay until it is done; resolves with the final job. */
export async function trackJob(job: ApiJob): Promise<ApiJob> {
  const startedAt = Date.parse(job.created) || Date.now();
  const title = both("ai.title.specUpload", { doc: job.document, version: job.version });
  for (;;) {
    upsertActivity({
      id: job.id,
      title,
      startedAt,
      status: job.status,
      error: job.error ?? undefined,
      stages: job.stages.map((st) => ({ name: st.name, title: both(STAGE_KEYS[st.name] ?? st.title), status: st.status, counts: st.counts })),
    });
    if (job.status !== "running") return job;
    await new Promise((r) => setTimeout(r, 1000));
    job = await getJson<ApiJob>(`/jobs/${encodeURIComponent(job.id)}`);
  }
}

// ---------- Knowledge graph tab ----------

export type KgStats = {
  backend: "neo4j" | "yaml";
  nodes: Record<string, number>;
  total_nodes: number;
  edges: number | null;
  embedded_chunks: number;
  versions: string[];
};

export type KgEvent = {
  at: string;
  kind: string;
  document?: string;
  version?: string;
  valid_from?: string;
  passages?: number;
  changes?: number;
  in_scope?: number;
  parameters_changed?: string[];
  tests_flipped?: string[];
  drafts?: string[];
  signature?: string;
  label?: string;
  test_cases?: number;
};

export type KgNode = { label: string; key: string; props: Record<string, unknown> };
export type KgEdge = { type: string; from_label: string; from_key: string; to_label: string; to_key: string };

export type KgAnswer = {
  query: string;
  results: { passage: { key: string; heading: string; snippet: string | null }; rules: string[]; changes: string[]; tests: string[] }[];
};

export const getKgStats = () => getJson<KgStats>("/kg/stats");
export const getKgEvents = () => getJson<KgEvent[]>("/kg/events");
export const getSubgraph = (label: string, key: string, depth = 1) =>
  getJson<{ nodes: KgNode[]; edges: KgEdge[] }>(
    `/graph/subgraph?label=${encodeURIComponent(label)}&key=${encodeURIComponent(key)}&depth=${depth}`,
  );
export const askGraph = (q: string) => getJson<KgAnswer>(`/kg/ask?q=${encodeURIComponent(q)}`);

// ---------- Calendar (deadlines per vendor company) ----------

export type DeadlineKind = "round" | "update" | "permanent" | "catalogue" | "switch";
export type DeadlineStatus = "done" | "overdue" | "soon" | "open";

export type Company = {
  id: string;
  name: string;
  product: string | null;
  certified_until: string | null;
  /** null: new software, not certified yet */
  certified_for: string | null;
  /** progress over the approved catalogue while not certified */
  first_certification: { tests: number; passed: number } | null;
};

export type Deadline = {
  id: string;
  /** null = ITSG */
  company_id: string | null;
  kind: DeadlineKind;
  due: string;
  opened: string | null;
  ref: string | null;
  params: { round?: number; rounds?: number; test_case?: string; hidden?: boolean; version?: string; month?: string; drafts?: number; tests?: number; passed?: number };
  done: boolean;
  done_on: string | null;
  status: DeadlineStatus;
  /** days from today to the due date, negative when past */
  days: number;
};

export type CatalogueEvent =
  | { at: string; kind: "baseline"; version: string; tests: number }
  | { at: string; kind: "spec_upload"; document: string; version: string; valid_from: string; changes: number; drafts: number; flipped: number }
  | { at: string; kind: "approval"; test_case: string; decision: "approved" | "rejected" };

export type CalendarData = { today: string; companies: Company[]; deadlines: Deadline[]; history: CatalogueEvent[] };

/** All companies (ITSG), or one company by id or name (vendor view). */
export const getCalendar = (company?: string) =>
  getJson<CalendarData>(company ? `/calendar?company=${encodeURIComponent(company)}` : "/calendar");

/** Needs attention: overdue, or due within a week. */
export const isPressing = (d: Deadline) => d.status === "overdue" || d.status === "soon";

// ---------- Demo reset (user menu) ----------

export type ResetJob = {
  id: string;
  status: "running" | "done" | "failed";
  created: string;
  stages: { name: string; status: ActivityStage["status"]; counts: Record<string, unknown> }[];
  error: string | null;
};

export const getResetStatus = () => getJson<{ allowed: boolean; job: ResetJob | null }>("/admin/reset");

/** Starts the reset and mirrors it in the AI overlay until it is done; resolves with the final job. */
export async function resetAll(): Promise<ResetJob> {
  let job = await postJson<ResetJob>("/admin/reset", {});
  const startedAt = Date.parse(job.created) || Date.now();
  const title = both("admin.reset.job");
  for (;;) {
    upsertActivity({
      id: job.id,
      title,
      startedAt,
      status: job.status,
      error: job.error ?? undefined,
      stages: job.stages.map((st) => ({ name: st.name, title: both(`admin.reset.stage.${st.name}`), status: st.status, counts: st.counts })),
    });
    if (job.status !== "running") return job;
    await new Promise((r) => setTimeout(r, 1000));
    job = (await getResetStatus()).job ?? job;
  }
}
