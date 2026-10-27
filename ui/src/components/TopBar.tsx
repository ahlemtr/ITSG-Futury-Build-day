import { useNavigate } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { getOverview } from "../data/api";
import { useData } from "../data/useData";
import { formatDate } from "../format";
import { LANGUAGES, setLanguage } from "../i18n";
import { useTopBarContent } from "./TopBarContext";
import { useView, type View } from "./useView";

const VIEWS: { view: View; home: string }[] = [
  { view: "itsg", home: "/" },
  { view: "vendor", home: "/vendor" },
];

export function TopBar() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const view = useView();
  const screenContext = useTopBarContent();
  // rule sets from the backend: before the 13.4 upload only the one in force is known
  const overview = useData(getOverview, []);
  const sets = overview.status === "ready" ? overview.data : undefined;
  const defaultContext =
    view === "vendor" ? "app.vendorContext" : sets?.nextYear ? "app.ruleSetContext" : "app.ruleSetContextOne";
  const contextValues = {
    now: sets?.checksNow.ruleSet ?? "",
    next: sets?.nextYear?.ruleSet ?? "",
    from: sets?.nextYear ? formatDate(sets.nextYear.validFrom) : "",
  };

  return (
    <header className="topbar">
      <span className="wordmark">ITSG</span>
      <span className="product">{t("app.product")}</span>
      <div className="segmented" role="group" aria-label={t("app.viewSwitch")}>
        {VIEWS.map((v) => (
          <button key={v.view} type="button" aria-pressed={view === v.view} onClick={() => navigate(v.home)}>
            {t(`app.view.${v.view}`)}
          </button>
        ))}
      </div>
      <span className="topbar-context">
        {screenContext ?? (sets || view === "vendor" ? <Trans i18nKey={defaultContext} values={contextValues} components={{ strong: <strong /> }} /> : null)}
      </span>
      <div className="segmented" role="group" aria-label={t("app.languageSwitch")}>
        {LANGUAGES.map((lang) => (
          <button
            key={lang}
            type="button"
            aria-pressed={i18n.language === lang}
            onClick={() => setLanguage(lang)}
          >
            {lang.toUpperCase()}
          </button>
        ))}
      </div>
      <span className="avatar" title={t(view === "vendor" ? "app.vendorUser" : "app.user")}>
        {view === "vendor" ? "HS" : "IT"}
      </span>
    </header>
  );
}
