// Advisor queue. Mock mode: demo items in this browser. Api mode: GET /advisor/queue and
// POST /deviations/{id}/decide, which also adds the precedent to the catalogue.
import { useEffect, useSyncExternalStore } from "react";
import * as api from "./api";
import { isApi } from "./dataSource";
import { ADVISOR_ITEMS, NEXT_PRECEDENT_NUMBER } from "./mock/advisor";
import type { AdvisorItem, Precedent } from "./types";

type State = { open: AdvisorItem[]; decided: Precedent[]; status: "loading" | "ready" | "error" };

// Mock decisions are kept in the browser (localStorage), so a page reload does not lose them.
const STORAGE_KEY = "eel-ui-advisor";

function load(): State {
  if (isApi) return { open: [], decided: [], status: "loading" };
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as { decided: Precedent[]; decidedIds: string[] } | null;
    if (saved) {
      return {
        open: ADVISOR_ITEMS.filter((i) => !saved.decidedIds.includes(i.id)),
        decided: saved.decided,
        status: "ready",
      };
    }
  } catch {
    // storage blocked or unreadable: start from the demo queue
  }
  return { open: ADVISOR_ITEMS, decided: [], status: "ready" };
}

function save() {
  if (isApi) return;
  try {
    const decidedIds = ADVISOR_ITEMS.filter((i) => !state.open.includes(i)).map((i) => i.id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ decided: state.decided, decidedIds }));
  } catch {
    // storage blocked: decisions last until the next reload
  }
}

let state: State = load();
const listeners = new Set<() => void>();

function set(next: State) {
  state = next;
  save();
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Api mode: loads the queue from the backend (again). */
export async function refreshAdvisor() {
  if (!isApi) return;
  try {
    set({ ...state, open: await api.getAdvisorQueue(), status: "ready" });
  } catch {
    set({ ...state, status: "error" });
  }
}

export function useAdvisorState(): State {
  useEffect(() => {
    if (isApi) refreshAdvisor();
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
  const precedent: Precedent = isApi
    ? await api.decideDeviation(item, label, reason, advisor)
    : {
        id: `P-${String(NEXT_PRECEDENT_NUMBER + state.decided.length).padStart(3, "0")}`,
        signature: `${item.record}.${item.field}.${item.kind}`,
        label,
        reason,
        advisor,
        at: new Date().toISOString(),
        itemTitle: item.title,
      };
  set({ ...state, open: state.open.filter((i) => i.id !== itemId), decided: [precedent, ...state.decided] });
  return precedent;
}

/** Mock mode: puts all demo cases back into the queue. */
export function resetAdvisor() {
  set({ open: ADVISOR_ITEMS, decided: [], status: "ready" });
}
