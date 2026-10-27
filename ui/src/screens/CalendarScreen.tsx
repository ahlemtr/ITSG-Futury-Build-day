import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getCalendar, isPressing, type CalendarData, type CatalogueEvent, type Company, type Deadline } from "../data/api";
import { addDays, daysBetween, deadlineCode, deadlineTitle, dueText, monthLabel, toDate } from "../data/deadlines";
import { DEMO_VENDOR } from "../data/runTexts";
import { useData } from "../data/useData";
import { formatDate } from "../format";

/** Days before and after today on the timeline: two weeks back, about three months ahead (past the 1 January switch). */
const BACK = 14;
const AHEAD = 98;

type Filter = "open" | "pressing" | "done" | "all";

const FILTERS: Record<Filter, (d: Deadline) => boolean> = {
  open: (d) => !d.done,
  pressing: isPressing,
  done: (d) => d.done,
  all: () => true,
};

/** Deadlines per vendor company: ITSG sees all companies and the catalogue's history, the vendor its own. */
export function CalendarScreen({ vendor = false }: { vendor?: boolean }) {
  const { t } = useTranslation();
  const data = useData(() => getCalendar(vendor ? DEMO_VENDOR : undefined), [vendor]);

  return (
    <>
      <div className="page-header">
        <h1>{t("screens.calendar.title")}</h1>
        <p className="page-subtitle">{t(vendor ? "screens.calendar.vendorSubtitle" : "screens.calendar.subtitle")}</p>
      </div>
      {data.status === "loading" && <p className="page-subtitle">{t("common.loading")}</p>}
      {data.status === "error" && <div className="placeholder">{t("common.error")}</div>}
      {data.status === "ready" && <Calendar data={data.data} vendor={vendor} />}
    </>
  );
}

function Calendar({ data, vendor }: { data: CalendarData; vendor: boolean }) {
  const [filter, setFilter] = useState<Filter>("open");
  const rows = data.deadlines.filter(FILTERS[filter]);
  return (
    <div className="calendar">
      {vendor && <Reminders deadlines={data.deadlines} />}
      <Timeline data={data} vendor={vendor} />
      <div className={vendor ? undefined : "split"}>
        <DeadlineList rows={rows} all={data.deadlines} companies={data.companies} vendor={vendor} filter={filter} onFilter={setFilter} />
        {!vendor && <History events={data.history} />}
      </div>
    </div>
  );
}

// ---------- Vendor: what is due next ----------

