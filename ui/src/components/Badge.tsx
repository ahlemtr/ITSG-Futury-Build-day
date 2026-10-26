import { useTranslation } from "react-i18next";
import type { FieldStatus, Label } from "../data/types";

// Result labels: always text plus colour, never colour alone.
const TONE: Record<Label | FieldStatus, string> = {
  exact: "exact",
  identical: "exact",
  valid: "exact",
  variant: "variant",
  bug: "bug",
  invalid: "invalid",
  unclear: "unclear",
  ignored: "neutral",
};

export function Badge({ value }: { value: Label | FieldStatus }) {
  const { t } = useTranslation();
  return <span className={`badge badge-${TONE[value]}`}>{t(`status.${value}`)}</span>;
}
