import { useEffect, useRef, useState, type FormEvent } from "react";
import cytoscape, { type Core } from "cytoscape";
import { useTranslation } from "react-i18next";
import {
  askGraph,
  getKgEvents,
  getKgStats,
  getSubgraph,
  toSpecRef,
  type KgAnswer,
  type KgEdge,
  type KgEvent,
  type KgNode,
} from "../data/api";
import { useData } from "../data/useData";
import { SpecRefText } from "../components/SpecRefText";

const COUNTED = ["DocVersion", "Passage", "Chunk", "Rule", "Parameter", "Change", "TestCase", "Precedent"];

/** Node colours of the graph view: one muted tone per kind, legend below the canvas. */
const KIND_COLORS: Record<string, string> = {
  Rule: "#1c2430",
  Passage: "#1f5fad",
  Parameter: "#9a5b00",
  ParamValue: "#c58a2b",
  TestCase: "#1e7b45",
  Change: "#b42318",
  Precedent: "#6b2fa3",
  Criterion: "#4b5563",
  Field: "#8a94a3",
  MessageType: "#8a94a3",
  DocVersion: "#5b6573",
};

/** The knowledge graph: the memory the AI works from. It grows with every upload, test and decision. */
export function KnowledgeGraphScreen() {
  const { t } = useTranslation();
  const stats = useData(getKgStats, []);
  const events = useData(getKgEvents, []);
  const [focus, setFocus] = useState<{ label: string; key: string }>({ label: "Rule", key: "R41-2" });

  return (
    <>
      <div className="page-header">
        <h1>{t("kg.title")}</h1>
        <p className="page-subtitle">{t("kg.subtitle")}</p>
      </div>

      <section className="panel">
        <div className="figures kg-figures">
          {COUNTED.map((label) => (
            <div key={label} className="figure">
              <span className="figure-value">{stats.status === "ready" ? stats.data.nodes[label] ?? 0 : "…"}</span>
              <span className="figure-label">{t(`kg.count.${label}`)}</span>
            </div>
          ))}
        </div>
        {stats.status === "ready" && (
          <p className="cell-hint">
            {t("kg.statsLine", {
              nodes: stats.data.total_nodes,
              edges: stats.data.edges ?? "–",
              embedded: stats.data.embedded_chunks,
              backend: stats.data.backend === "neo4j" ? "Neo4j" : "YAML",
              versions: stats.data.versions.join(", "),
            })}
          </p>
        )}
      </section>

      <div className="kg-layout">
        <section className="panel panel-flush">
          <div className="kg-graph-head">
            <h2 className="panel-title">{t("kg.graphTitle", { key: focus.key })}</h2>
            <span className="cell-hint">{t("kg.graphHint")}</span>
          </div>
          <GraphView focus={focus} onFocus={setFocus} />
        </section>
        <section className="panel">
          <h2 className="card-title">{t("kg.growth")}</h2>
          {events.status === "ready" && events.data.length === 0 && <p className="empty">{t("kg.noEvents")}</p>}
          {events.status === "ready" && (
            <ol className="kg-events">
              {events.data.map((e, i) => (
                <EventRow key={i} event={e} />
              ))}
            </ol>
          )}
        </section>
      </div>

      <AskPanel onFocus={setFocus} />
    </>
  );
}

function EventRow({ event }: { event: KgEvent }) {
  const { t } = useTranslation();
  const when = new Date(event.at).toLocaleString("de-DE", { dateStyle: "short", timeStyle: "short" });
  let text: string;
  if (event.kind === "spec_upload")
    text = t("kg.event.upload", {
      doc: event.document,
      version: event.version,
      passages: event.passages ?? 0,
      changes: event.in_scope ?? 0,
      params: (event.parameters_changed ?? []).join(", ") || "–",
      tests: (event.drafts ?? []).length,
    });
  else if (event.kind === "precedent") text = t("kg.event.precedent", { signature: event.signature, label: event.label });
  else if (event.kind === "baseline")
    text = t("kg.event.baseline", { doc: event.document, version: event.version, tests: event.test_cases ?? 0 });
  else text = event.kind;
  return (
    <li>
      <span className="cell-hint tabular">{when}</span>
      <span>{text}</span>
    </li>
  );
}

