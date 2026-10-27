// Advisor queue: GET /advisor/queue and POST /deviations/{id}/decide, which also adds the precedent
// to the catalogue. Shared by the nav badge and the queue screen.
import { useEffect, useSyncExternalStore } from "react";
import * as api from "./api";
import type { AdvisorItem, Precedent } from "./types";

type State = { open: AdvisorItem[]; decided: Precedent[]; status: "loading" | "ready" | "error" };

let state: State = { open: [], decided: [], status: "loading" };
const listeners = new Set<() => void>();

function set(next: State) {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Loads the queue from the backend (again). */
export async function refreshAdvisor() {
  try {
    set({ ...state, open: await api.getAdvisorQueue(), status: "ready" });
  } catch {
    set({ ...state, status: "error" });
  }
}

export function useAdvisorState(): State {
  useEffect(() => {
    refreshAdvisor();
  }, []);
  return useSyncExternalStore(subscribe, () => state);
}

/** Stores the advisor's decision as a precedent and removes the item from the queue. */
export async function decide(
  itemId: string,
  label: Precedent["label"],
  reason: string,
  advisor: string,
): Promise<Precedent | undefined> {
  const item = state.open.find((i) => i.id === itemId);
  if (!item) return undefined;
  const precedent = await api.decideDeviation(item, label, reason, advisor);
  set({ ...state, open: state.open.filter((i) => i.id !== itemId), decided: [precedent, ...state.decided] });
  return precedent;
}
