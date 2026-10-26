import { useTranslation } from "react-i18next";
import type { Receipt } from "../data/types";
import { pick } from "../format";

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Receipt for an upload, like eVpT's processing confirmation. */
export function ReceiptCard({ receipt }: { receipt: Receipt }) {
  const { t, i18n } = useTranslation();
  return (
    <section className="sub-card">
      <div className="sub-card-head">
        <h3>{t("run.receipt.title")}</h3>
        <span className={`badge ${receipt.accepted ? "badge-exact" : "badge-bug"}`}>
          {t(receipt.accepted ? "run.receipt.accepted" : "run.receipt.rejected")}
        </span>
      </div>
      <p className="muted">{t("run.receipt.receivedAt", { time: formatTimestamp(receipt.receivedAt) })}</p>
      <table className="list-table compact">
        <thead>
          <tr>
            <th>{t("run.receipt.file")}</th>
            <th>{t("run.receipt.records")}</th>
            <th>SHA-256</th>
          </tr>
        </thead>
        <tbody>
          {receipt.files.map((f) => (
            <tr key={f.name}>
              <td>
                {f.name}
                <div className="cell-hint">{t("run.receipt.bytes", { count: f.size })}</div>
              </td>
              <td>
                {f.records.length === 0 && "–"}
                {f.records.map((r) => (
                  <div key={r.datensatzId + r.abgabegrund}>
                    <strong>{r.abgabegrund}</strong> <span className="mono cell-hint">{r.datensatzId}</span>
                  </div>
                ))}
              </td>
              <td className="mono hash" title={f.sha256}>
                {f.sha256.slice(0, 12)}…{f.sha256.slice(-6)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {receipt.issues.length > 0 && (
        <>
          <h4 className="issues-title">{t("run.receipt.issues", { count: receipt.issues.length })}</h4>
          <table className="list-table compact">
            <thead>
              <tr>
                <th>{t("run.receipt.line")}</th>
                <th>{t("result.col.block")}</th>
                <th>{t("result.col.field")}</th>
                <th>{t("run.receipt.position")}</th>
                <th>{t("run.receipt.message")}</th>
              </tr>
            </thead>
            <tbody>
              {receipt.issues.map((issue, i) => (
                <tr key={i}>
                  <td>{issue.line || "–"}</td>
                  <td>{issue.record}</td>
                  <td>{issue.field ?? "–"}</td>
                  <td>{issue.position ?? "–"}</td>
                  <td>{pick(issue.message, i18n.language)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
