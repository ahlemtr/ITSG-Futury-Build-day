import { useTranslation } from "react-i18next";
import { getTestCases } from "../../data/api";
import { getSubmissions } from "../../data/dataSource";
import { DEMO_VENDOR } from "../../data/runTexts";
import { useData } from "../../data/useData";
import { SubmissionsTable } from "../../components/SubmissionsTable";
import { InfoTip } from "../../components/InfoTip";

/** The vendor's own submissions; a row opens the same result view as on the ITSG side.
 * Hidden tests are left out: their result is pass / fail per rule on the test run page only. */
async function loadOwn() {
  const subs = (await getSubmissions()).filter((s) => s.vendor === DEMO_VENDOR);
  const hidden = new Set((await getTestCases()).filter((t) => t.hidden).map((t) => t.id));
  return subs.filter((s) => !hidden.has(s.testCaseId));
}

export function VendorResultsScreen() {
  const { t } = useTranslation();
  const state = useData(loadOwn, []);

  return (
    <>
      <div className="page-header">
        <h1>
          {t("screens.vendorResults.title")}
          <InfoTip>{t("screens.vendorResults.subtitle")}</InfoTip>
        </h1>
      </div>
      <section className="panel panel-flush">
        {state.status === "loading" && <p className="empty">{t("common.loading")}</p>}
        {state.status === "error" && <p className="empty">{t("common.error")}</p>}
        {state.status === "ready" && <SubmissionsTable rows={state.data} basePath="/vendor/results" />}
      </section>
    </>
  );
}
