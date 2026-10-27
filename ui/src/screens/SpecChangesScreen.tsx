import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  getJobs,
  getSpecDiff,
  getVersions,
  toSpecRef,
  trackJob,
  uploadSpec,
  type ApiJob,
  type SpecChange,
  type SpecDiff,
} from "../data/api";
import { useData } from "../data/useData";
import { wordDiff, type DiffPart } from "../records/wordDiff";
import { SpecRefText } from "../components/SpecRefText";
import { formatDate } from "../format";

/** Documents a new version can be uploaded for: the Verfahrensbeschreibung, the Gemeinsame Grundsätze and the
 * insurers' Rundschreiben (calculation rules). */
const DOCUMENTS = ["VB", "GG", "RS-ANL1", "RS-ANL2", "RS-ANL3"];

/** Screen 2: a new specification arrives. Upload it; the platform chunks, embeds, diffs and analyses it, the
 * knowledge graph grows and the test catalogue is recomputed. Then: what changed and what it touches. */
export function SpecChangesScreen() {
  const { t } = useTranslation();
  const [reload, setReload] = useState(0);
  const versions = useData(() => getVersions("VB"), [reload]);
  const vb =
    versions.status === "ready"
      ? [...versions.data].sort((a, b) => String(a.valid_from).localeCompare(String(b.valid_from)))
      : [];
  const pair = vb.length >= 2 ? [vb[vb.length - 2].version, vb[vb.length - 1].version] : null;
  const diff = useData(() => (pair ? getSpecDiff(pair[0], pair[1]) : Promise.resolve(null)), [pair?.join("-")]);
  const [showUpload, setShowUpload] = useState(false);
  const known = versions.status === "ready";

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{pair ? t("spec.titlePair", { old: pair[0], new: pair[1] }) : t("spec.titleNone")}</h1>
          <p className="page-subtitle">
            {!known
              ? t("common.loading")
              : !pair
                ? t("spec.subtitleNone", { version: vb[0]?.version ?? "–" })
                : diff.status === "ready" && diff.data
                  ? t("spec.subtitle", { count: diff.data.changes.length, tests: diff.data.changedTests.length })
                  : t("spec.subtitleLoading")}
          </p>
        </div>
        {pair && (
          <div className="header-actions">
            <button type="button" className="button" onClick={() => setShowUpload((v) => !v)}>
              {t("spec.upload.open")}
            </button>
            <Link className="button button-primary" to="/test-catalogue">
              {t("spec.toCatalogue")}
            </Link>
          </div>
        )}
      </div>

      {known && (!pair || showUpload) && <UploadCard onDone={() => setReload((n) => n + 1)} />}

      {pair && diff.status === "loading" && <p className="page-subtitle">{t("spec.loading")}</p>}
      {pair && diff.status === "error" && <div className="placeholder">{t("common.error")}</div>}
      {diff.status === "ready" && diff.data && <SpecDiffView diff={diff.data} />}
    </>
  );
}

