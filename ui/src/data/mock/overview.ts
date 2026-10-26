// Demo figures for the Overview. Kept consistent with the other mock data:
// 3 waiting deviations = advisor queue badge, 2 hidden variants = peter-hidden + peter-gap-exact-hidden,
// 2 tests to re-approve = peter-gap-exact + its hidden variant (02, M5.3).
import type { OverviewData } from "../types";

export const OVERVIEW: OverviewData = {
  checksNow: {
    ruleSet: "13.3",
    validUntil: "2026-12-31",
    month: "2026-10",
    submissions: 12,
    passedAllRules: 9,
    withOpenDeviations: 3,
  },
  nextYear: {
    ruleSet: "13.4",
    validFrom: "2027-01-01",
    specChangesInScope: 5,
    testsToReapprove: 2,
    hiddenVariantsReady: 2,
  },
  resolution: {
    catalogueAndRules: 15,
    aiConfirmedByAdvisor: 6,
    waitingForAdvisor: 3,
  },
};
