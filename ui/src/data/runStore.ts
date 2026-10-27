// State of the vendor's test runs.
// Mock mode: files are really read (parser, SHA-256), but the verdict per round is a stand-in that only
// checks that the expected messages (Abgabegründe) arrived.
// Api mode: the backend runs the round (POST /runs, /runs/{id}/submit): receipt, full rule check,
// insurer reply (TEEK0) built from the vendor's own file. The browser parser only shows the files.
import { useEffect, useSyncExternalStore } from "react";
import { decode, fieldValue, parseText, sha256, type ParsedFile } from "../records/parse";
import * as api from "./api";
import { isApi } from "./dataSource";
import { DEMO_VENDOR, RUNS } from "./mock/runs";
import type { Receipt, RoundOutcome, RunDef } from "./types";

export type UploadedFile = { name: string; parsed: ParsedFile };

export type ReplyFile = { name: string; text: string; parsed: ParsedFile };

export type RoundState = {
  receipt?: Receipt;
  files?: UploadedFile[];
  /** the vendor reported that its software produced no message */
  noMessage?: boolean;
  outcome?: RoundOutcome;
  /** api mode: the insurer reply built from the vendor's file */
  reply?: ReplyFile;
};

export type RunState = {
  /** api mode: the backend run */
  runId?: string;
  /** index of the open round */
  current: number;
  rounds: RoundState[];
  status: "running" | "passed" | "failed";
};

// Kept in the browser (localStorage), so a page reload does not lose a run.
const STORAGE_KEY = isApi ? "eel-ui-runs-api" : "eel-ui-runs";
const states = new Map<string, RunState>(Object.entries(load()));
const defs = new Map<string, RunDef>(isApi ? [] : RUNS.map((r) => [r.testCaseId, r]));
const loading = new Set<string>();
const failed = new Set<string>();
const listeners = new Set<() => void>();

function load(): Record<string, RunState> {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function save() {
  try {
    // parsed files are shown in this session only; receipts, outcomes and replies are kept
    const slim = [...states].map(([id, s]) => [
      id,
      { ...s, rounds: s.rounds.map((r) => ({ ...r, files: undefined, reply: r.reply && { ...r.reply, parsed: undefined } })) },
    ]);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(slim)));
  } catch {
    // storage blocked or full: the run still works until the next reload
  }
}

function notify() {
  listeners.forEach((l) => l());
}

function fresh(def: RunDef): RunState {
  return { current: 0, rounds: def.rounds.map(() => ({})), status: "running" };
}

export function getRunDef(id: string): RunDef | undefined {
  return defs.get(id);
}

function getState(id: string): RunState | undefined {
  const def = getRunDef(id);
  if (!def) return undefined;
  const saved = states.get(id);
  // A saved run from an older version of the test definition is started fresh.
  if (!saved || saved.rounds?.length !== def.rounds.length) states.set(id, fresh(def));
  return states.get(id);
}

function update(id: string, next: RunState) {
  states.set(id, next);
  save();
  notify();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRunState(id: string): RunState | undefined {
  return useSyncExternalStore(subscribe, () => getState(id));
}

/** The saved state of a run without loading it (status in lists). */
export function useSavedRun(id: string): RunState | undefined {
  return useSyncExternalStore(subscribe, () => states.get(id));
}

export type RunView =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; def: RunDef; state: RunState };

let views = new Map<string, RunView>();

/** The run definition and state of a test case; api mode starts or reloads the backend run. */
export function useRun(id: string): RunView {
  useEffect(() => {
    if (isApi && !defs.has(id) && !loading.has(id)) openApiRun(id);
  }, [id]);
  return useSyncExternalStore(subscribe, () => {
    const def = defs.get(id);
    const state = def && getState(id);
    const key = id;
    const prev = views.get(key);
    const next: RunView =
      def && state
        ? { status: "ready", def, state }
        : failed.has(id)
          ? { status: "error" }
          : { status: "loading" };
    // keep the same object while nothing changed (useSyncExternalStore needs a stable snapshot)
    if (prev && prev.status === next.status && (next.status !== "ready" || (prev.status === "ready" && prev.def === next.def && prev.state === next.state)))
      return prev;
    views = new Map(views).set(key, next);
    return next;
  });
}

export async function resetRun(id: string) {
  const def = getRunDef(id);
  if (!def) return;
  if (!isApi) return update(id, fresh(def));
  states.delete(id);
  defs.delete(id);
  save();
  notify();
  await openApiRun(id, true);
}

export function nextRound(id: string) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s || !def || s.status !== "running" || s.current >= def.rounds.length - 1) return;
  const outcome = s.rounds[s.current].outcome;
  // mock: only after a passed round. api: the backend keeps the run open until a required message is missing
  if (!outcome || (!isApi && !outcome.passed)) return;
  update(id, { ...s, current: s.current + 1 });
}

