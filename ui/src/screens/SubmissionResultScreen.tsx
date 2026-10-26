import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Trans, useTranslation } from "react-i18next";
import { getSubmissionResult } from "../data/dataSource";
import type { Deviation, FieldRow, FieldStatus, SubmissionResult } from "../data/types";
import { useData } from "../data/useData";
import { Badge } from "../components/Badge";
import { SpecRefText } from "../components/SpecRefText";
import { useSetTopBar } from "../components/TopBarContext";
import { formatDate, pick } from "../format";

const CHIP_ORDER: FieldStatus[] = ["identical", "variant", "bug", "invalid", "unclear", "ignored", "valid"];

const isDeviation = (row: FieldRow) => row.deviationId !== undefined;
const rowKey = (row: FieldRow) => `${row.block}.${row.field}`;

export function SubmissionResultScreen() {
  const { id = "" } = useParams();
  const { t } = useTranslation();
  const state = useData(() => getSubmissionResult(id), [id]);
  const ruleSet = state.status === "ready" ? state.data?.ruleSet : undefined;

  useSetTopBar(
    ruleSet ? (
      <Trans i18nKey="result.topbar" values={{ id, ruleSet }} components={{ strong: <strong /> }} />
    ) : null,
    [id, ruleSet],
  );

  if (state.status === "loading") return <p className="page-subtitle">{t("common.loading")}</p>;
  if (state.status === "error") return <div className="placeholder">{t("common.error")}</div>;
  if (!state.data) return <div className="placeholder">{t("result.notFound")}</div>;
  return <ResultView result={state.data} />;
}

function ResultView({ result }: { result: SubmissionResult }) {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<FieldStatus | "all">("all");
  const [onlyDeviations, setOnlyDeviations] = useState(false);
  const firstDeviation = result.fields.find(isDeviation) ?? result.fields[0];
  const [selectedKey, setSelectedKey] = useState(firstDeviation ? rowKey(firstDeviation) : "");

  const counts = new Map<FieldStatus, number>();
  for (const row of result.fields) counts.set(row.status, (counts.get(row.status) ?? 0) + 1);

  const rows = result.fields.filter(
    (row) => (filter === "all" || row.status === filter) && (!onlyDeviations || isDeviation(row)),
  );
  const selected = result.fields.find((row) => rowKey(row) === selectedKey);
  const deviation = selected?.deviationId
    ? result.deviations.find((d) => d.id === selected.deviationId)
    : undefined;

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>
            {result.testCaseId} · {result.vendor}
          </h1>
          <p className="page-subtitle">
            {t("result.subtitle", {
              round: result.round,
              total: result.roundsTotal,
              kind: result.fileKind,
              date: formatDate(result.receivedOn),
              ruleSet: result.ruleSet,
            })}
          </p>
        </div>
        <div className="header-actions">
          <span className="verdict">
            {t("result.verdict")} <Badge value={result.verdict} />
          </span>
          <Link className="button button-primary" to="/reports">
            {t("result.openReport")}
          </Link>
        </div>
      </div>

      <div className="toolbar">
        <div className="chips" role="group" aria-label={t("result.filter")}>
          <button
            type="button"
            className="chip"
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}
          >
            {t("chips.all")} <span className="chip-count">{result.fields.length}</span>
          </button>
          {CHIP_ORDER.filter((s) => counts.has(s)).map((status) => (
            <button
              key={status}
              type="button"
              className={`chip chip-${status}`}
              aria-pressed={filter === status}
              onClick={() => setFilter(filter === status ? "all" : status)}
            >
              {t(`chips.${status}`)} <span className="chip-count">{counts.get(status)}</span>
            </button>
          ))}
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyDeviations}
            onChange={(e) => setOnlyDeviations(e.target.checked)}
          />
          {t("result.onlyDeviations")}
        </label>
      </div>

      <div className="split">
        <section className="panel panel-flush">
          <table className="diff-table">
            <thead>
              <tr>
                <th>{t("result.col.block")}</th>
                <th>{t("result.col.field")}</th>
                <th>{t("result.col.expected")}</th>
                <th>{t("result.col.actual")}</th>
                <th>{t("result.col.mode")}</th>
                <th>{t("result.col.label")}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const key = rowKey(row);
                const quiet = !isDeviation(row);
                return (
                  <tr
                    key={key}
                    tabIndex={0}
                    aria-selected={key === selectedKey}
                    className={`${quiet ? "row-quiet" : "row-deviation"}${key === selectedKey ? " row-selected" : ""}`}
                    onClick={() => setSelectedKey(key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setSelectedKey(key);
                      }
                    }}
                  >
                    <td>{row.block}</td>
                    <td className="cell-field">{row.field}</td>
                    <td className="cell-value">
                      <Value value={row.expected} />
                    </td>
                    <td className="cell-value">
                      <Value value={row.actual} />
                      {row.vendorField && (
                        <div className="cell-hint">{t("result.vendorField", { field: row.vendorField })}</div>
                      )}
                    </td>
                    <td>{t(`mode.${row.mode}`)}</td>
                    <td>
                      <Badge value={row.status} />
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="empty">
                    {t("result.noRows")}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </section>

        <aside className="panel explain" aria-live="polite">
          {deviation ? (
            <DeviationPanel deviation={deviation} lang={i18n.language} />
          ) : selected ? (
            <FieldPanel row={selected} lang={i18n.language} />
          ) : null}
        </aside>
      </div>
    </>
  );
}

