import { Trans, useTranslation } from "react-i18next";
import { LANGUAGES, setLanguage } from "../i18n";
import { useTopBarContent } from "./TopBarContext";

export function TopBar() {
  const { t, i18n } = useTranslation();
  const screenContext = useTopBarContent();
  return (
    <header className="topbar">
      <span className="wordmark">ITSG</span>
      <span className="product">{t("app.product")}</span>
      <span className="topbar-context">
        {screenContext ?? <Trans i18nKey="app.ruleSetContext" components={{ strong: <strong /> }} />}
      </span>
      <div className="lang-switch" role="group" aria-label={t("app.languageSwitch")}>
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
      <span className="avatar" title={t("app.user")}>
        IT
      </span>
    </header>
  );
}