/** Uploads files for the open round, or `null` when the software produced no message. */
export async function submitRound(id: string, files: File[] | null) {
  if (isApi) return submitApiRound(id, files);
  const s = getState(id);
  const def = getRunDef(id);
  if (!s || !def || s.status !== "running") return;
  const round = def.rounds[s.current];

  let roundState: RoundState;
  const produced: { abgabegrund: string; datensatzId: string; azvu: string }[] = [];

  if (files === null) {
    roundState = { noMessage: true };
  } else {
    const { receipt, uploaded } = await readFiles(files);
    for (const f of uploaded)
      produced.push(
        ...f.parsed.records.map((r) => ({
          abgabegrund: r.abgabegrund,
          datensatzId: r.datensatzId,
          azvu: fieldValue(r, "DBID", "AKTENZEICHEN-VERURSACHER"),
        })),
      );
    roundState = { receipt, files: uploaded };
    if (!receipt.accepted) {
      // Rejected files are not judged; the vendor can upload again.
      const rounds = [...s.rounds];
      rounds[s.current] = roundState;
      update(id, { ...s, rounds });
      return;
    }
  }

  const expected = [...round.expects].sort();
  const got = produced.map((p) => p.abgabegrund).sort();
  const passed = expected.join(",") === got.join(",");
  const list = (codes: string[]) => (codes.length ? codes.join(" + ") : null);
  const last = produced.filter((p) => p.abgabegrund === round.expects[round.expects.length - 1]).pop();

  const outcome: RoundOutcome = {
    passed,
    label: passed ? "exact" : "bug",
    rules: passed ? round.rules.map((r) => ({ id: r.id, passed: true })) : [{ id: round.rules[0].id, passed: false }],
    message: def.hidden
      ? undefined
      : passed
        ? {
            de: `Erwartete Meldung erhalten (${list(got) ?? "keine Meldung"}). Demo-Modus: die Prüfung Feld für Feld kommt mit dem Checker.`,
            en: `Expected message received (${list(got) ?? "no message"}). Demo mode: the field-by-field check comes with the checker.`,
          }
        : {
            de: `Erwartet: ${list(expected) ?? "keine Meldung"} · Erhalten: ${list(got) ?? "keine Meldung"}`,
            en: `Expected: ${list(expected) ?? "no message"} · Received: ${list(got) ?? "no message"}`,
          },
    replyValues: last ? { REF: last.datensatzId, AZVU: last.azvu } : undefined,
  };

  const rounds = [...s.rounds];
  rounds[s.current] = { ...roundState, outcome };
  const isLast = s.current === def.rounds.length - 1;
  update(id, { ...s, rounds, status: !passed ? "failed" : isLast ? "passed" : "running" });
}

/** Reads the files in the browser: SHA-256, records, format issues (the receipt shown in mock mode). */
async function readFiles(files: File[]): Promise<{ receipt: Receipt; uploaded: UploadedFile[] }> {
  const uploaded: UploadedFile[] = [];
  const receipt: Receipt = { accepted: true, receivedAt: new Date().toISOString(), files: [], issues: [] };
  for (const file of files) {
    const bytes = await file.arrayBuffer();
    const parsed = parseText(decode(bytes));
    uploaded.push({ name: file.name, parsed });
    receipt.files.push({
      name: file.name,
      size: file.size,
      sha256: await sha256(bytes),
      records: parsed.records.map((r) => ({ abgabegrund: r.abgabegrund, datensatzId: r.datensatzId })),
    });
    receipt.issues.push(...parsed.issues.map((i) => ({ ...i, file: file.name })));
  }
  receipt.accepted = receipt.issues.length === 0;
  return { receipt, uploaded };
}

// ---------- api mode ----------

/** Rule set version -> the date the run is judged on (a day inside the version's validity). */
const VALID_ON: Record<string, string> = { "13.3": "2026-11-01", "13.4": "2027-01-01" };

async function openApiRun(id: string, forceNew = false) {
  loading.add(id);
  failed.delete(id);
  notify();
  try {
    const saved = states.get(id);
    let run: api.ApiRun | undefined;
    if (saved?.runId && !forceNew) {
      try {
        run = await api.getRun(saved.runId);
      } catch (e) {
        if (!(e instanceof api.ApiError && e.status === 404)) throw e;
        // the backend was restarted (runs live in memory): start again
      }
    }
    const curated = RUNS.find((r) => r.testCaseId === id);
    if (!run) {
      const ruleSet = curated?.ruleSet ?? "13.4";
      run = await api.startRun(id, VALID_ON[ruleSet] ?? "2027-01-01", DEMO_VENDOR);
      states.delete(id);
    }
    const def = await api.runDef(run, curated);
    defs.set(id, def);
    const prev = states.get(id);
    states.set(id, api.runState(run, def, prev?.runId === run.run_id ? prev : undefined));
    save();
  } catch {
    failed.add(id);
  } finally {
    loading.delete(id);
    notify();
  }
}

async function submitApiRound(id: string, files: File[] | null) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s?.runId || !def || s.status !== "running") return;
  const local = files ? await readFiles(files) : undefined;
  const res = await api.submitRun(s.runId, files ?? []);
  const rounds = [...s.rounds];
  const receipt = res.receipt ? api.toReceipt(res.receipt, local?.receipt) : undefined;
  if (res.rejected) {
    rounds[s.current] = { receipt, files: local?.uploaded };
    return update(id, { ...s, rounds });
  }
  const run = await api.getRun(s.runId);
  const result = run.results[run.results.length - 1];
  const reply = api.toReply(result);
  rounds[s.current] = {
    receipt,
    files: local?.uploaded,
    noMessage: files === null || undefined,
    outcome: api.toOutcome(result, def.hidden, reply),
    reply,
  };
  update(id, { ...s, rounds, status: api.toRunStatus(run.status) });
}
