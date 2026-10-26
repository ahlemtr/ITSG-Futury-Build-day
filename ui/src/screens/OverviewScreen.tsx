import { useTranslation } from "react-i18next";
import { getOverview, getSubmissions } from "../data/dataSource";
import type { OverviewData } from "../data/types";
import { useData } from "../data/useData";
import { SubmissionsTable } from "../components/SubmissionsTable";
import { formatDate } from "../format";

const LATEST_COUNT = 5;

export function OverviewScreen() {
  const { t } = useTranslation();
  const overview = useData(getOverview, []);
  const submissions = useData(getSubmissions, []);

  return (
    <>
      <div className="page-header">
        <h1>{t("screens.overview.title")}</h1>
        <p className="page-subtitle">{t("screens.overview.subtitle")}</p>
      </div>

      {overview.status === "loading" && <p className="page-subtitle">{t("common.loading")}</p>}
      {overview.status === "error" && <div className="placeholder">{t("common.error")}</div>}
      {overview.status === "ready" && <OverviewCards data={overview.data} />}

      <div className="overview-bottom">
        {overview.status === "ready" && <ResolutionCard data={overview.data.resolution} />}
        <section className="panel panel-flush">
          <h2 className="panel-title">{t("overview.latest")}</h2>
          {submissions.status === "ready" && (
            <SubmissionsTable rows={submissions.data.slice(0, LATEST_COUNT)} showRound={false} />
          )}
          {submissions.status === "error" && <p className="empty">{t("common.error")}</p>}
        </section>
      </div>
    </>
  );
}

function monthName(isoMonth: string, lang: string): string {
  const [y, m] = isoMonth.split("-").map(Number);
  return new Intl.DateTimeFormat(lang === "en" ? "en-GB" : "de-DE", { month: "long" }).format(
    new Date(y, m - 1, 1),
  );
}

function OverviewCards({ data }: { data: OverviewData }) {
  const { t, i18n } = useTranslation();
  const now = data.checksNow;
  const next = data.nextYear;
  return (
    <div className="overview-cards">
      <section className="panel">
        <h2 className="card-title">{t("overview.now.title")}</h2>
        <p className="card-subtitle">
          {t("overview.now.subtitle", { ruleSet: now.ruleSet, date: formatDate(now.validUntil) })}
        </p>
        <div className="figures">
          <Figure value={now.submissions} label={t("overview.now.submissions", { month: monthName(now.month, i18n.language) })} />
          <Figure value={now.passedAllRules} label={t("overview.now.passed")} />
          <Figure value={now.withOpenDeviations} label={t("overview.now.open")} attention />
        </div>
      </section>
      <section className="panel">
        <h2 className="card-title">{t("overview.next.title")}</h2>
        <p className="card-subtitle">
          {t("overview.next.subtitle", { ruleSet: next.ruleSet, date: formatDate(next.validFrom) })}
        </p>
        <div className="figures">
          <Figure value={next.specChangesInScope} label={t("overview.next.specChanges")} />
          <Figure value={next.testsToReapprove} label={t("overview.next.reapprove")} />
          <Figure value={next.hiddenVariantsReady} label={t("overview.next.hidden")} />
        </div>
      </section>
    </div>
  );
}

function Figure({ value, label, attention = false }: { value: number; label: string; attention?: boolean }) {
  return (
    <div className="figure">
      <span className={`figure-value${attention && value > 0 ? " figure-attention" : ""}`}>{value}</span>
      <span className="figure-label">{label}</span>
    </div>
  );
}

function ResolutionCard({ data }: { data: OverviewData["resolution"] }) {
  const { t } = useTranslation();
  const parts = [
    { key: "catalogueAndRules", value: data.catalogueAndRules, tone: "ink" },
    { key: "aiConfirmedByAdvisor", value: data.aiConfirmedByAdvisor, tone: "grey" },
    { key: "waitingForAdvisor", value: data.waitingForAdvisor, tone: "waiting" },
  ] as const;
  const total = parts.reduce((sum, p) => sum + p.value, 0);

  return (
    <section className="panel">
      <h2 className="card-title">{t("overview.resolution.title")}</h2>
      <p className="card-subtitle">{t("overview.resolution.subtitle", { count: total })}</p>
      <div className="stacked-bar" aria-hidden="true">
        {parts.map((p) => (
          <span key={p.key} className={`bar-${p.tone}`} style={{ flexGrow: p.value }} />
        ))}
      </div>
      <table className="legend-table">
        <tbody>
          {parts.map((p) => (
            <tr key={p.key}>
              <td>
                <span className={`legend-swatch bar-${p.tone}`} aria-hidden="true" />
                {t(`overview.resolution.${p.key}`)}
              </td>
              <td className="tabular">{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
