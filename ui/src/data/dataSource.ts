// The only place the UI gets data from.
// mode "mock": demo data from ./mock. mode "api": the backend (later).
import navCounts from "./mock/navCounts.json";

export type NavCounts = { specChanges: number; advisorQueue: number };

const MODE = import.meta.env.VITE_DATA_MODE ?? "mock";

export async function getNavCounts(): Promise<NavCounts> {
  if (MODE === "api") {
    throw new Error("API mode is not built yet");
  }
  return navCounts;
}
