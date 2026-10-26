import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Lets a screen replace the text on the right of the top bar
// (e.g. "Submission #2026-10-021 · rule set V13.3"). null = default text.
type Ctx = { content: ReactNode | null; setContent: (c: ReactNode | null) => void };

const TopBarCtx = createContext<Ctx>({ content: null, setContent: () => {} });

export function TopBarProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<ReactNode | null>(null);
  return <TopBarCtx.Provider value={{ content, setContent }}>{children}</TopBarCtx.Provider>;
}

export function useTopBarContent() {
  return useContext(TopBarCtx).content;
}

/** Shows `content` in the top bar while the calling screen is open. */
export function useSetTopBar(content: ReactNode | null, deps: unknown[]) {
  const { setContent } = useContext(TopBarCtx);
  useEffect(() => {
    setContent(content);
    return () => setContent(null);
  }, deps);
}
