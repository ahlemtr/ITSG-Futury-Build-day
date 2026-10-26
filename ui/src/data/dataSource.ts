// The only place the UI gets data from.
// mode "mock": demo data from ./mock. mode "api": the backend (later).
import navCounts from "./mock/navCounts.json";
import { SUBMISSIONS, SUBMISSION_RESULTS } from "./mock/submissions";
import type { SubmissionResult, SubmissionSummary } from "./types";

export type NavCounts = { specChanges: number; advisorQueue: number };

const MODE = import.meta.env.VITE_DATA_MODE ?? "mock";

function notBuilt(): never {
  throw new Error("API mode is not built yet");
}

export async function getNavCounts(): Promise<NavCounts> {
  if (MODE === "api") notBuilt();
  return navCounts;
}

export async function getSubmissions(): Promise<SubmissionSummary[]> {
  if (MODE === "api") notBuilt();
  return SUBMISSIONS;
}

/** Returns null when no submission has this id. */
export async function getSubmissionResult(id: string): Promise<SubmissionResult | null> {
  if (MODE === "api") notBuilt();
  return SUBMISSION_RESULTS.find((s) => s.id === id) ?? null;
}
