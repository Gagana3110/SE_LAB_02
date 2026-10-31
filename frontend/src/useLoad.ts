import { useCallback, useEffect, useState } from "react";
import { messageOf } from "./api";

/** Loads data when a page opens. Call reload() after a change to show the latest values. */
export function useLoad<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    return load()
      .then((value) => {
        setData(value);
        setError("");
      })
      .catch((reason) => setError(messageOf(reason)));
  }, [load]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, reload };
}
