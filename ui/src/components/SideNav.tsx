import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getNavCounts, type NavCounts } from "../data/dataSource";
import { useAdvisorState } from "../data/advisorStore";
import { DEMO_VENDOR } from "../data/runTexts";
import { Term } from "./Term";
import { useView } from "./useView";

type Item = { to: string; key: string; count?: keyof NavCounts; match: (path: string) => boolean };

const startsWith = (prefix: string) => (p: string) => p === prefix || p.startsWith(`${prefix}/`);

const ITSG_ITEMS: Item[] = [
  { to: "/", key: "overview", match: (p) => p === "/" },
  { to: "/spec-changes", key: "specChanges", count: "specChanges", match: startsWith("/spec-changes") },
  { to: "/test-catalogue", key: "testCatalogue", match: startsWith("/test-catalogue") },
  { to: "/submissions", key: "submissions", match: startsWith("/submissions") },
  { to: "/advisor-queue", key: "advisorQueue", count: "advisorQueue", match: startsWith("/advisor-queue") },
  { to: "/reports", key: "reports", match: startsWith("/reports") },
];

const VENDOR_ITEMS: Item[] = [
  { to: "/vendor", key: "myTests", match: (p) => p === "/vendor" || p.startsWith("/vendor/runs") },
  { to: "/vendor/results", key: "results", match: startsWith("/vendor/results") },
  { to: "/vendor/reports", key: "vendorReports", match: startsWith("/vendor/reports") },
];

export function SideNav() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const view = useView();
  const [counts, setCounts] = useState<NavCounts | null>(null);
  const advisor = useAdvisorState();

  useEffect(() => {
    getNavCounts().then(setCounts).catch(() => setCounts(null));
  }, []);

  const items = view === "vendor" ? VENDOR_ITEMS : ITSG_ITEMS;

  return (
    <nav className="nav" aria-label={t("nav.label")}>
      <div className="nav-section">
        {view === "vendor" ? (
          <>
            {t("nav.vendorPortal")}
            <div className="nav-vendor">{DEMO_VENDOR}</div>
          </>
        ) : (
          <Term id="systemuntersuchung" />
        )}
      </div>
      <ul>
        {items.map((item) => {
          const count = item.count === "advisorQueue" ? advisor.open.length : item.count && counts ? counts[item.count] : 0;
          const active = item.match(pathname);
          return (
            <li key={item.key}>
              <Link to={item.to} className={active ? "active" : undefined} aria-current={active ? "page" : undefined}>
                <span>{t(`nav.${item.key}`)}</span>
                {count > 0 && (
                  <span className="nav-count" aria-label={t("nav.openItems", { count })}>
                    {count}
                  </span>
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