function Reminders({ deadlines }: { deadlines: Deadline[] }) {
  const { t, i18n } = useTranslation();
  const pressing = deadlines.filter(isPressing);
  const next = deadlines.find((d) => !d.done);
  const shown = pressing.length ? pressing : next ? [next] : [];
  return (
    <section className="panel reminders" aria-labelledby="reminders-title">
      <h2 id="reminders-title" className="card-title">
        {pressing.length ? t("calendar.reminders.title", { count: pressing.length }) : t("calendar.reminders.none")}
      </h2>
      <ul className="reminder-list">
        {shown.map((d) => (
          <li key={d.id} className={`reminder reminder-${d.status}`}>
            <span className="reminder-days tabular">{d.days < 0 ? `+${-d.days}` : d.days}</span>
            <span className="reminder-unit">{t(d.days < 0 ? "calendar.reminders.daysLate" : "calendar.reminders.daysLeft", { count: Math.abs(d.days) })}</span>
            <span className="reminder-text">
              <strong>{deadlineTitle(t, d, i18n.language)}</strong>
              <span className="cell-hint">{t("calendar.dueOn", { date: formatDate(d.due) })}</span>
            </span>
            {d.kind === "round" && d.params.test_case && (
              <Link className="button" to={`/vendor/runs/${d.params.test_case}`}>
                {t("calendar.openRun")}
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

// ---------- Timeline: companies down, days across ----------

type Row = { id: string | null; name: string; sub: string; deadlines: Deadline[] };

function Timeline({ data, vendor }: { data: CalendarData; vendor: boolean }) {
  const { t, i18n } = useTranslation();
  const today = toDate(data.today);
  const start = addDays(today, -BACK);
  const span = BACK + AHEAD;
  const at = (iso: string) => (daysBetween(start, toDate(iso)) / span) * 100;
  const inRange = (iso: string) => {
    const n = daysBetween(start, toDate(iso));
    return n >= 0 && n <= span;
  };

  const rows: Row[] = useMemo(() => {
    const byCompany = (id: string | null) => data.deadlines.filter((d) => d.company_id === id);
    const out: Row[] = vendor ? [] : [{ id: null, name: "ITSG", sub: t("calendar.itsgRow"), deadlines: byCompany(null) }];
    for (const c of data.companies) out.push({ id: c.id, name: c.name, sub: companySub(t, c), deadlines: byCompany(c.id) });
    return out;
  }, [data, vendor, t]);

  const months = useMemo(() => {
    const out: { iso: string; left: number }[] = [];
    let m = new Date(start.getFullYear(), start.getMonth() + 1, 1);
    while (daysBetween(start, m) <= span) {
      const iso = `${m.getFullYear()}-${String(m.getMonth() + 1).padStart(2, "0")}-01`;
      out.push({ iso, left: at(iso) });
      m = new Date(m.getFullYear(), m.getMonth() + 1, 1);
    }
    return out;
  }, [data.today]);

  const switches = data.deadlines.filter((d) => d.kind === "switch" && inRange(d.due));
  const kinds = new Set(data.deadlines.filter((d) => inRange(d.due)).map((d) => d.kind));

  return (
    <section className="panel panel-flush timeline-panel" aria-labelledby="timeline-title">
      <div className="timeline-head">
        <h2 id="timeline-title" className="panel-title">
          {t("calendar.timeline", { from: formatDate(start.toISOString().slice(0, 10)), to: formatDate(addDays(start, span).toISOString().slice(0, 10)) })}
        </h2>
        <Legend kinds={kinds} />
      </div>
      <div className="timeline-scroll">
        <div className="timeline" role="table" aria-label={t("calendar.timelineLabel")}>
          <div className="tl-row tl-axis" role="row">
            <div className="tl-name" role="columnheader">{t("calendar.company")}</div>
            <div className="tl-track" role="columnheader">
              {months.map((m) => (
                <span key={m.iso} className="tl-month" style={{ left: `${m.left}%` }}>
                  {monthLabel(m.iso.slice(0, 7), i18n.language, "short")}
                </span>
              ))}
              <span className="tl-today-label" style={{ left: `${at(data.today)}%` }}>
                {t("calendar.today", { date: formatDate(data.today).slice(0, 6) })}
              </span>
            </div>
          </div>
          {rows.map((row) => (
            <div key={row.id ?? "itsg"} className={rowClass(row, inRange)} role="row">
              <div className="tl-name" role="rowheader">
                <span className="tl-company">{row.name}</span>
                <span className="cell-hint">{row.sub}</span>
              </div>
              <div className="tl-track" role="cell">
                {months.map((m) => (
                  <span key={m.iso} className="tl-gridline" style={{ left: `${m.left}%` }} aria-hidden="true" />
                ))}
                {switches.map((s) => (
                  <span key={s.id} className="tl-switch" style={{ left: `${at(s.due)}%` }} aria-hidden="true" />
                ))}
                <span className="tl-today" style={{ left: `${at(data.today)}%` }} aria-hidden="true" />
                {row.deadlines
                  .filter((d) => d.kind === "round" && d.opened && (inRange(d.due) || inRange(d.opened)))
                  .map((d) => {
                    const left = Math.max(0, at(d.opened!));
                    const width = Math.max(1.2, Math.min(100, at(d.due)) - left);
                    return (
                      <span
                        key={d.id}
                        className={`tl-bar tl-${d.status}`}
                        style={{ left: `${left}%`, width: `${width}%` }}
                        title={`${deadlineTitle(t, d, i18n.language)} · ${formatDate(d.due)} · ${dueText(t, d)}`}
                      >
                        {width > 9 ? deadlineTitle(t, d, i18n.language) : deadlineCode(t, d)}
                      </span>
                    );
                  })}
                {marks(row.deadlines.filter((d) => d.kind !== "round" && inRange(d.due))).map((group) => (
                  <Mark key={group[0].due} group={group} left={at(group[0].due)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/** A row with test run rounds gets two lanes: the round bars above, the point deadlines below. */
function rowClass(row: Row, inRange: (iso: string) => boolean): string {
  const lanes = row.deadlines.some((d) => d.kind === "round" && d.opened && (inRange(d.due) || inRange(d.opened)));
  return ["tl-row", row.id === null && "tl-row-itsg", lanes && "tl-row-lanes"].filter(Boolean).join(" ");
}

/** Deadlines of one row on the same day share one mark; the weightiest kind gives it its shape. */
const WEIGHT: Record<string, number> = { switch: 0, catalogue: 1, recert: 2, permanent: 3 };
function marks(deadlines: Deadline[]): Deadline[][] {
  const byDay = new Map<string, Deadline[]>();
  for (const d of deadlines) byDay.set(d.due, [...(byDay.get(d.due) ?? []), d]);
  return [...byDay.values()].map((g) => g.sort((a, b) => WEIGHT[a.kind] - WEIGHT[b.kind]));
}

function Mark({ group, left }: { group: Deadline[]; left: number }) {
  const { t, i18n } = useTranslation();
  const lead = group[0];
  // one status for the mark: overdue wins, then soon; done only when all are done
  const status = group.find((d) => d.status === "overdue")?.status ?? group.find((d) => d.status === "soon")?.status ?? (group.every((d) => d.done) ? "done" : "open");
  const title = group.map((d) => `${deadlineTitle(t, d, i18n.language)} · ${dueText(t, d)}`).join("\n");
  const label = group.map((d) => deadlineCode(t, d)).join(" + ");
  return (
    <span className={`tl-mark tl-mark-${lead.kind} tl-${status}`} style={{ left: `${left}%` }} title={`${formatDate(lead.due)}\n${title}`}>
      <span className="tl-glyph" aria-hidden="true">{status === "done" ? "✓" : ""}</span>
      <span className="tl-mark-label">{label}</span>
    </span>
  );
}

function Legend({ kinds }: { kinds: Set<string> }) {
  const { t } = useTranslation();
  const order = ["round", "recert", "permanent", "catalogue", "switch"].filter((k) => kinds.has(k));
  return (
    <ul className="tl-legend">
      {order.map((k) => (
        <li key={k}>
          <span className={`tl-swatch tl-swatch-${k}`} aria-hidden="true" />
          {t(`calendar.legend.${k}`)}
        </li>
      ))}
      <li>
        <span className="tl-swatch tl-swatch-overdue" aria-hidden="true" />
        {t("calendar.status.overdue")}
      </li>
    </ul>
  );
}

function companySub(t: (k: string, o?: Record<string, unknown>) => string, c: Company): string {
  const cert = c.certified_until
    ? t("calendar.certifiedUntil", { date: formatDate(c.certified_until) })
    : t("calendar.firstCertification");
  return cert;
}

// ---------- List ----------

function DeadlineList({
  rows,
  all,
  companies,
  vendor,
  filter,
  onFilter,
}: {
  rows: Deadline[];
  all: Deadline[];
  companies: Company[];
  vendor: boolean;
  filter: Filter;
  onFilter: (f: Filter) => void;
}) {
  const { t, i18n } = useTranslation();
  const names = new Map(companies.map((c) => [c.id, c.name]));
  return (
    <section className="panel panel-flush" aria-labelledby="deadline-list-title">
      <div className="list-head">
        <h2 id="deadline-list-title" className="panel-title">{t("calendar.list")}</h2>
        <div className="chips" role="group" aria-label={t("calendar.filter")}>
          {(Object.keys(FILTERS) as Filter[]).map((f) => (
            <button key={f} type="button" className="chip" aria-pressed={filter === f} onClick={() => onFilter(f)}>
              {t(`calendar.filters.${f}`)} <span className="chip-count">{all.filter(FILTERS[f]).length}</span>
            </button>
          ))}
        </div>
      </div>
      <table className="list-table">
        <thead>
          <tr>
            <th>{t("calendar.col.due")}</th>
            {!vendor && <th>{t("calendar.company")}</th>}
            <th>{t("calendar.col.what")}</th>
            <th>{t("calendar.col.status")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id} className={d.done ? "row-quiet" : undefined}>
              <td className="tabular cell-field">{formatDate(d.due)}</td>
              {!vendor && <td>{d.company_id ? names.get(d.company_id) : "ITSG"}</td>}
              <td>{deadlineTitle(t, d, i18n.language)}</td>
              <td>
                <span className={`badge badge-${d.status === "overdue" ? "bug" : d.done ? "exact" : "neutral"}`}>{dueText(t, d)}</span>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={vendor ? 3 : 4} className="empty">
                {t("calendar.empty")}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}

// ---------- ITSG: how the catalogue evolved ----------

function History({ events }: { events: CatalogueEvent[] }) {
  const { t } = useTranslation();
  return (
    <section className="panel" aria-labelledby="history-title">
      <h2 id="history-title" className="card-title">{t("calendar.history.title")}</h2>
      {events.length === 0 && <p className="empty">{t("calendar.history.empty")}</p>}
      <ol className="history">
        {events.map((e, i) => (
          <li key={i} className={`history-${e.kind}`}>
            <span className="cell-hint tabular">{formatDate(e.at.slice(0, 10))}</span>
            <span>{historyText(t, e)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function historyText(t: (k: string, o?: Record<string, unknown>) => string, e: CatalogueEvent): string {
  switch (e.kind) {
    case "baseline":
      return t("calendar.history.baseline", { version: e.version, count: e.tests });
    case "spec_upload":
      return t("calendar.history.upload", { document: e.document, version: e.version, date: formatDate(e.valid_from), drafts: e.drafts, flipped: e.flipped });
    case "approval":
      return t(`calendar.history.${e.decision}`, { testCase: e.test_case });
  }
}
