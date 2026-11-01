import { TERMS, type TermId } from "../i18n/terms";

// Shows a legal term exactly as the law and the specification write it.
export function Term({ id }: { id: TermId }) {
  return <span className="term">{TERMS[id]}</span>;
}
