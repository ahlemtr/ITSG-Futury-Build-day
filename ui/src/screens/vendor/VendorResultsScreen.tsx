import { useTranslation } from "react-i18next";
import { getSubmissions } from "../../data/dataSource";
import { DEMO_VENDOR } from "../../data/mock/runs";
import { useData } from "../../data/useData";
import { SubmissionsTable } from "../../components/SubmissionsTable";

/** The vendor's own submissions; a row opens the same result view as on the ITSG side. */
export function VendorResultsScreen() {
  const { t } = useTranslation();
  const state = useData(getSubmissions, []);

  return (
    <>
      <div className="page-header">
        <h1>{t("screens.vendorResults.title")}</h1>
        <p className="page-subtitle">{t("screens.vendorResults.subtitle")}</p>
      </div>
      <section className="panel panel-flush">
        {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
        {state.status === "error" && <p className="empty">{t("common.error")}</p>}
        {state.status === "ready" && (
          <SubmissionsTable rows={state.data.filter((s) => s.vendor === DEMO_VENDOR)} basePath="/vendor/results" />
        )}
      </section>
    </>
  );
}
