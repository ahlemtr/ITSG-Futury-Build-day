import { useTranslation } from "react-i18next";

/** Pass / fail badge for hidden tests and per-rule results (text plus colour). */
export function PassFail({ passed }: { passed: boolean }) {
  const { t } = useTranslation();
  return <span className={`badge ${passed ? "badge-exact" : "badge-bug"}`}>{t(passed ? "run.passed" : "run.failed")}</span>;
}
