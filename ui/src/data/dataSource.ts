// The only place the screens get submission data from: the backend through ./api.
export { getNavCounts, getOverview, getSubmissionResult, getSubmissions } from "./api";

export type NavCounts = { specChanges: number; advisorQueue: number };
