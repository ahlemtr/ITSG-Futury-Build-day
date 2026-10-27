// State of the vendor's test runs. The backend runs every round (POST /runs, /runs/{id}/submit): receipt,
// full rule check, insurer reply (TEEK0) built from the vendor's own file. The browser parser only shows
// the uploaded files field by field.
import { useEffect, useSyncExternalStore } from "react";
import { decode, parseText, sha256, type ParsedFile } from "../records/parse";
import * as api from "./api";
import { DEMO_VENDOR, RUNS } from "./runTexts";
import type { Receipt, RoundOutcome, RunDef } from "./types";

export type UploadedFile = { name: string; parsed: ParsedFile };

export type ReplyFile = { name: string; text: string; parsed: ParsedFile };

export type RoundState = {
  receipt?: Receipt;
  files?: UploadedFile[];
  /** the vendor reported that its software produced no message */
  noMessage?: boolean;
  outcome?: RoundOutcome;
  /** the insurer reply built from the vendor's file */
  reply?: ReplyFile;
};

export type RunState = {
  /** the backend run */
  runId?: string;
  /** index of the open round */
  current: number;
  rounds: RoundState[];
  status: "running" | "passed" | "failed";
};

// The backend run id, receipts and outcomes are kept in the browser (localStorage), so a reload continues the run.
const STORAGE_KEY = "eel-ui-runs-api";
const states = new Map<string, RunState>(Object.entries(load()));
const defs = new Map<string, RunDef>();
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

/** The saved state of a run without loading it (status in lists). */
export function useSavedRun(id: string): RunState | undefined {
  return useSyncExternalStore(subscribe, () => states.get(id));
}

export type RunView =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; def: RunDef; state: RunState };

let views = new Map<string, RunView>();

/** The run definition and state of a test case; starts or reloads the backend run. */
export function useRun(id: string): RunView {
  useEffect(() => {
    if (!defs.has(id) && !loading.has(id)) openRun(id);
  }, [id]);
  return useSyncExternalStore(subscribe, () => {
    const def = defs.get(id);
    const state = def && getState(id);
    const prev = views.get(id);
    const next: RunView =
      def && state ? { status: "ready", def, state } : failed.has(id) ? { status: "error" } : { status: "loading" };
    // keep the same object while nothing changed (useSyncExternalStore needs a stable snapshot)
    const unchanged =
      prev?.status === next.status &&
      (next.status !== "ready" || (prev.status === "ready" && prev.def === next.def && prev.state === next.state));
    if (prev && unchanged) return prev;
    views = new Map(views).set(id, next);
    return next;
  });
}

export async function resetRun(id: string) {
  states.delete(id);
  defs.delete(id);
  save();
  notify();
  await openRun(id, true);
}

/** The backend keeps the run open until a required message is missing, so a failed round can be followed. */
export function nextRound(id: string) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s || !def || s.status !== "running" || s.current >= def.rounds.length - 1) return;
  if (!s.rounds[s.current].outcome) return;
  update(id, { ...s, current: s.current + 1 });
}

/** Reads the files in the browser: sizes, DATENSATZ-IDs and the parsed record for the field view. */
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
  }
  return { receipt, uploaded };
}

/** Rule set version -> the date the run is judged on (a day inside the version's validity). */
const VALID_ON: Record<string, string> = { "13.3": "2026-11-01", "13.4": "2027-01-01" };

async function openRun(id: string, forceNew = false) {
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
        // the run is gone (demo reset): start again
      }
    }
    const curated = RUNS.find((r) => r.testCaseId === id);
    if (!run) {
      run = await api.startRun(id, VALID_ON[curated?.ruleSet ?? "13.4"] ?? "2027-01-01", DEMO_VENDOR);
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

/** Uploads files for the open round, or `null` when the software produced no message. */
export async function submitRound(id: string, files: File[] | null) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s?.runId || !def || s.status !== "running") return;
  const local = files ? await readFiles(files) : undefined;
  const res = await api.submitRun(s.runId, files ?? []);
  const rounds = [...s.rounds];
  const receipt = res.receipt ? api.toReceipt(res.receipt, local?.receipt) : undefined;
  if (res.rejected) {
    // Rejected files are not judged; the vendor can upload again.
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
    outcome: api.toOutcome(result, def.hidden),
    reply,
  };
  update(id, { ...s, rounds, status: api.toRunStatus(run.status) });
}
