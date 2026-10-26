import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { getNavCounts, type NavCounts } from "../data/dataSource";
import { Term } from "./Term";

const ITEMS = [
  { to: "/", key: "overview" },
  { to: "/spec-changes", key: "specChanges" },
  { to: "/test-catalogue", key: "testCatalogue" },
  { to: "/submissions", key: "submissions" },
  { to: "/advisor-queue", key: "advisorQueue" },
  { to: "/reports", key: "reports" },
] as const;

export function SideNav() {
  const { t } = useTranslation();
  const [counts, setCounts] = useState<NavCounts | null>(null);

  useEffect(() => {
    getNavCounts().then(setCounts).catch(() => setCounts(null));
  }, []);

  return (
    <nav className="nav" aria-label={t("nav.label")}>
      <div className="nav-section">
        <Term id="systemuntersuchung" />
      </div>
      <ul>
        {ITEMS.map((item) => {
          const count = counts && item.key in counts ? counts[item.key as keyof NavCounts] : 0;
          return (
            <li key={item.key}>
              <NavLink to={item.to} end={item.to === "/"}>
                <span>{t(`nav.${item.key}`)}</span>
                {count > 0 && (
                  <span className="nav-count" aria-label={t("nav.openItems", { count })}>
                    {count}
                  </span>
                )}
              </NavLink>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
