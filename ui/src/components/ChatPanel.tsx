import { Component, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { toSpecRef } from "../data/api";
import {
  ask,
  clearChat,
  doneTyping,
  partsLength,
  setChatOpen,
  splitCitations,
  takeParts,
  useChat,
  type ChatReply,
} from "../data/chat";
import { InfoTip } from "./InfoTip";
import { SpecRefText } from "./SpecRefText";

/** Characters written per frame while an answer is typed out (about 40 ms per frame). */
const CHARS_PER_TICK = 3;
const TICK_MS = 16;

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

/** The top bar button that opens the assistant. */
export function ChatButton() {
  const { t } = useTranslation();
  const { open } = useChat();
  return (
    <button type="button" className="button chat-launch" aria-expanded={open} aria-controls="chat-panel" onClick={() => setChatOpen(!open)}>
      {t("chat.open")}
    </button>
  );
}

/** A crash inside the chat stays inside the chat: the rest of the app keeps working. */
class ChatBoundary extends Component<{ children: ReactNode; fallback: (reset: () => void) => ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error("[chat]", error);
  }
  render() {
    return this.state.failed ? this.props.fallback(() => this.setState({ failed: false })) : this.props.children;
  }
}

export function ChatPanel() {
  const { t } = useTranslation();
  const { open } = useChat();
  if (!open) return null;
  return (
    <ChatBoundary
      fallback={(reset) => (
        <aside id="chat-panel" className="chat-panel chat-panel-failed" role="alert">
          <p>{t("chat.crashed")}</p>
          <button
            type="button"
            className="button"
            onClick={() => {
              clearChat();
              reset();
            }}
          >
            {t("chat.clear")}
          </button>
        </aside>
      )}
    >
      <Panel />
    </ChatBoundary>
  );
}

/** A drawer on the right: questions about the documents, answered from the knowledge graph with citations. */
function Panel() {
  const { t, i18n } = useTranslation();
  const { busy, turns } = useChat();
  const [question, setQuestion] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);

  useEffect(() => input.current?.focus(), []);
  const follow = () => log.current?.scrollTo({ top: log.current.scrollHeight });
  useEffect(follow, [turns.length, busy]);

  const send = (e?: FormEvent) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    void ask(q, i18n.language);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
    if (e.key === "Escape") setChatOpen(false);
  };
  const typing = turns.some((x) => x.role === "assistant" && x.typing);

  return (
    <aside id="chat-panel" className="chat-panel" aria-labelledby="chat-title">
      <header className="chat-head">
        <h2 id="chat-title">
          {t("chat.title")}
          <InfoTip>{t("chat.info")}</InfoTip>
        </h2>
        {turns.length > 0 && (
          <button type="button" className="link-button" onClick={clearChat} disabled={busy}>
            {t("chat.clear")}
          </button>
        )}
        <button type="button" className="chat-close" aria-label={t("chat.close")} onClick={() => setChatOpen(false)}>
          ×
        </button>
      </header>

      <div className="chat-log" ref={log}>
        {turns.length === 0 && (
          <div className="chat-empty">
            <p>{t("chat.empty")}</p>
            <ul>
              {(["q1", "q2", "q3"] as const).map((k) => (
                <li key={k}>
                  <button type="button" className="chat-suggestion" onClick={() => void ask(t(`chat.examples.${k}`), i18n.language)}>
                    {t(`chat.examples.${k}`)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {turns.map((turn, i) =>
          turn.role === "user" ? (
            <p key={i} className="chat-question">
              {turn.text}
            </p>
          ) : turn.role === "assistant" ? (
            <Answer key={i} reply={turn.reply} typing={turn.typing} onTyped={() => doneTyping(i)} onGrow={follow} />
          ) : (
            <p key={i} className="chat-error" role="alert">
              {t("chat.error", { error: turn.text })}
            </p>
          ),
        )}
        {busy && (
          <p className="chat-thinking" role="status" aria-label={t("chat.thinking")}>
            <span className="chat-dot" />
            <span className="chat-dot" />
            <span className="chat-dot" />
          </p>
        )}
      </div>

      <form className="chat-form" onSubmit={send}>
        <label htmlFor="chat-input" className="visually-hidden">
          {t("chat.label")}
        </label>
        <textarea
          id="chat-input"
          ref={input}
          rows={2}
          value={question}
          placeholder={t("chat.placeholder")}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKey}
        />
        <button type="submit" className="button button-primary" disabled={busy || typing || !question.trim()}>
          {t("chat.send")}
        </button>
      </form>
    </aside>
  );
}

/** "**genau**" -> bold; the model writes light markdown. */
function Text({ text }: { text: string }) {
  return (
    <>
      {text.split("**").map((piece, i) => (i % 2 ? <strong key={i}>{piece}</strong> : <span key={i}>{piece}</span>))}
    </>
  );
}

function Answer({ reply, typing, onTyped, onGrow }: { reply: ChatReply; typing: boolean; onTyped: () => void; onGrow: () => void }) {
  const { t } = useTranslation();
  const parts = useMemo(() => splitCitations(reply.answer ?? ""), [reply.answer]);
  const total = partsLength(parts);
  const [shown, setShown] = useState(typing && !reducedMotion() ? 0 : total);
  const done = shown >= total;

  // write the answer out progressively, then show its sources
  useEffect(() => {
    if (done) {
      if (typing) onTyped();
      return;
    }
    const id = window.setTimeout(() => setShown((n) => Math.min(total, n + CHARS_PER_TICK)), TICK_MS);
    onGrow();
    return () => window.clearTimeout(id);
  }, [shown, done, total]);

  const sources = reply.answer ? reply.context.filter((c) => c.cited) : reply.context.slice(0, 3);
  const extra = reply.citations.filter((k) => !reply.context.some((c) => c.key === k));
  return (
    <div className="chat-answer">
      {reply.answer ? (
        <p aria-busy={!done}>
          {takeParts(parts, shown).map((part, i) =>
            "key" in part ? (
              <span key={i} className="chat-cite">
                <SpecRefText spec={toSpecRef(part.key)} />
              </span>
            ) : (
              <Text key={i} text={part.text} />
            ),
          )}
          {!done && <span className="chat-caret" aria-hidden="true" />}
        </p>
      ) : (
        <p className="chat-noanswer">{t("chat.noAnswer")}</p>
      )}
      {done && (sources.length > 0 || extra.length > 0) && (
        <details className="reasoning chat-sources-box" open={!reply.answer}>
          <summary>{t("chat.sources", { count: sources.length + extra.length })}</summary>
          <ul className="chat-sources">
            {sources.map((s) => (
              <li key={s.key}>
                <SpecRefText spec={{ ...toSpecRef(s.key), title: s.heading || undefined }} />
                {s.snippet && (
                  <q className="cell-hint" lang="de">
                    {s.snippet}
                  </q>
                )}
                {(s.rules.length > 0 || s.test_cases.length > 0) && (
                  <span className="cell-hint">
                    {s.rules.length > 0 && t("chat.rules", { rules: s.rules.map((r) => r.id).join(", ") })}
                    {s.rules.length > 0 && s.test_cases.length > 0 && " · "}
                    {s.test_cases.length > 0 && t("chat.tests", { tests: s.test_cases.join(", ") })}
                  </span>
                )}
              </li>
            ))}
            {extra.map((k) => (
              <li key={k}>
                <SpecRefText spec={toSpecRef(k)} />
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
