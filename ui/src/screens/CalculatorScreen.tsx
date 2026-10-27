import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { postJson, toSpecRef } from "../data/api";
import { InfoTip } from "../components/InfoTip";
import { SpecRefText } from "../components/SpecRefText";

type Step = { key: string; value: string; formula: string; section: string; passage: string | null; confirmed: boolean };
type CalcResult = {
  bemessungszeitraum: [string, string];
  zwoelf_monate: [string, string];
  regelentgelt: string;
  krankengeld: string;
  steps: Step[];
};

type Form = {
  au_start: string;
  pay: "monthly" | "hourly";
  billing_day: string;
  billing_month: "same" | "next";
  gross: string;
  net: string;
  one_off: string;
  weekly_hours: string;
  paid_hours: string;
};

// Beispiel 103 of RS Anlage 3: the calculator opens with a worked example of the Rundschreiben
const EXAMPLE: Form = {
  au_start: "2026-05-16",
  pay: "monthly",
  billing_day: "31",
  billing_month: "same",
  gross: "2250",
  net: "1650",
  one_off: "4500",
  weekly_hours: "",
  paid_hours: "",
};

/** "1.234,5" or "1234.5" -> "1234.5" */
const num = (s: string) => (s.includes(",") ? s.replace(/\./g, "").replace(",", ".") : s).trim();

const eur = (v: string, lang: string) =>
  Number(v).toLocaleString(lang === "en" ? "en-GB" : "de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const MONEY = new Set([
  "regelentgelt_laufend", "netto_laufend", "hinzurechnung_brutto", "regelentgelt_kumuliert", "hoechstregelentgelt",
  "regelentgelt_massgeblich", "hinzurechnung_netto", "netto_kumuliert", "kg_70_regelentgelt", "kg_90_netto",
  "kg_100_netto_laufend", "krankengeld",
]);

