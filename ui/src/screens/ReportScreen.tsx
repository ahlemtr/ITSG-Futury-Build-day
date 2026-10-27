import { useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { downloadJson, getReport, reportHtmlUrl, type ReportView, type RuleLine } from "../data/api";
import { useData } from "../data/useData";
import { PassFail } from "../components/PassFail";
import { SpecRefText } from "../components/SpecRefText";
import { useSetTopBar } from "../components/TopBarContext";
import { formatDate } from "../format";

const PASSED = ["exact_match", "correct_variant"];

/** Screen 6: the signed report. The vendor never sees expected values of hidden tests. */
export function ReportScreen({ vendor = false }: { vendor?: boolean }) {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const state = useData(() => getReport(id), [id]);

  useSetTopBar(<Trans i18nKey="report.topbar" values={{ id }} components={{ strong: <strong /> }} />, [id]);

  if (state.status === "loading") return <p className="page-subtitle">{t("report.signing")}</p>;
  if (state.status === "error") return <div className="placeholder">{t("common.error")}</div>;
  if (!state.data) return <div className="placeholder">{t("result.notFound")}</div>;
  return <ReportBody view={state.data} vendor={vendor} />;
}

function ReportBody({ view, vendor }: { view: ReportView; vendor: boolean }) {
  const { t } = useTranslation();
  const r = view.signed.report;
  const sig = view.signed.signature;
  const passed = PASSED.includes(r.label);
  const failed = view.rules.filter((l) => l.result === "fail");
  const showValues = !(vendor && view.hidden);

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{t("report.title", { vendor: r.vendor ?? "–" })}</h1>
          <p className="page-subtitle">
            {t("report.subtitle", {
              testCase: r.test_case_id,
              ruleSet: r.rule_set_version,
              date: formatDate(r.valid_on),
              files: r.files.length,
            })}
            {view.hidden && ` · ${t("run.hidden")}`}
          </p>
        </div>
        <div className="header-actions">
          <button type="button" className="button" onClick={() => downloadJson(`report-${r.submission_id}.json`, view.signed)}>
            {t("report.downloadJson")}
          </button>
          {showValues && (
            <a className="button button-primary" href={reportHtmlUrl(r.submission_id)} target="_blank" rel="noreferrer">
              {t("report.openPrintable")}
            </a>
          )}
        </div>
      </div>

      <div className="overview-cards">
        <section className="panel verdict-card">
          <p className="eyebrow">{t("report.verdict")}</p>
          <p className="verdict-text">{t(passed ? "run.verdict.passed" : "run.verdict.failed")}</p>
          <p className="muted">
            {passed
              ? t("report.passedHint", { count: view.rules.length })
              : t("report.failedHint", { rules: failed.map((l) => l.id).join(", ") || "–" })}
          </p>
        </section>
        <section className="panel">
          <h2 className="card-title">{t("report.signature")}</h2>
          <dl className="facts">
            <div>
              <dt>SHA-256</dt>
              <dd className="mono hash" title={sig.json_sha256}>
                {sig.json_sha256.slice(0, 16)}…{sig.json_sha256.slice(-8)}
              </dd>
            </div>
            <div>
              <dt>{sig.algorithm}</dt>
              <dd>
                <span className={`badge ${view.valid ? "badge-exact" : "badge-bug"}`}>
                  {t(view.valid ? "report.valid" : "report.invalid")}
                </span>
              </dd>
            </div>
            <div>
              <dt>{t("report.signedAt")}</dt>
              <dd>{new Date(r.created).toLocaleString("de-DE")}</dd>
            </div>
          </dl>
        </section>
      </div>

      <section className="panel panel-flush">
        <h2 className="panel-title">{t("report.rules")}</h2>
        <table className="list-table">
          <thead>
            <tr>
              <th>{t("result.rule")}</th>
              <th>{t("report.col.checks")}</th>
              <th>{t("submissions.col.result")}</th>
              <th>{t("result.specPassage")}</th>
            </tr>
          </thead>
          <tbody>
            {view.rules.map((l, i) => (
              <RuleRow key={`${l.id}-${i}`} line={l} />
            ))}
          </tbody>
        </table>
      </section>

      {showValues && r.checks.length > 0 && (
        <section className="panel panel-flush">
          <h2 className="panel-title">{t("report.deviations")}</h2>
          <table className="list-table">
            <thead>
              <tr>
                <th>{t("result.col.block")}</th>
                <th>{t("result.col.field")}</th>
                <th>{t("result.col.expected")}</th>
                <th>{t("result.col.actual")}</th>
                <th>{t("result.reasoning")}</th>
              </tr>
            </thead>
            <tbody>
              {r.checks.map((c, i) => (
                <tr key={i}>
                  <td>{[c.abgabegrund, c.record].filter(Boolean).join(" ")}</td>
                  <td className="cell-field">{c.field ?? "–"}</td>
                  <td className="mono">{c.expected ?? "–"}</td>
                  <td className="mono">{c.actual ?? "–"}</td>
                  <td>{c.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="panel panel-flush">
        <h2 className="panel-title">{t("report.files")}</h2>
        <table className="list-table compact">
          <tbody>
            {r.files.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td className="mono hash">{f.sha256}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}

function RuleRow({ line }: { line: RuleLine }) {
  const { t } = useTranslation();
  return (
    <tr>
      <td className="cell-field">{line.id}</td>
      <td>{line.text}</td>
      <td>{line.result === "open" ? <span className="badge badge-unclear">{t("status.unclear")}</span> : <PassFail passed={line.result === "pass"} />}</td>
      <td>{line.source ? <SpecRefText spec={line.source} /> : "–"}</td>
    </tr>
  );
}
