import type { SpecRef } from "../data/types";

const DOCUMENT_NAMES: Record<SpecRef["document"], string> = {
  VB: "Verfahrensbeschreibung DTA EEL",
  GG: "Gemeinsame Grundsätze EEL",
  BP: "Beispielpapier",
};

/** "VB V13.3, 3.12 · DBVO Vorerkrankungen". German in both languages; full document name on hover. */
export function SpecRefText({ spec }: { spec: SpecRef }) {
  return (
    <span lang="de">
      <abbr title={DOCUMENT_NAMES[spec.document]}>{spec.document}</abbr> V{spec.version}, {spec.section}
      {spec.title && ` · ${spec.title}`}
    </span>
  );
}