/** The advisors' calculator: Krankengeld from Arbeitsentgelt as RS Anlage 3 computes it, every step with its source. */
export function CalculatorScreen() {
  const { t, i18n } = useTranslation();
  const [form, setForm] = useState<Form>(EXAMPLE);
  const [fileValue, setFileValue] = useState("");
  const [result, setResult] = useState<CalcResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof Form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        au_start: form.au_start,
        pay: form.pay,
        billing_day: Number(form.billing_day) || 31,
        billing_month: form.billing_month,
        gross: num(form.gross),
        net: num(form.net),
        one_off: num(form.one_off) || "0",
        ...(form.pay === "hourly" ? { weekly_hours: num(form.weekly_hours), paid_hours: num(form.paid_hours) } : {}),
      };
      setResult(await postJson<CalcResult>("/calc/krankengeld", body));
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const lang = i18n.language;
  const compared = result && fileValue.trim() ? Number(num(fileValue)) : null;
  const matches = compared !== null && result ? Math.abs(compared - Number(result.krankengeld)) < 0.005 : null;

  return (
    <>
      <div className="page-header">
        <h1>
          {t("calc.title")}
          <InfoTip>{t("calc.info")}</InfoTip>
        </h1>
      </div>

      <div className="calc-layout">
        <form className="panel calc-form" onSubmit={submit}>
          <h2 className="card-title">{t("calc.inputs")}</h2>
          <label>
            <span className="field-label">{t("calc.f.au_start")}</span>
            <input type="date" value={form.au_start} onChange={set("au_start")} required />
          </label>
          <label>
            <span className="field-label">{t("calc.f.pay")}</span>
            <select value={form.pay} onChange={set("pay")}>
              <option value="monthly">{t("calc.pay.monthly")}</option>
              <option value="hourly">{t("calc.pay.hourly")}</option>
            </select>
          </label>
          <div className="calc-pair">
            <label>
              <span className="field-label">{t("calc.f.billing_day")}</span>
              <input inputMode="numeric" value={form.billing_day} onChange={set("billing_day")} />
            </label>
            <label>
              <span className="field-label">{t("calc.f.billing_month")}</span>
              <select value={form.billing_month} onChange={set("billing_month")}>
                <option value="same">{t("calc.billing.same")}</option>
                <option value="next">{t("calc.billing.next")}</option>
              </select>
            </label>
          </div>
          <label>
            <span className="field-label">{t("calc.f.gross")}</span>
            <input inputMode="decimal" value={form.gross} onChange={set("gross")} required />
          </label>
          <label>
            <span className="field-label">{t("calc.f.net")}</span>
            <input inputMode="decimal" value={form.net} onChange={set("net")} required />
          </label>
          <label>
            <span className="field-label">{t("calc.f.one_off")}</span>
            <input inputMode="decimal" value={form.one_off} onChange={set("one_off")} />
          </label>
          {form.pay === "hourly" && (
            <div className="calc-pair">
              <label>
                <span className="field-label">{t("calc.f.weekly_hours")}</span>
                <input inputMode="decimal" value={form.weekly_hours} onChange={set("weekly_hours")} required />
              </label>
              <label>
                <span className="field-label">{t("calc.f.paid_hours")}</span>
                <input inputMode="decimal" value={form.paid_hours} onChange={set("paid_hours")} required />
              </label>
            </div>
          )}
          <label>
            <span className="field-label">{t("calc.f.fileValue")}</span>
            <input inputMode="decimal" value={fileValue} placeholder={t("calc.optional")} onChange={(e) => setFileValue(e.target.value)} />
          </label>
          <div className="calc-actions">
            <button type="submit" className="button button-primary" disabled={busy}>
              {t("calc.calculate")}
            </button>
            <button type="button" className="link-button" onClick={() => setForm(EXAMPLE)}>
              {t("calc.example")}
            </button>
          </div>
          {error && (
            <p className="field-error" role="alert">
              {error}
            </p>
          )}
        </form>

        <section className="panel panel-flush calc-result" aria-live="polite">
          {!result && <p className="empty">{t("calc.empty")}</p>}
          {result && (
            <>
              <div className="calc-headline">
                <div>
                  <span className="cell-hint">{t("calc.krankengeld")}</span>
                  <strong className="calc-amount tabular">{eur(result.krankengeld, lang)} €</strong>
                  <span className="cell-hint">{t("calc.perDay")}</span>
                </div>
                <div>
                  <span className="cell-hint">{t("calc.bz")}</span>
                  <strong className="tabular">{result.steps[0].value}</strong>
                </div>
                {matches !== null && (
                  <span className={`badge ${matches ? "badge-exact" : "badge-bug"}`}>
                    {t(matches ? "calc.match" : "calc.mismatch", { value: eur(String(compared), lang) })}
                  </span>
                )}
              </div>
              <table className="list-table">
                <thead>
                  <tr>
                    <th>{t("calc.col.step")}</th>
                    <th className="num">{t("calc.col.value")}</th>
                    <th>{t("calc.col.how")}</th>
                    <th>{t("calc.col.source")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.steps.map((s) => (
                    <tr key={s.key} className={s.key === "krankengeld" ? "calc-final" : undefined}>
                      <td>{t(`calc.step.${s.key}`, { defaultValue: s.key })}</td>
                      <td className="num tabular">{MONEY.has(s.key) ? `${eur(s.value, lang)} €` : s.value}</td>
                      <td className="cell-hint tabular">{t(`calc.how.${s.key}`, { defaultValue: s.formula.replace(/(\d)\.(\d)/g, lang === "en" ? "$1.$2" : "$1,$2") })}</td>
                      <td>
                        {s.passage ? (
                          <span title={s.passage}>
                            <SpecRefText spec={{ ...toSpecRef(s.passage), section: s.section }} />
                          </span>
                        ) : (
                          s.section
                        )}
                        {!s.confirmed && (
                          <span className="badge calc-unconfirmed" title={t("calc.unconfirmedHint")}>
                            {t("calc.unconfirmed")}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="cell-hint calc-scope">{t("calc.scope")}</p>
            </>
          )}
        </section>
      </div>
    </>
  );
}
