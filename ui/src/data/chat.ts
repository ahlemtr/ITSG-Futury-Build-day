// Chat assistant (HANDOUT agenda 4): POST /chat, answers from the knowledge graph with passage citations.
import { useSyncExternalStore } from "react";
import { both, postJson } from "./api";
import { withAi } from "./aiActivity";

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

export type ChatTurn = { role: "user"; text: string } | { role: "assistant"; reply: ChatReply } | { role: "error"; text: string };

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
  );
}

export const setChatOpen = (open: boolean) => set({ open });

export const clearChat = () => set({ turns: [] });

export async function ask(question: string, language: string) {
  const history = state.turns.flatMap((t) =>
    t.role === "user" ? [{ role: "user", text: t.text }] : t.role === "assistant" && t.reply.answer ? [{ role: "assistant", text: t.reply.answer }] : [],
  );
  set({ busy: true, turns: [...state.turns, { role: "user", text: question }] });
  try {
    const reply = await withAi(
      both("ai.title.chat"),
      postJson<ChatReply>("/chat", { question, history, language: language === "en" ? "en" : "de" }),
    );
    set({ turns: [...state.turns, { role: "assistant", reply }] });
  } catch (e) {
    set({ turns: [...state.turns, { role: "error", text: e instanceof Error ? e.message : String(e) }] });
  } finally {
    set({ busy: false });
  }
}

/** "… [VB@13.4#3.12.5] …" -> text and citation keys in order, for rendering the keys as spec references. */
export function splitCitations(text: string): ({ text: string } | { key: string })[] {
  const out: ({ text: string } | { key: string })[] = [];
  const re = /\[([A-Z0-9-]+@[^#\]\s]+#[^\]\s]+)\]/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) });
    out.push({ key: m[1] });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last) });
  return out;
}
