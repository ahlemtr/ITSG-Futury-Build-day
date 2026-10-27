import { useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { decide, resetAdvisor, useAdvisorState } from "../data/advisorStore";
import { isApi } from "../data/dataSource";
import { ADVISOR_ITEMS } from "../data/mock/advisor";
import type { AdvisorItem, Precedent } from "../data/types";
import { Badge } from "../components/Badge";
import { SpecRefText } from "../components/SpecRefText";
import { useSetTopBar } from "../components/TopBarContext";
import { pick } from "../format";

const DECISIONS: Precedent["label"][] = ["variant", "bug", "invalid"];
const ADVISOR = "SA";
const ADVISOR_FIRST_ID = ADVISOR_ITEMS[0]?.id ?? "";

export function AdvisorQueueScreen() {
  const { t, i18n } = useTranslation();
  const { open, decided, status } = useAdvisorState();
  const [selectedId, setSelectedId] = useState(open[0]?.id ?? "");
  const [lastSaved, setLastSaved] = useState<Precedent | null>(null);
  const [failed, setFailed] = useState(false);
  const selected = open.find((i) => i.id === selectedId) ?? open[0];

  useSetTopBar(<Trans i18nKey="advisor.topbar" values={{ count: open.length }} components={{ strong: <strong /> }} />, [
    open.length,
  ]);

  async function onDecide(item: AdvisorItem, label: Precedent["label"], reason: string) {
    let precedent: Precedent | undefined;
    try {
      precedent = await decide(item.id, label, reason, ADVISOR);
      setFailed(false);
    } catch {
      setFailed(true);
      return;
    }
    if (!precedent) return;
    setLastSaved(precedent);
    const next = open.find((i) => i.id !== item.id);
    setSelectedId(next?.id ?? "");
  }

  return (
    <>
      <div className="page-header page-header-split">
        <div>
          <h1>{t("screens.advisorQueue.title")}</h1>
          <p className="page-subtitle">{t("screens.advisorQueue.subtitle")}</p>
        </div>
        {decided.length > 0 && !isApi && (
          <div className="header-actions">
            <button
              type="button"
              className="button"
              onClick={() => {
                resetAdvisor();
                setLastSaved(null);
                setSelectedId(ADVISOR_FIRST_ID);
              }}
            >
              {t("advisor.resetDemo")}
            </button>
          </div>
        )}
      </div>

      {lastSaved && (
        <p className="saved-note" role="status">
          {t("advisor.saved", { id: lastSaved.id, label: t(`status.${lastSaved.label}`) })}
        </p>
      )}

      {failed && (
        <p className="field-error" role="alert">
          {t("common.error")}
        </p>
      )}

      <div className="queue-layout">
        <div className="queue-side">
          <section className="panel panel-flush">
            {status === "loading" && <p className="empty">{t("common.loading")}</p>}
            {status === "error" && <p className="empty">{t("common.error")}</p>}
            {status === "ready" && open.length === 0 && <p className="empty">{t("advisor.empty")}</p>}
            <ul className="queue-list">
              {open.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`queue-item${item.id === selected?.id ? " queue-item-selected" : ""}`}
                    aria-pressed={item.id === selected?.id}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <span className="queue-item-head">
                      <strong>{pick(item.title, i18n.language)}</strong>
                      <Badge value="unclear" />
                    </span>
                    <span className="cell-hint">
                      {item.vendor} · {item.testCaseId}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          {decided.length > 0 && (
            <section className="panel">
              <h2 className="card-title">{t("advisor.decidedToday")}</h2>
              <ul className="decided-list">
                {decided.map((p) => (
                  <li key={p.id}>
                    {p.id !== p.signature && <span className="mono">{p.id} </span>}
                    {pick(p.itemTitle, i18n.language)} <Badge value={p.label} />
                    <div className="cell-hint">
                      {t("advisor.signature")}: <span className="mono">{p.signature}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {selected && <DeviationDetail key={selected.id} item={selected} onDecide={onDecide} />}
      </div>
    </>
  );
}

function DeviationDetail({
  item,
  onDecide,
}: {
  item: AdvisorItem;
  onDecide: (item: AdvisorItem, label: Precedent["label"], reason: string) => Promise<void>;
}) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const [reason, setReason] = useState("");
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  // Doc 05: a proposal without a cited passage is rejected and never shown.
  const proposal = item.proposal && item.proposal.citations.length > 0 ? item.proposal : undefined;
  const missingReason = tried && reason.trim() === "";

  async function submit(label: Precedent["label"]) {
    setTried(true);
    if (reason.trim() === "") return;
    setBusy(true);
    try {
      await onDecide(item, label, reason.trim());
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel advisor-detail">
      <p className="eyebrow">{t("advisor.deviation")}</p>
      <h2>{pick(item.title, lang)}</h2>
      <p className="cell-hint">
        {item.vendor} · {item.testCaseId} · V{item.ruleSet} · {item.record}
        {item.field !== "*" && ` · ${item.field}`}
      </p>

      <div className="compare-tiles">
        <div className="fact-tile">
          <span className="cell-hint">{t("result.col.expected")}</span>
          <strong>{pick(item.expected, lang)}</strong>
        </div>
        <div className="fact-tile">
          <span className="cell-hint">{t("result.col.actual")}</span>
          <strong>{pick(item.actual, lang)}</strong>
        </div>
      </div>

      {proposal ? (
        <section className="sub-card ai-card">
          <div className="sub-card-head">
            <h3>
              {t("advisor.aiProposal")}: {t(`advisor.proposal.${proposal.label}`)}
            </h3>
            <span className="muted tabular">
              {t("advisor.confidence")} {proposal.confidence.toFixed(2)}
            </span>
          </div>
          <p>{pick(proposal.reasoning, lang)}</p>
          <p className="cell-hint">
            {t("advisor.cited")}:{" "}
            {proposal.citations.map((c, i) => (
              <span key={i}>
                {i > 0 && "; "}
                <SpecRefText spec={c} />
              </span>
            ))}
            {" · "}
            {t("advisor.similar")}: {proposal.precedents.length ? proposal.precedents.join(", ") : t("advisor.none")}
          </p>
          <p className="cell-hint">{t("advisor.draftOnly")}</p>
        </section>
      ) : (
        <p className="hint-box">{t("advisor.noProposal")}</p>
      )}

      <div className="decision">
        <label className="field-label" htmlFor={`reason-${item.id}`}>
          {t("advisor.reason")}
        </label>
        <textarea
          id={`reason-${item.id}`}
          className={`reason${missingReason ? " reason-missing" : ""}`}
          rows={3}
          value={reason}
          placeholder={t("advisor.reasonPlaceholder")}
          aria-invalid={missingReason}
          onChange={(e) => setReason(e.target.value)}
        />
        {missingReason && <p className="field-error">{t("advisor.reasonRequired")}</p>}
        <div className="decision-bar">
          {DECISIONS.map((label) => {
            const suggested = proposal?.label === label;
            return (
              <button
                key={label}
                type="button"
                className={`button${suggested ? " button-primary" : ""}`}
                disabled={busy}
                onClick={() => submit(label)}
              >
                {t(suggested ? "advisor.confirmAs" : "advisor.markAs", { label: t(`status.${label}`) })}
              </button>
            );
          })}
        </div>
        <p className="cell-hint">{t("advisor.becomesPrecedent")}</p>
      </div>
    </section>
  );
}
