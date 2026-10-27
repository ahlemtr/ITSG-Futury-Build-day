import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { toSpecRef } from "../data/api";
import { ask, clearChat, setChatOpen, splitCitations, useChat, type ChatReply } from "../data/chat";
import { InfoTip } from "./InfoTip";
import { SpecRefText } from "./SpecRefText";

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

/** A drawer on the right: questions about the documents, answered from the knowledge graph with citations. */
export function ChatPanel() {
  const { t, i18n } = useTranslation();
  const { open, busy, turns } = useChat();
  const [question, setQuestion] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [turns.length, busy]);

  if (!open) return null;

  const send = (e?: FormEvent) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    void ask(q, i18n.language);
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) send();
    if (e.key === "Escape") setChatOpen(false);
  };

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

      <div className="chat-log" aria-live="polite">
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
            <Answer key={i} reply={turn.reply} />
          ) : (
            <p key={i} className="chat-error" role="alert">
              {t("chat.error", { error: turn.text })}
            </p>
          ),
        )}
        {busy && <p className="chat-thinking">{t("chat.thinking")}</p>}
        <div ref={end} />
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
        <button type="submit" className="button button-primary" disabled={busy || !question.trim()}>
          {t("chat.send")}
        </button>
      </form>
    </aside>
  );
}

function Answer({ reply }: { reply: ChatReply }) {
  const { t } = useTranslation();
  const sources = reply.answer ? reply.context.filter((c) => c.cited) : reply.context.slice(0, 3);
  const extra = reply.citations.filter((k) => !reply.context.some((c) => c.key === k));
  return (
    <div className="chat-answer">
      {reply.answer ? (
        <p>
          {splitCitations(reply.answer).map((part, i) =>
            "key" in part ? (
              <span key={i} className="chat-cite">
                <SpecRefText spec={toSpecRef(part.key)} />
              </span>
            ) : (
              <span key={i}>{part.text}</span>
            ),
          )}
        </p>
      ) : (
        <p className="chat-noanswer">{t("chat.noAnswer")}</p>
      )}
      {(sources.length > 0 || extra.length > 0) && (
        <details className="reasoning" open={!reply.answer}>
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
