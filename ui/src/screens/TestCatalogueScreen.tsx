import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  approveTestCase,
  draftHidden,
  getTestCase,
  getTestCases,
  toSpecRef,
  type ApiTestCase,
  type ChainStep,
  type Expected,
  type TestCaseDetail,
} from "../data/api";
import { isApi } from "../data/dataSource";
import { useData } from "../data/useData";
import { SpecRefText } from "../components/SpecRefText";
import { formatDate } from "../format";

const STATUS_TONE: Record<ApiTestCase["status"], string> = { approved: "exact", draft: "unclear", rejected: "bug" };

/** Screen 3: test builder output. Drafts need a human approval before vendors get them. */
export function TestCatalogueScreen() {
  const { t } = useTranslation();
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const list = useData(() => (isApi ? getTestCases() : Promise.resolve(null)), [reload]);
  const cases = list.status === "ready" && list.data ? list.data.filter((c) => c.origin !== "pta") : [];
  const [selectedId, setSelectedId] = useState("peter-gap-exact");
  const selected = cases.find((c) => c.id === selectedId) ?? cases[0];
  const drafts = cases.filter((c) => c.status === "draft");

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    try {
      await fn();
    } finally {
      setBusy(false);
      setReload((n) => n + 1);
    }
  }

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{t("catalogue.title")}</h1>
          <p className="page-subtitle">{t("catalogue.subtitle", { count: cases.length, drafts: drafts.length })}</p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="button"
            disabled={busy || !selected || selected.hidden}
            onClick={() => selected && act(() => draftHidden(selected.id))}
          >
            {t("catalogue.hidden")}
          </button>
          <button
            type="button"
            className="button button-primary"
            disabled={busy || drafts.length === 0}
            onClick={() => act(() => Promise.all(drafts.map((d) => approveTestCase(d.id, "approved"))))}
          >
            {t("catalogue.approveAll", { count: drafts.length })}
          </button>
        </div>
      </div>

      {!isApi && <div className="placeholder">{t("report.apiOnly")}</div>}
      {list.status === "loading" && <p className="page-subtitle">{t("common.loading")}</p>}
      {list.status === "error" && <div className="placeholder">{t("common.error")}</div>}

      {cases.length > 0 && (
        <div className="split split-wide">
          <section className="panel panel-flush">
            <table className="list-table">
              <thead>
                <tr>
                  <th>{t("submissions.col.testCase")}</th>
                  <th>{t("catalogue.col.rules")}</th>
                  <th>{t("myTests.col.visibility")}</th>
                  <th>{t("myTests.col.status")}</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => (
                  <tr
                    key={c.id}
                    tabIndex={0}
                    className={`row-link${c.id === selected?.id ? " row-selected" : ""}`}
                    aria-selected={c.id === selected?.id}
                    onClick={() => setSelectedId(c.id)}
                    onKeyDown={(e) => e.key === "Enter" && setSelectedId(c.id)}
                  >
                    <td>
                      <span className="cell-field">{c.id}</span>
                      <div className="cell-hint">
                        {t(`catalogue.kind.${c.kind}`)}
                        {c.parent && ` · ${t("catalogue.from", { parent: c.parent })}`}
                        {c.result_changes.length > 0 && ` · ${t("catalogue.flips", { version: c.result_changes.join(", ") })}`}
                      </div>
                    </td>
                    <td className="cell-hint">
                      {c.targets.slice(0, 3).join(", ")}
                      {c.targets.length > 3 && ` +${c.targets.length - 3}`}
                    </td>
                    <td>
                      <span className={`badge ${c.hidden ? "badge-unclear" : "badge-neutral"}`}>{t(c.hidden ? "run.hidden" : "run.public")}</span>
                    </td>
                    <td>
                      <span className={`badge badge-${STATUS_TONE[c.status]}`}>{t(`catalogue.status.${c.status}`)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          {selected && <CaseDetail key={`${selected.id}-${reload}`} tc={selected} busy={busy} act={act} />}
        </div>
      )}
    </>
  );
}

