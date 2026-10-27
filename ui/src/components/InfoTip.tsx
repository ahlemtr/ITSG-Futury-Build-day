import { useId, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** An explanation behind a small "i": shown on hover and keyboard focus, read out with the button. */
export function InfoTip({ children, label }: { children: ReactNode; label?: string }) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <span className="infotip">
      <button type="button" className="infotip-button" aria-label={label ?? t("common.info")} aria-describedby={id}>
        i
      </button>
      <span role="tooltip" id={id} className="infotip-text">
        {children}
      </span>
    </span>
  );
}

/** AI or rule reasoning, folded: the decision stays visible, the why opens on demand. */
export function Reasoning({ children, label }: { children: ReactNode; label?: string }) {
  const { t } = useTranslation();
  return (
    <details className="reasoning">
      <summary>{label ?? t("common.why")}</summary>
      <div className="reasoning-body">{children}</div>
    </details>
  );
}

/** A number with its label, for results that used to be a sentence. */
export function Stat({ value, label, attention = false }: { value: ReactNode; label: string; attention?: boolean }) {
  return (
    <span className={`stat${attention ? " stat-attention" : ""}`}>
      <strong className="tabular">{value}</strong> {label}
    </span>
  );
}
