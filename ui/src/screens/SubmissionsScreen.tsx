import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getSubmissions } from "../data/dataSource";
import { useData } from "../data/useData";
import { Badge } from "../components/Badge";
import { formatDate } from "../format";

export function SubmissionsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const state = useData(getSubmissions, []);

  return (
    <>
      <div className="page-header">
        <h1>{t("screens.submissions.title")}</h1>
        <p className="page-subtitle">{t("screens.submissions.subtitle")}</p>
      </div>
      <section className="panel panel-flush">
        {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
        {state.status === "error" && <p className="empty">{t("common.error")}</p>}
        {state.status === "ready" && (
          <table className="list-table">
            <thead>
              <tr>
                <th>{t("submissions.col.vendor")}</th>
                <th>{t("submissions.col.testCase")}</th>
                <th>{t("submissions.col.round")}</th>
                <th>{t("submissions.col.ruleSet")}</th>
                <th>{t("submissions.col.result")}</th>
                <th>{t("submissions.col.received")}</th>
              </tr>
            </thead>
            <tbody>
              {state.data.map((s) => (
                <tr
                  key={s.id}
                  tabIndex={0}
                  className="row-link"
                  onClick={() => navigate(`/submissions/${s.id}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/submissions/${s.id}`)}
                >
                  <td>{s.vendor}</td>
                  <td>{s.testCaseId}</td>
                  <td>
                    {s.round} / {s.roundsTotal}
                  </td>
                  <td>V{s.ruleSet}</td>
                  <td>
                    <Badge value={s.verdict} />
                  </td>
                  <td>
                    <time dateTime={s.receivedOn}>{formatDate(s.receivedOn)}</time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}
