import { useTranslation } from "react-i18next";
import { getTestCases } from "../../data/api";
import { getSubmissions, isApi } from "../../data/dataSource";
import { DEMO_VENDOR } from "../../data/mock/runs";
import { useData } from "../../data/useData";
import { SubmissionsTable } from "../../components/SubmissionsTable";

/** The vendor's own submissions; a row opens the same result view as on the ITSG side.
 * Hidden tests are left out: their result is pass / fail per rule on the test run page only. */
async function loadOwn() {
  const subs = (await getSubmissions()).filter((s) => s.vendor === DEMO_VENDOR);
  if (!isApi) return subs;
  const hidden = new Set((await getTestCases()).filter((t) => t.hidden).map((t) => t.id));
  return subs.filter((s) => !hidden.has(s.testCaseId));
}

export function VendorResultsScreen() {
  const { t } = useTranslation();
  const state = useData(loadOwn, []);

  return (
    <>
      <div className="page-header">
        <h1>{t("screens.vendorResults.title")}</h1>
        <p className="page-subtitle">{t("screens.vendorResults.subtitle")}</p>
      </div>
      <section className="panel panel-flush">
        {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
        {state.status === "error" && <p className="empty">{t("common.error")}</p>}
        {state.status === "ready" && <SubmissionsTable rows={state.data} basePath="/vendor/results" />}
      </section>
    </>
  );
}
