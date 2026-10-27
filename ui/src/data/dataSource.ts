// The only place the UI gets data from.
// mode "mock": demo data from ./mock. mode "api": the backend through ./api (npm run dev:api).
import * as api from "./api";
import navCounts from "./mock/navCounts.json";
import { OVERVIEW } from "./mock/overview";
import { SUBMISSIONS, SUBMISSION_RESULTS } from "./mock/submissions";
import type { OverviewData, SubmissionResult, SubmissionSummary } from "./types";

export type NavCounts = { specChanges: number; advisorQueue: number };

export const MODE = import.meta.env.VITE_DATA_MODE ?? "mock";
export const isApi = MODE === "api";

export async function getNavCounts(): Promise<NavCounts> {
  if (isApi) return api.getNavCounts();
  return navCounts;
}

export async function getOverview(): Promise<OverviewData> {
  if (isApi) return api.getOverview();
  return OVERVIEW;
}

export async function getSubmissions(): Promise<SubmissionSummary[]> {
  if (isApi) return api.getSubmissions();
  return SUBMISSIONS;
}

/** Returns null when there is no field-by-field result for this id. */
export async function getSubmissionResult(id: string): Promise<SubmissionResult | null> {
  if (isApi) return api.getSubmissionResult(id);
  return SUBMISSION_RESULTS.find((s) => s.id === id) ?? null;
}