function UploadCard({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const [file, setFile] = useState<File | null>(null);
  const [document, setDocument] = useState("VB");
  const [version, setVersion] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<ApiJob | null>(null);
  const jobs = useData(getJobs, [last?.status]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const started = await uploadSpec(file, { document, version: version || undefined, validFrom: validFrom || undefined });
      const job = await trackJob(started);
      setLast(job);
      if (job.status === "done") onDone();
      else setError(job.error);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel upload-card">
      <h2 className="card-title">{t("spec.upload.title")}</h2>
      <p className="card-subtitle">{t("spec.upload.hint")}</p>
      <form className="upload-form" onSubmit={submit}>
        <label>
          <span className="field-label">{t("spec.upload.document")}</span>
          <select value={document} onChange={(e) => setDocument(e.target.value)} disabled={busy}>
            {DOCUMENTS.map((d) => (
              <option key={d} value={d}>
                {t(`spec.doc.${d}`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="field-label">{t("spec.upload.file")}</span>
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          <span className="field-label">{t("spec.upload.version")}</span>
          <input value={version} placeholder={t("spec.upload.auto")} onChange={(e) => setVersion(e.target.value)} disabled={busy} />
        </label>
        <label>
          <span className="field-label">{t("spec.upload.validFrom")}</span>
          <input type="date" value={validFrom} onChange={(e) => setValidFrom(e.target.value)} disabled={busy} />
        </label>
        <button type="submit" className="button button-primary" disabled={!file || busy}>
          {t(busy ? "spec.upload.running" : "spec.upload.submit")}
        </button>
      </form>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {last?.status === "done" && last.result.calculation_rules !== undefined && (
        <p className="saved-note" role="status">
          {t("spec.upload.doneCalc", {
            doc: t(`spec.doc.${last.document}`, { defaultValue: last.document }),
            version: last.version,
            rules: last.result.calculation_rules.length,
            proposals:
              (last.result.parameter_proposals ?? [])
                .map((p) => `${p.parameter}: ${String(p.current)} → ${String(p.proposed)}`)
                .join(", ") || "–",
          })}
        </p>
      )}
      {last?.status === "done" && last.result.calculation_rules === undefined && (
        <p className="saved-note" role="status">
          {t(last.result.track === "now" ? "spec.upload.doneNow" : "spec.upload.doneNext", {
            version: last.version,
            date: formatDate(last.valid_from),
            drafts: last.result.drafts?.length ?? 0,
            flipped: last.result.flipped?.length ?? 0,
          })}
        </p>
      )}
      {jobs.status === "ready" && jobs.data.length > 0 && (
        <table className="list-table compact">
          <thead>
            <tr>
              <th>{t("spec.upload.document")}</th>
              <th>{t("spec.upload.version")}</th>
              <th>{t("spec.upload.validFrom")}</th>
              <th>{t("myTests.col.status")}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.data.map((j) => (
              <tr key={j.id}>
                <td>{j.document}</td>
                <td>V{j.version}</td>
                <td>{formatDate(j.valid_from)}</td>
                <td>
                  <span className={`badge badge-${j.status === "done" ? "exact" : j.status === "failed" ? "bug" : "unclear"}`}>
                    {t(`spec.upload.status.${j.status}`)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

const isRuleChange = (c: SpecChange) => c.recompute.length > 0 || c.changes_param.length > 0;

function SpecDiffView({ diff }: { diff: SpecDiff }) {
  const { t } = useTranslation();
  const first = diff.changes.find(isRuleChange) ?? diff.changes[0];
  const [selectedKey, setSelectedKey] = useState(first?.key ?? "");
  const selected = diff.changes.find((c) => c.key === selectedKey) ?? first;

  return (
    <div className="queue-layout">
      <div className="queue-side">
        <section className="panel panel-flush">
          <ul className="queue-list">
            {diff.changes.map((c) => (
              <li key={c.key}>
                <button
                  type="button"
                  className={`queue-item${c.key === selected?.key ? " queue-item-selected" : ""}`}
                  aria-pressed={c.key === selected?.key}
                  onClick={() => setSelectedKey(c.key)}
                >
                  <span className="queue-item-head">
                    <strong>{[c.block, c.field].filter(Boolean).join(" · ") || c.key}</strong>
                    <span className={`badge ${isRuleChange(c) ? "badge-bug" : "badge-neutral"}`}>
                      {t(isRuleChange(c) ? "spec.ruleChange" : `spec.label.${c.label}`, { defaultValue: c.label })}
                    </span>
                  </span>
                  <span className="cell-hint">{c.summary ?? c.key}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      {selected && <ChangeDetail key={selected.key} change={selected} diff={diff} />}
    </div>
  );
}

function Parts({ parts }: { parts: DiffPart[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === "same" ? <span key={i}>{p.text}</span> : <mark key={i} className={`diff-${p.kind}`}>{p.text}</mark>,
      )}
    </>
  );
}

const showValue = (v: unknown) => (v === undefined ? "–" : JSON.stringify(v));

function periodsText(p: { send_41: boolean; periods: [string, string][]; total_days: number | null }, t: (k: string) => string) {
  if (!p.send_41) return t("spec.no41");
  return `41 · ${p.periods.map(([a, b]) => `${formatDate(a)}–${formatDate(b)}`).join(", ")}`;
}

function ChangeDetail({ change, diff }: { change: SpecChange; diff: SpecDiff }) {
  const { t } = useTranslation();
  const parts = wordDiff(change.old ?? "", change.new ?? "");
  const flips = change.recompute.length ? diff.recomputed.filter((r) => r.differs) : [];
  const drafts = (diff.agent ?? []).filter((d) => d.change_key === change.key);

  return (
    <section className="panel advisor-detail">
      <p className="eyebrow">{change.key}</p>
      <h2>{change.summary ?? change.key}</h2>
      <p className="cell-hint">
        {change.modifies_old.map(toSpecRef).map((s, i) => (
          <span key={`o${i}`}>
            <SpecRefText spec={s} />
            {" → "}
          </span>
        ))}
        {change.modifies_new.map(toSpecRef).map((s, i) => (
          <SpecRefText key={`n${i}`} spec={s} />
        ))}
      </p>

      <div className="passage-pair">
        <div className="fact-tile">
          <span className="cell-hint">{t("spec.old", { version: diff.oldVersion })}</span>
          <p className="passage" lang="de">
            <Parts parts={parts.old} />
          </p>
        </div>
        <div className="fact-tile">
          <span className="cell-hint">{t("spec.new", { version: diff.newVersion })}</span>
          <p className="passage" lang="de">
            <Parts parts={parts.new} />
          </p>
        </div>
      </div>

      <h3>{t("spec.impact")}</h3>
      <dl className="facts">
        <div>
          <dt>{t("spec.recompute")}</dt>
          <dd>{change.recompute.join(", ") || "–"}</dd>
        </div>
        <div>
          <dt>{t("spec.review")}</dt>
          <dd>{change.review.join(", ") || "–"}</dd>
        </div>
        {change.changes_param.map((p) => (
          <div key={p}>
            <dt>{t("spec.param")}</dt>
            <dd className="mono">
              {p}: {showValue(diff.params.old[p])} → {showValue(diff.params.new[p])}
            </dd>
          </div>
        ))}
      </dl>

      {flips.length > 0 && (
        <table className="list-table compact">
          <thead>
            <tr>
              <th>{t("spec.flips")}</th>
              <th>V{diff.oldVersion}</th>
              <th>V{diff.newVersion}</th>
            </tr>
          </thead>
          <tbody>
            {flips.map((f) => (
              <tr key={f.id}>
                <td className="cell-field">{f.id}</td>
                <td>{periodsText(f.old, t)}</td>
                <td>{periodsText(f.new, t)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {drafts.length > 0 && (
        <section className="sub-card ai-card">
          <div className="sub-card-head">
            <h3>{t("spec.agent")}</h3>
          </div>
          <ul className="rule-list">
            {drafts.map((d, i) => (
              <li key={i}>
                <strong>{t(`spec.decision.${d.decision}`)}</strong>
                {d.test_case_id && <span className="mono"> · {d.test_case_id}</span>}
                <div lang="de">{d.reasoning}</div>
                <div className="cell-hint">
                  {d.citations.map(toSpecRef).map((s, j) => (
                    <span key={j}>
                      {j > 0 && "; "}
                      <SpecRefText spec={s} />
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <p className="cell-hint">{t("advisor.draftOnly")}</p>
        </section>
      )}
    </section>
  );
}
