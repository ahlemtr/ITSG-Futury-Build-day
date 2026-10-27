import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getReports, getTestCases } from "../data/api";
import { isApi } from "../data/dataSource";
import { DEMO_VENDOR } from "../data/mock/runs";
import { useData } from "../data/useData";
import { Badge } from "../components/Badge";
import { formatDate } from "../format";

/** Reports list (ITSG: every checked submission; vendor: its own, hidden tests included as pass / fail). */
export function ReportsScreen({ vendor = false }: { vendor?: boolean }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const screen = vendor ? "vendorReports" : "reports";
  const base = vendor ? "/vendor/reports" : "/reports";
  const state = useData(async () => {
    if (!isApi) return null;
    const [rows, cases] = await Promise.all([getReports(vendor ? DEMO_VENDOR : undefined), getTestCases()]);
    const hidden = new Set(cases.filter((c) => c.hidden).map((c) => c.id));
    return rows.map((r) => ({ ...r, hidden: hidden.has(r.testCaseId) }));
  }, [vendor]);

  return (
    <>
      <div className="page-header">
        <h1>{t(`screens.${screen}.title`)}</h1>
        <p className="page-subtitle">{t(`screens.${screen}.subtitle`)}</p>
      </div>
      {state.status === "ready" && state.data === null && <div className="placeholder">{t("report.apiOnly")}</div>}
      {(state.status !== "ready" || state.data !== null) && (
        <section className="panel panel-flush">
          {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
          {state.status === "error" && <p className="empty">{t("common.error")}</p>}
          {state.status === "ready" && state.data && (
            <table className="list-table">
              <thead>
                <tr>
                  {!vendor && <th>{t("submissions.col.vendor")}</th>}
                  <th>{t("submissions.col.testCase")}</th>
                  <th>{t("submissions.col.ruleSet")}</th>
                  <th>{t("submissions.col.result")}</th>
                  <th>{t("report.col.signed")}</th>
                </tr>
              </thead>
              <tbody>
                {state.data.length === 0 && (
                  <tr>
                    <td colSpan={5} className="empty">
                      {t("report.none")}
                    </td>
                  </tr>
                )}
                {state.data.map((r) => {
                  const open = () => navigate(`${base}/${r.id}`);
                  return (
                    <tr key={r.id} tabIndex={0} className="row-link" onClick={open} onKeyDown={(e) => e.key === "Enter" && open()}>
                      {!vendor && <td>{r.vendor}</td>}
                      <td>
                        {r.testCaseId}
                        {r.hidden && <span className="badge badge-unclear"> {t("run.hidden")}</span>}
                      </td>
                      <td>V{r.ruleSet}</td>
                      <td>
                        <Badge value={r.verdict} />
                      </td>
                      <td>{r.signed ? formatDate(r.signed.slice(0, 10)) : <span className="muted">{t("report.notSigned")}</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </section>
      )}
    </>
  );
}