function Value({ value }: { value: string | null }) {
  const { t } = useTranslation();
  if (value === null || value === "") {
    return (
      <span className="missing" title={t("result.empty")}>
        –
      </span>
    );
  }
  return <span title={value}>{value}</span>;
}

function DeviationPanel({ deviation, lang }: { deviation: Deviation; lang: string }) {
  const { t } = useTranslation();
  return (
    <>
      <p className="eyebrow">{t("result.why")}</p>
      <h2>{pick(deviation.title, lang)}</h2>
      <Badge value={deviation.label} />
      <dl className="facts">
        <div>
          <dt>{t("result.decidedBy")}</dt>
          <dd>{t(`decidedBy.${deviation.decidedBy}`)}</dd>
        </div>
        <div>
          <dt>{t("result.rule")}</dt>
          <dd>
            <strong>{deviation.rule.id}</strong> · {pick(deviation.rule.text, lang)}
          </dd>
        </div>
        <div>
          <dt>{t("result.specPassage")}</dt>
          <dd>
            <SpecRefText spec={deviation.spec} />
          </dd>
        </div>
        {deviation.criterion && (
          <div>
            <dt>{t("result.criterion")}</dt>
            <dd>
              {pick(deviation.criterion.text, lang)}
              <div className="cell-hint">{deviation.criterion.id}</div>
            </dd>
          </div>
        )}
        <div>
          <dt>{t("result.reasoning")}</dt>
          <dd>{pick(deviation.reasoning, lang)}</dd>
        </div>
      </dl>
    </>
  );
}

function FieldPanel({ row, lang }: { row: FieldRow; lang: string }) {
  const { t } = useTranslation();
  return (
    <>
      <p className="eyebrow">{t("result.fieldInfo")}</p>
      <h2>
        {row.block} · {row.field}
      </h2>
      <Badge value={row.status} />
      <dl className="facts">
        <div>
          <dt>{t("result.col.mode")}</dt>
          <dd>
            <strong>{t(`mode.${row.mode}`)}</strong> · {t(`modeHint.${row.mode}`)}
          </dd>
        </div>
        <div>
          <dt>{t("result.explanation")}</dt>
          <dd>{row.note ? pick(row.note, lang) : t("result.identicalNote")}</dd>
        </div>
        {row.source && (
          <div>
            <dt>{t("result.source")}</dt>
            <dd>
              <SpecRefText spec={row.source} />
            </dd>
          </div>
        )}
      </dl>
    </>
  );
}
