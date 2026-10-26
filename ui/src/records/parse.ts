// Reads DTA EEL files (TEEL0 / TEEK0) in the browser, driven by the record layouts.
// Port of plan/starter/layouts/parse_check.py. Display only: the official check is the backend's.
import layoutsJson from "./layouts.generated.json";
import type { Localized } from "../data/types";

type LayoutField = { name: string; start: number; end: number; type: string; format?: string };
type Layout = {
  record: string;
  title: string;
  status: string;
  fixedLength: number;
  fields: LayoutField[];
  blockOrder?: string[];
  repeatingGroup?: {
    countField: string;
    startsAt: number;
    groupLength: number;
    fields: (LayoutField & { offset: number; length: number })[];
  };
};

const LAYOUTS = layoutsJson as Record<string, Layout>;
const DSLW_LENGTH = LAYOUTS.DSLW.fixedLength;
const ENVELOPE = ["VOSZ", "DSKO", "NCSZ"];

export type ParsedField = {
  name: string;
  /** 1-based position in the line */
  start: number;
  end: number;
  raw: string;
  /** trimmed, dates as DD.MM.YYYY, "" when empty */
  value: string;
};

export type ParsedBlock = {
  record: string;
  title: string;
  fields: ParsedField[];
  /** DBVO: one list of fields per listed period */
  groups?: ParsedField[][];
};

export type ParseIssue = {
  line: number;
  record: string;
  field?: string;
  position?: number;
  message: Localized;
};

export type ParsedRecord = {
  line: number;
  abgabegrund: string;
  datensatzId: string;
  head: ParsedField[];
  blocks: ParsedBlock[];
};

export type ParsedFile = {
  lineKinds: string[];
  records: ParsedRecord[];
  issues: ParseIssue[];
};

function display(raw: string, field: LayoutField): string {
  const v = raw.trim();
  if (field.format === "date_yyyymmdd") {
    if (/^0*$/.test(v)) return "";
    return /^\d{8}$/.test(v) ? `${v.slice(6, 8)}.${v.slice(4, 6)}.${v.slice(0, 4)}` : v;
  }
  if (field.format === "amount_2dp" && /^\d+$/.test(v)) return (Number(v) / 100).toFixed(2);
  return v;
}

function readField(line: string, f: LayoutField, base: number, lineNo: number, record: string, issues: ParseIssue[]) {
  const raw = line.slice(base + f.start - 1, base + f.end);
  if (f.type === "n" && raw.trim() !== "" && !/^\d+$/.test(raw)) {
    issues.push({
      line: lineNo,
      record,
      field: f.name,
      position: base + f.start,
      message: {
        de: `Numerisches Feld enthält "${raw.trim()}"`,
        en: `Numeric field contains "${raw.trim()}"`,
      },
    });
  }
  return { name: f.name, start: base + f.start, end: base + f.end, raw, value: display(raw, f) };
}

function readBlock(line: string, pos: number, layout: Layout, lineNo: number, issues: ParseIssue[]) {
  const fields = layout.fields.map((f) => readField(line, f, pos, lineNo, layout.record, issues));
  let length = layout.fixedLength;
  const block: ParsedBlock = { record: layout.record, title: layout.title, fields };
  const rg = layout.repeatingGroup;
  if (rg) {
    const count = Number(fields.find((f) => f.name === rg.countField)?.raw ?? "0") || 0;
    block.groups = [];
    for (let k = 0; k < count; k++) {
      const base = pos + rg.startsAt - 1 + k * rg.groupLength;
      block.groups.push(
        rg.fields.map((f) =>
          readField(
            line,
            { ...f, name: f.name.replace("{nn}", String(k + 1)), start: f.offset, end: f.offset + f.length - 1 },
            base,
            lineNo,
            layout.record,
            issues,
          ),
        ),
      );
    }
    length += count * rg.groupLength;
  }
  return { block, length };
}

function readDslw(line: string, lineNo: number, issues: ParseIssue[]): ParsedRecord {
  const dslw = LAYOUTS.DSLW;
  const head = dslw.fields.map((f) => readField(line, f, 0, lineNo, "DSLW", issues));
  const value = (name: string) => head.find((f) => f.name === name)?.value ?? "";
  const flags = head.filter((f) => f.name.startsWith("MM-"));
  const blocks: ParsedBlock[] = [];
  let pos = DSLW_LENGTH;

  for (const [i, blockName] of (dslw.blockOrder ?? []).entries()) {
    if (flags[i]?.value !== "J") continue;
    const found = line.slice(pos, pos + 4);
    if (found !== blockName) {
      issues.push({
        line: lineNo,
        record: "DSLW",
        field: flags[i].name,
        position: pos + 1,
        message: {
          de: `${flags[i].name} = J, aber an Position ${pos + 1} steht "${found}" statt ${blockName}`,
          en: `${flags[i].name} = J, but position ${pos + 1} holds "${found}" instead of ${blockName}`,
        },
      });
      return { line: lineNo, abgabegrund: value("ABGABEGRUND"), datensatzId: value("DATENSATZ-ID"), head, blocks };
    }
    const layout = LAYOUTS[blockName];
    if (!layout || layout.status === "missing") {
      issues.push({
        line: lineNo,
        record: blockName,
        position: pos + 1,
        message: {
          de: `Layout von ${blockName} ist unbekannt, Rest der Zeile nicht gelesen`,
          en: `Layout of ${blockName} is unknown, rest of the line not read`,
        },
      });
      return { line: lineNo, abgabegrund: value("ABGABEGRUND"), datensatzId: value("DATENSATZ-ID"), head, blocks };
    }
    const { block, length } = readBlock(line, pos, layout, lineNo, issues);
    blocks.push(block);
    pos += length;
  }

  if (pos !== line.length) {
    issues.push({
      line: lineNo,
      record: "DSLW",
      message: {
        de: `Zeile hat ${line.length} Zeichen, die Layouts erklären ${pos}`,
        en: `Line has ${line.length} characters, the layouts account for ${pos}`,
      },
    });
  }
  return { line: lineNo, abgabegrund: value("ABGABEGRUND"), datensatzId: value("DATENSATZ-ID"), head, blocks };
}

export function parseText(text: string): ParsedFile {
  const issues: ParseIssue[] = [];
  const records: ParsedRecord[] = [];
  const lineKinds: string[] = [];
  text.split(/\r?\n/).forEach((line, i) => {
    if (line.trim() === "") return;
    const kind = line.slice(0, 4);
    lineKinds.push(kind);
    if (kind === "DSLW") records.push(readDslw(line, i + 1, issues));
    else if (!ENVELOPE.includes(kind)) {
      issues.push({
        line: i + 1,
        record: kind,
        message: { de: `Unbekannter Satz "${kind}"`, en: `Unknown record "${kind}"` },
      });
    }
  });
  if (records.length === 0) {
    issues.push({
      line: 0,
      record: "DSLW",
      message: { de: "Keine DSLW-Datensätze gefunden", en: "No DSLW records found" },
    });
  }
  return { lineKinds, records, issues };
}

/** EEL files are cp1252; the ITSG sample is UTF-8. Try UTF-8 first. */
export function decode(bytes: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

export async function sha256(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Value of a field in a parsed record, e.g. fieldValue(r, "DBID", "AKTENZEICHEN-VERURSACHER"). */
export function fieldValue(record: ParsedRecord, block: string, field: string): string {
  const fields = block === "DSLW" ? record.head : record.blocks.find((b) => b.record === block)?.fields;
  return fields?.find((f) => f.name === field)?.value ?? "";
}
