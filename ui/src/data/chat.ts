// Chat assistant: POST /chat, answers from the knowledge graph with passage citations.
import { useSyncExternalStore } from "react";
import { postJson } from "./api";

export type ChatSource = {
  key: string;
  heading: string;
  snippet: string | null;
  rules: { id: string; title: string | null }[];
  changes: string[];
  test_cases: string[];
  cited: boolean;
};

export type ChatReply = {
  question: string;
  /** null: no cited answer (model unavailable or no valid citation); the sources are still there */
  answer: string | null;
  citations: string[];
  rules: string[];
  test_cases: string[];
  context: ChatSource[];
};

export type ChatTurn =
  | { role: "user"; text: string }
  /** `typing`: the answer is still being written out on screen */
  | { role: "assistant"; reply: ChatReply; typing: boolean }
  | { role: "error"; text: string };

type State = { open: boolean; busy: boolean; turns: ChatTurn[] };

// kept for the session: the conversation survives navigation between screens
let state: State = { open: false, busy: false, turns: [] };
const listeners = new Set<() => void>();

function set(next: Partial<State>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

export function useChat(): State {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l);
      return () => listeners.delete(l);
    },
    () => state,
    () => state,
  );
}

export const setChatOpen = (open: boolean) => set({ open });

export const clearChat = () => set({ turns: [] });

/** The answer at `index` has been written out completely. */
export function doneTyping(index: number) {
  const t = state.turns[index];
  if (t?.role === "assistant" && t.typing) set({ turns: state.turns.map((x, i) => (i === index ? { ...t, typing: false } : x)) });
}

/** Anything else than a chat reply (an HTML error page, a text body) is an error, never rendered as a reply. */
function isReply(x: unknown): x is ChatReply {
  const r = x as ChatReply;
  return typeof r === "object" && r !== null && (r.answer === null || typeof r.answer === "string") && Array.isArray(r.context) && Array.isArray(r.citations);
}

export async function ask(question: string, language: string) {
  const history = state.turns.flatMap((t) =>
    t.role === "user" ? [{ role: "user", text: t.text }] : t.role === "assistant" && t.reply.answer ? [{ role: "assistant", text: t.reply.answer }] : [],
  );
  set({ busy: true, turns: [...state.turns, { role: "user", text: question }] });
  try {
    const reply = await postJson<unknown>("/chat", { question, history, language: language === "en" ? "en" : "de" });
    if (!isReply(reply)) throw new Error("unexpected answer from the server");
    set({ turns: [...state.turns, { role: "assistant", reply, typing: true }] });
  } catch (e) {
    set({ turns: [...state.turns, { role: "error", text: e instanceof Error ? e.message : String(e) }] });
  } finally {
    set({ busy: false });
  }
}

export type Part = { text: string } | { key: string };

/** "… [VB@13.4#3.12.5] …" -> text and citation keys in order, for rendering the keys as spec references. */
export function splitCitations(text: string): Part[] {
  const out: Part[] = [];
  const re = /\[([A-Z0-9-]+@[^#\]\s]+#[^\]\s]+)\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    const at = m.index ?? 0;
    if (at > last) out.push({ text: text.slice(last, at) });
    out.push({ key: m[1] });
    last = at + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}

/** The first `n` characters of the parts; a citation counts as one character. */
export function takeParts(parts: Part[], n: number): Part[] {
  const out: Part[] = [];
  for (const p of parts) {
    if (n <= 0) break;
    if ("key" in p) {
      out.push(p);
      n -= 1;
    } else {
      out.push({ text: p.text.slice(0, n) });
      n -= p.text.length;
    }
  }
  return out;
}

export const partsLength = (parts: Part[]) => parts.reduce((sum, p) => sum + ("key" in p ? 1 : p.text.length), 0);