function GraphView({ focus, onFocus }: { focus: { label: string; key: string }; onFocus: (f: { label: string; key: string }) => void }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const [depth, setDepth] = useState(1);
  const graph = useData(() => getSubgraph(focus.label, focus.key, depth), [focus.label, focus.key, depth]);

  useEffect(() => {
    if (!box.current || graph.status !== "ready") return;
    const nodes = graph.data.nodes.filter((n) => n.label !== "Chunk");
    const keep = new Set(nodes.map((n) => `${n.label}:${n.key}`));
    const edges = graph.data.edges.filter((e) => keep.has(`${e.from_label}:${e.from_key}`) && keep.has(`${e.to_label}:${e.to_key}`));
    cy.current?.destroy();
    cy.current = cytoscape({
      container: box.current,
      elements: [
        ...nodes.map((n: KgNode) => ({
          data: { id: `${n.label}:${n.key}`, label: shortLabel(n), kind: n.label, key: n.key, focus: n.key === focus.key ? 1 : 0 },
        })),
        ...edges.map((e: KgEdge, i) => ({
          data: { id: `e${i}`, source: `${e.from_label}:${e.from_key}`, target: `${e.to_label}:${e.to_key}`, type: e.type },
        })),
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": (el) => KIND_COLORS[el.data("kind")] ?? "#8a94a3",
            label: "data(label)",
            "font-size": 10,
            "font-family": "Fira Sans, sans-serif",
            color: "#1c2430",
            "text-valign": "bottom",
            "text-margin-y": 4,
            width: 14,
            height: 14,
          },
        },
        { selector: "node[focus = 1]", style: { width: 24, height: 24, "border-width": 3, "border-color": "#d50032" } },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#c9d1db",
            "target-arrow-color": "#c9d1db",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(type)",
            "font-size": 7,
            color: "#8a94a3",
            "text-rotation": "autorotate",
          },
        },
      ],
      layout: { name: "cose", animate: true, animationDuration: 600, nodeRepulsion: () => 9000, idealEdgeLength: () => 90 },
      wheelSensitivity: 0.3,
    });
    cy.current.on("tap", "node", (ev) => {
      const kind = ev.target.data("kind") as string;
      if (["Rule", "Passage", "Parameter", "TestCase", "Change", "Precedent", "Criterion"].includes(kind))
        onFocus({ label: kind, key: ev.target.data("key") as string });
    });
    return () => {
      cy.current?.destroy();
      cy.current = null;
    };
  }, [graph, focus.key, onFocus]);

  return (
    <>
      <div className="kg-toolbar">
        <label className="toggle">
          <input type="checkbox" checked={depth === 2} onChange={(e) => setDepth(e.target.checked ? 2 : 1)} />
          {t("kg.depth2")}
        </label>
        <ul className="kg-legend">
          {Object.entries(KIND_COLORS)
            .filter(([k]) => !["Field", "MessageType", "Criterion"].includes(k))
            .map(([kind, color]) => (
              <li key={kind}>
                <span className="legend-swatch" style={{ background: color }} aria-hidden="true" />
                {t(`kg.count.${kind}`, { defaultValue: kind })}
              </li>
            ))}
        </ul>
      </div>
      {graph.status === "error" && <p className="empty">{t("common.error")}</p>}
      <div ref={box} className="kg-canvas" role="img" aria-label={t("kg.graphTitle", { key: focus.key })} />
    </>
  );
}

function shortLabel(n: KgNode): string {
  if (n.label === "Passage") return n.key.replace(/^([A-Z-]+)@([^#]+)#/, "$1 $2 ");
  if (n.label === "ParamValue") return `${n.key} = ${String(n.props.value)}`;
  if (n.label === "Change") return String(n.props.summary ?? n.key).slice(0, 40);
  if (n.label === "Criterion") return n.key.slice(0, 8);
  return n.key;
}

function AskPanel({ onFocus }: { onFocus: (f: { label: string; key: string }) => void }) {
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [answer, setAnswer] = useState<KgAnswer | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    try {
      setAnswer(await askGraph(q.trim()));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel kg-ask">
      <h2 className="card-title">{t("kg.ask.title")}</h2>
      <p className="card-subtitle">{t("kg.ask.hint")}</p>
      <form className="kg-ask-form" onSubmit={submit}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kg.ask.placeholder")} />
        <button type="submit" className="button button-primary" disabled={busy || !q.trim()}>
          {t(busy ? "kg.ask.running" : "kg.ask.submit")}
        </button>
      </form>
      {answer && answer.results.length === 0 && <p className="empty">{t("kg.ask.none")}</p>}
      {answer && answer.results.length > 0 && (
        <table className="list-table">
          <thead>
            <tr>
              <th>{t("kg.ask.passage")}</th>
              <th>{t("kg.ask.rules")}</th>
              <th>{t("kg.ask.tests")}</th>
            </tr>
          </thead>
          <tbody>
            {answer.results.map((r) => (
              <tr key={r.passage.key}>
                <td>
                  <button type="button" className="link-button" onClick={() => onFocus({ label: "Passage", key: r.passage.key })}>
                    <SpecRefText spec={toSpecRef(r.passage.key)} />
                  </button>
                  {r.passage.snippet && (
                    <div className="cell-hint" lang="de">
                      „{r.passage.snippet}“
                    </div>
                  )}
                  {r.changes.length > 0 && <div className="cell-hint">{t("kg.ask.changed", { count: r.changes.length })}</div>}
                </td>
                <td>
                  {r.rules.map((rule) => (
                    <button key={rule} type="button" className="chip" onClick={() => onFocus({ label: "Rule", key: rule })}>
                      {rule}
                    </button>
                  ))}
                  {r.rules.length === 0 && "–"}
                </td>
                <td>
                  {r.tests.map((tc) => (
                    <button key={tc} type="button" className="chip" onClick={() => onFocus({ label: "TestCase", key: tc })}>
                      {tc}
                    </button>
                  ))}
                  {r.tests.length === 0 && "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
