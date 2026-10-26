// State of the vendor's test runs in this browser tab (mock mode).
// Files are really read (parser, SHA-256). The verdict per round is a simple stand-in until the
// backend checker exists: it only checks that the expected messages (Abgabegründe) arrived.
import { useSyncExternalStore } from "react";
import { decode, fieldValue, parseText, sha256, type ParsedFile } from "../records/parse";
import { RUNS } from "./mock/runs";
import type { Receipt, RoundOutcome, RunDef } from "./types";

export type UploadedFile = { name: string; parsed: ParsedFile };

export type RoundState = {
  receipt?: Receipt;
  files?: UploadedFile[];
  /** the vendor reported that its software produced no message */
  noMessage?: boolean;
  outcome?: RoundOutcome;
};

export type RunState = {
  /** index of the open round */
  current: number;
  rounds: RoundState[];
  status: "running" | "passed" | "failed";
};

const states = new Map<string, RunState>();
const listeners = new Set<() => void>();

function fresh(def: RunDef): RunState {
  return { current: 0, rounds: def.rounds.map(() => ({})), status: "running" };
}

export function getRunDef(id: string): RunDef | undefined {
  return RUNS.find((r) => r.testCaseId === id);
}

function getState(id: string): RunState | undefined {
  const def = getRunDef(id);
  if (!def) return undefined;
  if (!states.has(id)) states.set(id, fresh(def));
  return states.get(id);
}

function update(id: string, next: RunState) {
  states.set(id, next);
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useRunState(id: string): RunState | undefined {
  return useSyncExternalStore(subscribe, () => getState(id));
}

export function resetRun(id: string) {
  const def = getRunDef(id);
  if (def) update(id, fresh(def));
}

export function nextRound(id: string) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s || !def || s.status !== "running") return;
  if (!s.rounds[s.current].outcome?.passed || s.current >= def.rounds.length - 1) return;
  update(id, { ...s, current: s.current + 1 });
}

/** Uploads files for the open round, or `null` when the software produced no message. */
export async function submitRound(id: string, files: File[] | null) {
  const s = getState(id);
  const def = getRunDef(id);
  if (!s || !def || s.status !== "running") return;
  const round = def.rounds[s.current];

  let roundState: RoundState;
  let produced: { abgabegrund: string; datensatzId: string; azvu: string }[] = [];

  if (files === null) {
    roundState = { noMessage: true };
  } else {
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
      produced.push(
        ...parsed.records.map((r) => ({
          abgabegrund: r.abgabegrund,
          datensatzId: r.datensatzId,
          azvu: fieldValue(r, "DBID", "AKTENZEICHEN-VERURSACHER"),
        })),
      );
    }
    receipt.accepted = receipt.issues.length === 0;
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
