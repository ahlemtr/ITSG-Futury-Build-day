import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ParsedField } from "../records/parse";
import type { UploadedFile } from "../data/runStore";

/** Every field of the uploaded file by name, grouped by block (demo step 2). */
export function ParsedRecordView({ files }: { files: UploadedFile[] }) {
  const { t } = useTranslation();
  const [showEmpty, setShowEmpty] = useState(false);
  const visible = (f: ParsedField) => showEmpty || f.value !== "";

  return (
    <section className="sub-card">
      <div className="sub-card-head">
        <h3>{t("run.parsed.title")}</h3>
        <label className="toggle">
          <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} />
          {t("run.parsed.showEmpty")}
        </label>
      </div>
      {files.map((file) =>
        file.parsed.records.map((record, n) => (
          <div key={`${file.name}-${record.line}`} className="parsed-record">
            <p className="muted">
              {t("run.parsed.record", { file: file.name, n: n + 1, line: record.line })} · <strong>{record.abgabegrund}</strong>
            </p>
            <details>
              <summary>
                DSLW <span className="muted">· {t("run.parsed.fields", { count: record.head.length })}</span>
              </summary>
              <FieldTable fields={record.head.filter(visible)} />
            </details>
            {record.blocks.map((block) => (
              <details key={block.record} open={block.record === "DBVO"}>
                <summary>
                  {block.record} <span className="muted">· {block.title}</span>
                </summary>
                <FieldTable fields={block.fields.filter(visible)} />
                {block.groups && block.groups.length > 0 && (
                  <table className="list-table compact">
                    <thead>
                      <tr>
                        <th>{t("run.parsed.period")}</th>
                        {block.groups[0].map((f) => (
                          <th key={f.name}>{f.name.replace(/-\d+$/, "")}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {block.groups.map((g, i) => (
                        <tr key={i}>
                          <td>{i + 1}</td>
                          {g.map((f) => (
                            <td key={f.name}>{f.value || "–"}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </details>
            ))}
          </div>
        )),
      )}
    </section>
  );
}

function FieldTable({ fields }: { fields: ParsedField[] }) {
  const { t } = useTranslation();
  return (
    <table className="list-table compact">
      <thead>
        <tr>
          <th>{t("result.col.field")}</th>
          <th>{t("run.parsed.position")}</th>
          <th>{t("run.parsed.value")}</th>
        </tr>
      </thead>
      <tbody>
        {fields.map((f) => (
          <tr key={f.name}>
            <td className="cell-field">{f.name}</td>
            <td className="tabular muted">
              {f.start}–{f.end}
            </td>
            <td>{f.value || "–"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
