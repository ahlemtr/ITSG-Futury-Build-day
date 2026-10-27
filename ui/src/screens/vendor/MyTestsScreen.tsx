import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getVendorRuns } from "../../data/api";
import { RUNS } from "../../data/runTexts";
import { useSavedRun } from "../../data/runStore";
import { useData } from "../../data/useData";
import type { RunDef } from "../../data/types";
import { pick } from "../../format";
import { InfoTip } from "../../components/InfoTip";

export function MyTestsScreen() {
  const { t } = useTranslation();
  const runs = useData(() => getVendorRuns(RUNS), []);
  return (
    <>
      <div className="page-header">
        <h1>
          {t("screens.myTests.title")}
          <InfoTip>{t("screens.myTests.subtitle")}</InfoTip>
        </h1>
      </div>
      <section className="panel panel-flush">
        <table className="list-table">
          <thead>
            <tr>
              <th>{t("submissions.col.testCase")}</th>
              <th>{t("myTests.col.story")}</th>
              <th>{t("submissions.col.ruleSet")}</th>
              <th>{t("myTests.col.visibility")}</th>
              <th>{t("myTests.col.status")}</th>
            </tr>
          </thead>
          <tbody>
            {runs.status === "ready" && runs.data.map((run) => <TestRow key={run.testCaseId} run={run} />)}
            {runs.status !== "ready" && (
              <tr>
                <td colSpan={5} className="empty">
                  {t(runs.status === "loading" ? "common.loading" : "common.error")}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}

function TestRow({ run }: { run: RunDef }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const state = useSavedRun(run.testCaseId);
  const open = () => navigate(`/vendor/runs/${run.testCaseId}`);

  let status = t("myTests.status.notStarted");
  let tone = "neutral";
  if (state?.status === "passed") [status, tone] = [t("run.passed"), "exact"];
  else if (state?.status === "failed") [status, tone] = [t("run.failed"), "bug"];
  else if (state && (state.current > 0 || state.rounds[0].receipt || state.rounds[0].outcome))
    [status, tone] = [t("myTests.status.inRound", { nr: state.current + 1, total: state.rounds.length }), "variant"];

  return (
    <tr tabIndex={0} className="row-link" onClick={open} onKeyDown={(e) => e.key === "Enter" && open()}>
      <td className="cell-field">{run.testCaseId}</td>
      <td>{pick(run.title, i18n.language)}</td>
      <td>V{run.ruleSet}</td>
      <td>
        <span className={`badge ${run.hidden ? "badge-unclear" : "badge-neutral"}`}>
          {t(run.hidden ? "run.hidden" : "run.public")}
        </span>
      </td>
      <td>
        <span className={`badge badge-${tone}`}>{status}</span>
      </td>
    </tr>
  );
}
