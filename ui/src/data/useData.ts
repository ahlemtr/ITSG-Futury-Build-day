import { useEffect, useState } from "react";

type State<T> = { status: "loading" } | { status: "error"; error: Error } | { status: "ready"; data: T };

/** Loads data from the data source and re-loads when the dependencies change. */
export function useData<T>(load: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    load()
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch((error: Error) => !cancelled && setState({ status: "error", error }));
    return () => {
      cancelled = true;
    };
  }, deps);

  return state;
}
