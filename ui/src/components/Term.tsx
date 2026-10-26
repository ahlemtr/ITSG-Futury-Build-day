import { useTranslation } from "react-i18next";
import { TERMS, type TermId } from "../i18n/terms";

// Shows a legal term in German. In English mode, the meaning appears on hover.
export function Term({ id }: { id: TermId }) {
  const { i18n } = useTranslation();
  const term = TERMS[id];
  const isEnglish = i18n.language === "en";
  return (
    <span className="term" lang="de" title={isEnglish ? term.en : undefined}>
      {term.de}
    </span>
  );
}
