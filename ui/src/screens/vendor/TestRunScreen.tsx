import { useRef, useState, type DragEvent } from "react";
import { useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { isApi } from "../../data/dataSource";
import { nextRound, resetRun, submitRound, useRun, type ReplyFile, type RoundState, type RunState } from "../../data/runStore";
import type { RoundDef, RunDef } from "../../data/types";
import { Badge } from "../../components/Badge";
import { PassFail } from "../../components/PassFail";
import { ReceiptCard } from "../../components/ReceiptCard";
import { ParsedRecordView } from "../../components/ParsedRecordView";
import { useSetTopBar } from "../../components/TopBarContext";
import { pick } from "../../format";

export function TestRunScreen() {
  const { id = "" } = useParams();
  const { t, i18n } = useTranslation();
  const view = useRun(id);
  const def = view.status === "ready" ? view.def : undefined;
  const state = view.status === "ready" ? view.state : undefined;

  useSetTopBar(
    def ? <Trans i18nKey="run.topbar" values={{ id, ruleSet: def.ruleSet }} components={{ strong: <strong /> }} /> : null,
    [id, def?.ruleSet],
  );

  if (view.status === "loading") return <p className="page-subtitle">{t("common.loading")}</p>;
  if (!def || !state) return <div className="placeholder">{t("run.notFound")}</div>;
  const lang = i18n.language;

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{pick(def.title, lang)}</h1>
          <p className="page-subtitle">
            {def.testCaseId} · V{def.ruleSet} · {t(def.hidden ? "run.hidden" : "run.public")} ·{" "}
            {t("run.roundsCount", { count: def.rounds.length })}
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="button" onClick={() => resetRun(id)}>
            {t("run.reset")}
          </button>
        </div>
      </div>

      {state.status !== "running" && <RunVerdict def={def} state={state} />}

      <div className="run-layout">
        <aside className="panel story">
          <p className="eyebrow">{t("run.story")}</p>
          <p>{pick(def.story, lang)}</p>
          <div className="fact-tiles">
            {def.facts.map((f) => (
              <div key={f.value + f.label.de} className="fact-tile">
                <span className="cell-hint">{pick(f.label, lang)}</span>
                <strong className="tabular">{f.value}</strong>
              </div>
            ))}
          </div>
          {def.hidden && <p className="hint-box">{t("run.hiddenHint")}</p>}
        </aside>

        <div className="rounds">
          <Stepper def={def} state={state} />
          {def.rounds.map((round, i) =>
            i <= state.current ? (
              <RoundCard
                key={round.nr}
                runId={id}
                def={def}
                round={round}
                rs={state.rounds[i]}
                isCurrent={i === state.current}
                running={state.status === "running"}
              />
            ) : null,
          )}
        </div>
      </div>
    </>
  );
}

