import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useActivities, type Activity, type ActivityStage } from "../data/aiActivity";
import { pick } from "../format";

/** Pinned to the top of every screen while the AI works in the background; the screen stays usable. */
export function AiOverlay() {
  const activities = useActivities();
  if (activities.length === 0) return null;
  return (
    <div className="ai-overlay" role="status" aria-live="polite">
      {activities.map((a) => (
        <ActivityCard key={a.id} activity={a} />
      ))}
    </div>
  );
}

function useElapsed(startedAt: number, running: boolean): string {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [running]);
  const s = Math.max(0, Math.round((now - startedAt) / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function ActivityCard({ activity }: { activity: Activity }) {
  const { t, i18n } = useTranslation();
  const running = activity.status === "running";
  const elapsed = useElapsed(activity.startedAt, running);
  const current = activity.stages?.find((s) => s.status === "running");
  return (
    <section className={`ai-card-overlay ai-${activity.status}`}>
      <div className="ai-head">
        <NeuralMark running={running} />
        <div className="ai-title">
          <strong>{pick(activity.title, i18n.language)}</strong>
          <span className="cell-hint">
            {running
              ? current
                ? pick(current.title, i18n.language)
                : t("ai.thinking")
              : t(activity.status === "done" ? "ai.done" : "ai.failed")}
          </span>
        </div>
        <span className="ai-elapsed tabular">{elapsed}</span>
      </div>
      {running && <div className="ai-progress" aria-hidden="true" />}
      {activity.stages && (
        <ol className="ai-stages">
          {activity.stages.map((s) => (
            <StageRow key={s.name} stage={s} />
          ))}
        </ol>
      )}
      {activity.error && <p className="field-error">{activity.error}</p>}
    </section>
  );
}

const SHOWN_COUNTS = [
  "passages", "chunks", "sections", "vectors", "changes", "candidates", "rules", "analysed", "param_changes",
  "parameters_changed", "in_scope", "flipped", "drafts", "rechecked", "skipped",
];

function StageRow({ stage }: { stage: ActivityStage }) {
  const { t, i18n } = useTranslation();
  const counts = SHOWN_COUNTS.filter((k) => stage.counts[k] !== undefined && stage.counts[k] !== 0);
  return (
    <li className={`ai-stage ai-stage-${stage.status}`}>
      <span className="ai-dot" aria-hidden="true" />
      <span>{pick(stage.title, i18n.language)}</span>
      <span className="cell-hint">
        {counts.map((k) => `${t(`ai.count.${k}`)} ${String(stage.counts[k])}`).join(" · ")}
      </span>
    </li>
  );
}

/** Five nodes and their links; the links light up one after the other while the AI works. */
function NeuralMark({ running }: { running: boolean }) {
  const nodes = [
    [6, 14], [18, 5], [18, 23], [30, 9], [30, 20],
  ];
  const links = [[0, 1], [0, 2], [1, 3], [2, 4], [1, 4], [2, 3]];
  return (
    <svg className={`neural${running ? " neural-running" : ""}`} viewBox="0 0 36 28" width="36" height="28" aria-hidden="true">
      {links.map(([a, b], i) => (
        <line key={i} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]} style={{ animationDelay: `${i * 0.18}s` }} />
      ))}
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r="2.6" style={{ animationDelay: `${i * 0.22}s` }} />
      ))}
    </svg>
  );
}
