import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { SubmissionSummary } from "../data/types";
import { formatDate } from "../format";
import { Badge } from "./Badge";

/** List of submissions; a row opens the submission result. Used on Overview and Submissions. */
export function SubmissionsTable({
  rows,
  showRound = true,
  basePath = "/submissions",
}: {
  rows: SubmissionSummary[];
  showRound?: boolean;
  basePath?: string;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const open = (id: string) => navigate(`${basePath}/${id}`);

  return (
    <table className="list-table">
      <thead>
        <tr>
          <th>{t("submissions.col.vendor")}</th>
          <th>{t("submissions.col.testCase")}</th>
          {showRound && <th>{t("submissions.col.round")}</th>}
          <th>{t("submissions.col.ruleSet")}</th>
          <th>{t("submissions.col.result")}</th>
          <th>{t("submissions.col.received")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr
            key={s.id}
            tabIndex={0}
            className="row-link"
            onClick={() => open(s.id)}
            onKeyDown={(e) => e.key === "Enter" && open(s.id)}
          >
            <td>{s.vendor}</td>
            <td>{s.testCaseId}</td>
            {showRound && (
              <td>
                {s.round} / {s.roundsTotal}
              </td>
            )}
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
  );
}