function CaseDetail({ tc, busy, act }: { tc: ApiTestCase; busy: boolean; act: (fn: () => Promise<unknown>) => void }) {
  const { t } = useTranslation();
  const detail = useData(() => getTestCase(tc.id), [tc.id]);

  return (
    <aside className="panel explain">
      <p className="eyebrow">{t(`catalogue.kind.${tc.kind}`)}</p>
      <h2>{tc.id}</h2>
      <span className={`badge badge-${STATUS_TONE[tc.status]}`}>{t(`catalogue.status.${tc.status}`)}</span>
      {detail.status === "loading" && <p className="muted">{t("common.loading")}</p>}
      {detail.status === "error" && <p className="muted">{t("common.error")}</p>}
      {detail.status === "ready" && <DetailBody d={detail.data} />}
      {tc.status === "draft" && (
        <div className="decision-bar">
          <button type="button" className="button button-primary" disabled={busy} onClick={() => act(() => approveTestCase(tc.id, "approved"))}>
            {t("catalogue.approve")}
          </button>
          <button type="button" className="button" disabled={busy} onClick={() => act(() => approveTestCase(tc.id, "rejected"))}>
            {t("catalogue.reject")}
          </button>
        </div>
      )}
    </aside>
  );
}

function expectedText(e: Expected | undefined, t: (k: string, o?: Record<string, unknown>) => string): string {
  if (!e) return "–";
  if (!e.send_41) return t("spec.no41");
  return t("catalogue.with41", { count: e.periods.length, days: e.total_days ?? "–" });
}

function DetailBody({ d }: { d: TestCaseDetail }) {
  const { t } = useTranslation();
  const tc = d.test_case;
  const inp = tc.inputs;
  const lastPrior = [...inp.priors].sort((a, b) => b.end.localeCompare(a.end))[0];
  const versions = Object.keys(d.chains);
  const latest = versions[versions.length - 1];

  return (
    <>
      <div className="fact-tiles">
        {lastPrior && (
          <div className="fact-tile">
            <span className="cell-hint">{t("catalogue.fact.priorEnds")}</span>
            <strong className="tabular">{formatDate(lastPrior.end)}</strong>
          </div>
        )}
        <div className="fact-tile">
          <span className="cell-hint">{t("catalogue.fact.auFrom")}</span>
          <strong className="tabular">{formatDate(inp.current.start)}</strong>
        </div>
        <div className="fact-tile">
          <span className="cell-hint">{t("catalogue.fact.priors")}</span>
          <strong className="tabular">{inp.priors.length}</strong>
        </div>
      </div>

      <dl className="facts">
        {versions.map((v) => (
          <div key={v}>
            <dt>{t("catalogue.expected", { version: v })}</dt>
            <dd>{expectedText(tc.expected[v], t)}</dd>
          </div>
        ))}
      </dl>

      {latest && <RoundTable steps={d.chains[latest]} version={latest} />}

      <p className="cell-hint">
        {t("catalogue.footnote")}{" "}
        {tc.sources.map(toSpecRef).map((s, i) => (
          <span key={i}>
            {i > 0 && "; "}
            <SpecRefText spec={s} />
          </span>
        ))}
      </p>
    </>
  );
}

function RoundTable({ steps, version }: { steps: ChainStep[]; version: string }) {
  const { t } = useTranslation();
  const rounds = [...new Set(steps.map((s) => s.round))].sort((a, b) => a - b);
  if (rounds.length === 0) return <p className="hint-box">{t("catalogue.noMessages", { version })}</p>;
  const list = (r: number, actor: ChainStep["actor"]) =>
    steps
      .filter((s) => s.round === r && s.actor === actor)
      .map((s) => s.abgabegrund)
      .join(" + ") || "–";
  return (
    <table className="list-table compact">
      <thead>
        <tr>
          <th>{t("catalogue.col.round")}</th>
          <th>{t("catalogue.softwareMust", { version })}</th>
          <th>{t("catalogue.weSend")}</th>
        </tr>
      </thead>
      <tbody>
        {rounds.map((r) => (
          <tr key={r}>
            <td className="tabular">{r}</td>
            <td>{list(r, "employer")}</td>
            <td>{list(r, "insurer")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
