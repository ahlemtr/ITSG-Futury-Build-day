import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getSpecDiff, toSpecRef, type SpecChange, type SpecDiff } from "../data/api";
import { isApi } from "../data/dataSource";
import { useData } from "../data/useData";
import { wordDiff, type DiffPart } from "../records/wordDiff";
import { SpecRefText } from "../components/SpecRefText";
import { formatDate } from "../format";

/** Screen 2: a new Verfahrensbeschreibung is published. What changed, which rules and tests it touches. */
export function SpecChangesScreen() {
  const { t } = useTranslation();
  const state = useData(() => (isApi ? getSpecDiff() : Promise.resolve(null)), []);

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{t("screens.specChanges.title")}</h1>
          <p className="page-subtitle">
            {state.status === "ready" && state.data
              ? t("spec.subtitle", { count: state.data.changes.length, tests: state.data.changedTests.length })
              : t("spec.subtitleLoading")}
          </p>
        </div>
        <div className="header-actions">
          <Link className="button button-primary" to="/test-catalogue">
            {t("spec.toCatalogue")}
          </Link>
        </div>
      </div>
      {!isApi && <div className="placeholder">{t("report.apiOnly")}</div>}
      {state.status === "loading" && <p className="page-subtitle">{t("spec.loading")}</p>}
      {state.status === "error" && <div className="placeholder">{t("common.error")}</div>}
      {state.status === "ready" && state.data && <SpecDiffView diff={state.data} />}
    </>
  );
}

const isRuleChange = (c: SpecChange) => c.recompute.length > 0 || c.changes_param.length > 0;

function SpecDiffView({ diff }: { diff: SpecDiff }) {
  const { t } = useTranslation();
  const first = diff.changes.find(isRuleChange) ?? diff.changes[0];
  const [selectedKey, setSelectedKey] = useState(first?.key ?? "");
  const selected = diff.changes.find((c) => c.key === selectedKey) ?? first;

  return (
    <div className="queue-layout">
      <div className="queue-side">
        <section className="panel panel-flush">
          <ul className="queue-list">
            {diff.changes.map((c) => (
              <li key={c.key}>
                <button
                  type="button"
                  className={`queue-item${c.key === selected?.key ? " queue-item-selected" : ""}`}
                  aria-pressed={c.key === selected?.key}
                  onClick={() => setSelectedKey(c.key)}
                >
                  <span className="queue-item-head">
                    <strong>{[c.block, c.field].filter(Boolean).join(" · ") || c.key}</strong>
                    <span className={`badge ${isRuleChange(c) ? "badge-bug" : "badge-neutral"}`}>
                      {t(isRuleChange(c) ? "spec.ruleChange" : `spec.label.${c.label}`, { defaultValue: c.label })}
                    </span>
                  </span>
                  <span className="cell-hint">{c.summary ?? c.key}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {selected && <ChangeDetail key={selected.key} change={selected} diff={diff} />}
    </div>
  );
}

function Parts({ parts }: { parts: DiffPart[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === "same" ? <span key={i}>{p.text}</span> : <mark key={i} className={`diff-${p.kind}`}>{p.text}</mark>,
      )}
    </>
  );
}

const showValue = (v: unknown) => (v === undefined ? "–" : JSON.stringify(v));

function periodsText(p: { send_41: boolean; periods: [string, string][]; total_days: number | null }, t: (k: string) => string) {
  if (!p.send_41) return t("spec.no41");
  return `41 · ${p.periods.map(([a, b]) => `${formatDate(a)}–${formatDate(b)}`).join(", ")}`;
}

function ChangeDetail({ change, diff }: { change: SpecChange; diff: SpecDiff }) {
  const { t } = useTranslation();
  const parts = wordDiff(change.old ?? "", change.new ?? "");
  const flips = change.recompute.length ? diff.recomputed.filter((r) => r.differs) : [];
  const drafts = (diff.agent ?? []).filter((d) => d.change_key === change.key);

  return (
    <section className="panel advisor-detail">
      <p className="eyebrow">{change.key}</p>
      <h2>{change.summary ?? change.key}</h2>
      <p className="cell-hint">
        {change.modifies_old.map(toSpecRef).map((s, i) => (
          <span key={`o${i}`}>
            <SpecRefText spec={s} />
            {" → "}
          </span>
        ))}
        {change.modifies_new.map(toSpecRef).map((s, i) => (
          <SpecRefText key={`n${i}`} spec={s} />
        ))}
      </p>

      <div className="passage-pair">
        <div className="fact-tile">
          <span className="cell-hint">{t("spec.old", { version: diff.oldVersion })}</span>
          <p className="passage" lang="de">
            <Parts parts={parts.old} />
          </p>
        </div>
        <div className="fact-tile">
          <span className="cell-hint">{t("spec.new", { version: diff.newVersion })}</span>
          <p className="passage" lang="de">
            <Parts parts={parts.new} />
          </p>
        </div>
      </div>

      <h3>{t("spec.impact")}</h3>
      <dl className="facts">
        <div>
          <dt>{t("spec.recompute")}</dt>
          <dd>{change.recompute.join(", ") || "–"}</dd>
        </div>
        <div>
          <dt>{t("spec.review")}</dt>
          <dd>{change.review.join(", ") || "–"}</dd>
        </div>
        {change.changes_param.map((p) => (
          <div key={p}>
            <dt>{t("spec.param")}</dt>
            <dd className="mono">
              {p}: {showValue(diff.params.old[p])} → {showValue(diff.params.new[p])}
            </dd>
          </div>
        ))}
      </dl>

      {flips.length > 0 && (
        <table className="list-table compact">
          <thead>
            <tr>
              <th>{t("spec.flips")}</th>
              <th>V{diff.oldVersion}</th>
              <th>V{diff.newVersion}</th>
            </tr>
          </thead>
          <tbody>
            {flips.map((f) => (
              <tr key={f.id}>
                <td className="cell-field">{f.id}</td>
                <td>{periodsText(f.old, t)}</td>
                <td>{periodsText(f.new, t)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {drafts.length > 0 && (
        <section className="sub-card ai-card">
          <div className="sub-card-head">
            <h3>{t("spec.agent")}</h3>
          </div>
          <ul className="rule-list">
            {drafts.map((d, i) => (
              <li key={i}>
                <strong>{t(`spec.decision.${d.decision}`)}</strong>
                {d.test_case_id && <span className="mono"> · {d.test_case_id}</span>}
                <div lang="de">{d.reasoning}</div>
                <div className="cell-hint">
                  {d.citations.map(toSpecRef).map((s, j) => (
                    <span key={j}>
                      {j > 0 && "; "}
                      <SpecRefText spec={s} />
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="cell-hint">{t("advisor.draftOnly")}</p>
        </section>
      )}
    </section>
  );
}
