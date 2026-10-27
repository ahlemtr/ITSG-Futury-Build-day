import { useTranslation } from "react-i18next";
import { getSubmissions } from "../data/dataSource";
import { useData } from "../data/useData";
import { SubmissionsTable } from "../components/SubmissionsTable";
import { InfoTip } from "../components/InfoTip";

export function SubmissionsScreen() {
  const { t } = useTranslation();
  const state = useData(getSubmissions, []);

  return (
    <>
      <div className="page-header">
        <h1>
          {t("screens.submissions.title")}
          <InfoTip>{t("screens.submissions.subtitle")}</InfoTip>
        </h1>
      </div>
      <section className="panel panel-flush">
        {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
        {state.status === "error" && <p className="empty">{t("common.error")}</p>}
        {state.status === "ready" && <SubmissionsTable rows={state.data} />}
      </section>
    </>
  );
}