function Stepper({ def, state }: { def: RunDef; state: RunState }) {
  const { t } = useTranslation();
  return (
    <ol className="stepper">
      {def.rounds.map((round, i) => {
        const outcome = state.rounds[i].outcome;
        const status = outcome ? (outcome.passed ? "done" : "failed") : i === state.current ? "current" : "locked";
        return (
          <li key={round.nr} className={`step step-${status}`} aria-current={status === "current" ? "step" : undefined}>
            <span className="step-nr">{round.nr}</span>
            <span>
              {t("run.round", { nr: round.nr })}
              <span className="step-sub">{t(`run.stepStatus.${status}`)}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function RoundCard(props: {
  runId: string;
  def: RunDef;
  round: RoundDef;
  rs: RoundState;
  isCurrent: boolean;
  running: boolean;
}) {
  const { runId, def, round, rs, isCurrent, running } = props;
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const open = isCurrent && running && !rs.outcome;
  const isLast = round.nr === def.rounds.length;
  const expectsNothing = round.expects.length === 0;

  return (
    <section className={`panel round-card${isCurrent ? " round-current" : ""}`}>
      <div className="sub-card-head">
        <h2>{t("run.round", { nr: round.nr })}</h2>
        {!def.hidden && (
          <span className="muted">
            {t("run.expects")}{" "}
            <strong>{expectsNothing ? t("run.noMessage") : round.expects.join(" + ")}</strong>
          </span>
        )}
      </div>
      <p>{pick(round.instruction, lang)}</p>

      {open && <UploadZone runId={runId} primaryUpload={!expectsNothing} multiple={round.expects.length > 1} />}
      {open && isApi && <p className="cell-hint">{t("run.upload.channelHint")}</p>}
      {rs.noMessage && <p className="hint-box">{t("run.reportedNoMessage")}</p>}
      {rs.receipt && <ReceiptCard receipt={rs.receipt} />}
      {rs.files && rs.receipt?.accepted !== false && <ParsedRecordView files={rs.files} />}

      {rs.outcome && (
        <section className="sub-card">
          <div className="sub-card-head">
            <h3>{t("run.outcome")}</h3>
            {def.hidden ? <PassFail passed={rs.outcome.passed} /> : <Badge value={rs.outcome.label} />}
          </div>
          {rs.outcome.message && <p>{pick(rs.outcome.message, lang)}</p>}
          <ul className="rule-list">
            {rs.outcome.rules.map((r) => {
              const rule = round.rules.find((x) => x.id === r.id);
              return (
                <li key={r.id}>
                  <PassFail passed={r.passed} /> <strong>{r.id}</strong> {rule && `· ${pick(rule.text, lang)}`}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {round.reply && !def.hidden && (isApi ? rs.reply : rs.outcome?.passed) && (
        <section className="sub-card reply">
          <div className="sub-card-head">
            <h3>{pick(round.reply.title, lang)}</h3>
            <span className="mono muted">{rs.reply?.name ?? round.reply.fileName}</span>
          </div>
          {!rs.reply && round.reply.rows.length > 0 && <table className="list-table compact">
            <tbody>
              {round.reply.rows.map((row) => (
                <tr key={row.field}>
                  <td className="cell-field">{row.field}</td>
                  <td className="mono">{fillReply(row.value, rs) || t("run.reply.blank")}</td>
                  <td className="muted">{row.note ? pick(row.note, lang) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>}
          {rs.reply && <ParsedRecordView files={[rs.reply]} />}
          <p className="cell-hint">{t("run.reply.fromYourFile")}</p>
          {rs.reply ? (
            <button type="button" className="button" onClick={() => download(rs.reply!)}>
              {t("run.reply.download", { file: rs.reply.name })}
            </button>
          ) : (
            <button type="button" className="button" disabled title={t("run.reply.downloadLater")}>
              {t("run.reply.download", { file: round.reply.fileName })}
            </button>
          )}
          {rs.reply && <p className="cell-hint">{t("run.reply.importHint")}</p>}
        </section>
      )}

      {isCurrent && running && rs.outcome && (isApi || rs.outcome.passed) && !isLast && (
        <div className="round-next">
          <button type="button" className="button button-primary" onClick={() => nextRound(runId)}>
            {t("run.next", { nr: round.nr + 1 })}
          </button>
        </div>
      )}
    </section>
  );
}

/** Saves the insurer reply (TEEK0) so the vendor can import it into the payroll software. */
function download(reply: ReplyFile) {
  const url = URL.createObjectURL(new Blob([reply.text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = reply.name;
  a.click();
  URL.revokeObjectURL(url);
}

function fillReply(value: string, rs: RoundState): string {
  const values = rs.outcome?.replyValues;
  if (value === "{REF}") return values?.REF ?? "";
  if (value === "{AZVU}") return values?.AZVU ?? "";
  return value;
}

function UploadZone({ runId, primaryUpload, multiple }: { runId: string; primaryUpload: boolean; multiple: boolean }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function send(files: File[] | null) {
    setBusy(true);
    try {
      await submitRound(runId, files);
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const files = [...e.dataTransfer.files];
    if (files.length) send(files);
  }

  return (
    <div
      className={`dropzone${dragging ? " dropzone-active" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <p>{busy ? t("run.upload.checking") : t(multiple ? "run.upload.dropMany" : "run.upload.drop")}</p>
      <div className="dropzone-actions">
        <button
          type="button"
          className={`button${primaryUpload ? " button-primary" : ""}`}
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          {t("run.upload.choose")}
        </button>
        <button
          type="button"
          className={`button${primaryUpload ? "" : " button-primary"}`}
          disabled={busy}
          onClick={() => send(null)}
        >
          {t("run.upload.none")}
        </button>
      </div>
      <input
        ref={input}
        type="file"
        multiple
        hidden
        onChange={(e) => {
          const files = [...(e.target.files ?? [])];
          e.target.value = "";
          if (files.length) send(files);
        }}
      />
    </div>
  );
}

function RunVerdict({ def, state }: { def: RunDef; state: RunState }) {
  const { t } = useTranslation();
  const passed = state.status === "passed";
  const failedRule = state.rounds.flatMap((r) => r.outcome?.rules ?? []).find((r) => !r.passed);
  return (
    <section className={`panel verdict-card ${passed ? "verdict-passed" : "verdict-failed"}`}>
      <p className="eyebrow">{t("run.verdict.title")}</p>
      <p className="verdict-text">{t(passed ? "run.verdict.passed" : "run.verdict.failed")}</p>
      <p className="muted">
        {passed
          ? t("run.verdict.passedHint", { count: def.rounds.length })
          : t("run.verdict.failedHint", { rule: failedRule?.id ?? "–" })}
      </p>
    </section>
  );
}
