// Every background AI job the screen is waiting for: spec upload pipelines (with stages from GET /jobs/{id})
// and single AI calls (triage, explanations, stories, the spec-update agent). The overlay shows them.
import { useSyncExternalStore } from "react";
import type { Localized } from "./types";

export type ActivityStage = { name: string; title: Localized; status: "waiting" | "running" | "done" | "failed"; counts: Record<string, unknown> };

export type Activity = {
  id: string;
  title: Localized;
  startedAt: number;
  /** null = one AI call without stages */
  stages: ActivityStage[] | null;
  status: "running" | "done" | "failed";
  error?: string;
};

let activities: Activity[] = [];
const listeners = new Set<() => void>();

function set(next: Activity[]) {
  activities = next;
  listeners.forEach((l) => l());
}

export function useActivities(): Activity[] {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => activities,
  );
}

// closed by the user: later updates of a job that is still being polled stay hidden
const dismissed = new Set<string>();

export function dismissActivity(id: string) {
  dismissed.add(id);
  set(activities.filter((x) => x.id !== id));
}

export function upsertActivity(a: Activity) {
  if (dismissed.has(a.id)) return;
  set(activities.some((x) => x.id === a.id) ? activities.map((x) => (x.id === a.id ? a : x)) : [...activities, a]);
  // finished jobs stay visible for a moment, then leave
  if (a.status !== "running") setTimeout(() => set(activities.filter((x) => x.id !== a.id)), a.status === "done" ? 4000 : 12000);
}

let counter = 0;

/** Shows a stage-less AI activity while `work` runs (calls that may reach the language model). */
export async function withAi<T>(title: Localized, work: Promise<T>): Promise<T> {
  const id = `ai-${++counter}`;
  const startedAt = Date.now();
  upsertActivity({ id, title, startedAt, stages: null, status: "running" });
  try {
    const out = await work;
    upsertActivity({ id, title, startedAt, stages: null, status: "done" });
    return out;
  } catch (e) {
    upsertActivity({ id, title, startedAt, stages: null, status: "failed", error: String(e) });
    throw e;
  }
}
