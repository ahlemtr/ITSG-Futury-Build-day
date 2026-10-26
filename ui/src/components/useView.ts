import { useLocation } from "react-router-dom";

export type View = "itsg" | "vendor";

/** The vendor view lives under /vendor, everything else is the ITSG view. */
export function useView(): View {
  const { pathname } = useLocation();
  return pathname === "/vendor" || pathname.startsWith("/vendor/") ? "vendor" : "itsg";
}

/** Path prefix for pages both views share (submission results, reports). */
export function viewBase(view: View): string {
  return view === "vendor" ? "/vendor" : "";
}
