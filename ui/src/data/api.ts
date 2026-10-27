// The backend API (api mode). Vite proxies /api/* to FastAPI (see vite.config.ts).
// Every function maps the backend JSON to the UI types in ./types, so the screens do not change.
import type { Label, Localized, OverviewData, SpecRef } from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init);
  if (!res.ok) {
    const body = await res.text();
    let detail = body;
    try {
      detail = JSON.parse(body).detail ?? body;
    } catch {
      // not JSON: keep the text
    }
    throw new ApiError(res.status, `${res.status} ${path}: ${detail}`);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("json") ? res.json() : res.text()) as Promise<T>;
}

export const getJson = <T>(path: string) => request<T>(path);

export const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export function postForm<T>(path: string, fields: Record<string, string | undefined>, files: File[] = []) {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) if (v !== undefined) form.append(k, v);
  for (const f of files) form.append("files", f, f.name);
  return request<T>(path, { method: "POST", body: form });
}

// ---------- shared mapping helpers ----------

/** Backend explanations are English only; shown as is in both languages. */
export const same = (text: string): Localized => ({ de: text, en: text });

/** Backend labels (05 section 5) to UI labels. */
export function toLabel(label: string | null | undefined): Label {
  switch (label) {
    case "exact_match":
      return "exact";
    case "correct_variant":
      return "variant";
    case "bug":
    case "invalid":
    case "unclear":
      return label;
    default:
      return "unclear";
  }
}

/** "VB@13.4#3.12/chaining" -> { document: VB, version: 13.4, section: 3.12/chaining }. */
export function toSpecRef(key: string): SpecRef {
  const [docVersion, section = ""] = key.split("#");
  const [document, version = ""] = docVersion.split("@");
  return { document: document as SpecRef["document"], version, section };
}

/** Spec passages first (VB, GG, BP), ITSG criteria (BVORERK) last. */
export function mainSource(sources: string[]): string | undefined {
  const rank = (k: string) => (k.startsWith("VB@") ? 0 : k.startsWith("GG@") ? 1 : k.startsWith("BP@") ? 2 : 3);
  return [...sources].sort((a, b) => rank(a) - rank(b))[0];
}

// ---------- Overview ----------

export async function getOverview(): Promise<OverviewData> {
  type Api = Omit<OverviewData, "nextYear"> & { nextYear: OverviewData["nextYear"] | null };
  const o = await getJson<Api>("/overview");
  return {
    ...o,
    nextYear: o.nextYear ?? {
      ruleSet: "–",
      validFrom: o.checksNow.validUntil,
      specChangesInScope: 0,
      testsToReapprove: 0,
      hiddenVariantsReady: 0,
    },
  };
}

export async function getNavCounts(): Promise<{ specChanges: number; advisorQueue: number }> {
  const [o, queue] = await Promise.all([getOverview(), getJson<unknown[]>("/advisor/queue")]);
  return { specChanges: o.nextYear.specChangesInScope > 0 ? 1 : 0, advisorQueue: queue.length };
}
