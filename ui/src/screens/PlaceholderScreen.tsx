import { useTranslation } from "react-i18next";

// Temporary page for screens that are built in later steps.
export function PlaceholderScreen({ screen }: { screen: string }) {
  const { t } = useTranslation();
  return (
    <>
      <div className="page-header">
        <h1>{t(`screens.${screen}.title`)}</h1>
        <p className="page-subtitle">{t(`screens.${screen}.subtitle`)}</p>
      </div>
      <div className="placeholder">{t("placeholder")}</div>
    </>
  );
}
