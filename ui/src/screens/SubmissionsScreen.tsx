import { useTranslation } from "react-i18next";
import { getSubmissions } from "../data/dataSource";
import { useData } from "../data/useData";
import { SubmissionsTable } from "../components/SubmissionsTable";

export function SubmissionsScreen() {
  const { t } = useTranslation();
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
        {state.status === "ready" && <SubmissionsTable rows={state.data} />}
      </section>
    </>
  );
}
