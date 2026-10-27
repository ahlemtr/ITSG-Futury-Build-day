import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getResetStatus, resetAll } from "../data/api";

const RUNS_KEY = "eel-ui-runs-api"; // runStore: the vendor's runs, gone after a reset

/** The avatar in the top bar: a menu with the demo reset (ITSG view). */
export function UserMenu({ initials, title }: { initials: string; title: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (!open) return;
    getResetStatus()
      .then((s) => setAllowed(s.allowed))
      .catch(() => setAllowed(false));
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const ask = () => {
    setOpen(false);
    setError(null);
    dialog.current?.showModal();
  };

  const confirm = async () => {
    setBusy(true);
    setError(null);
    dialog.current?.close(); // the AI overlay shows the stages; a modal dialog would cover it
    try {
      const job = await resetAll();
      if (job.status === "failed") throw new Error(job.error ?? "failed");
      try {
        localStorage.removeItem(RUNS_KEY);
      } catch {
        // storage blocked: the run store starts fresh on a 404 anyway
      }
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      dialog.current?.showModal();
    }
  };

  return (
    <div className="user-menu" ref={root}>
      <button
        type="button"
        className="avatar"
        title={title}
        aria-label={t("admin.menu")}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {initials}
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="menu-head">{title}</div>
          <button type="button" role="menuitem" className="menu-item menu-danger" disabled={allowed === false} onClick={ask}>
            {t("admin.reset.action")}
          </button>
          {allowed === false && <p className="menu-note">{t("admin.reset.notAllowed")}</p>}
        </div>
      )}
      <dialog ref={dialog} className="confirm-dialog" aria-labelledby="reset-title" onCancel={(e) => busy && e.preventDefault()}>
        <h2 id="reset-title">{t("admin.reset.title")}</h2>
        <p>{t("admin.reset.body")}</p>
        {error && <p className="dialog-error">{t("admin.reset.failed", { error })}</p>}
        <div className="dialog-actions">
          <button type="button" className="button" disabled={busy} onClick={() => dialog.current?.close()}>
            {t("admin.reset.cancel")}
          </button>
          <button type="button" className="button button-danger" disabled={busy} onClick={confirm}>
            {t("admin.reset.confirm")}
          </button>
        </div>
      </dialog>
    </div>
  );
}
