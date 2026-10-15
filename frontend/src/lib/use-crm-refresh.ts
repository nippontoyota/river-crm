"use client";

import { useEffect, useRef } from "react";

// Same-browser changes refresh immediately; other sessions are checked every
// 3 seconds while visible. Keep open editors and unsaved form state intact.
export function useCrmRefresh(refresh: () => unknown, enabled = true) {
  const latest = useRef(refresh);
  useEffect(() => { latest.current = refresh; }, [refresh]);
  useEffect(() => {
    if (!enabled) return;
    let busy = false;
    const run = () => {
      if (busy || document.visibilityState !== "visible") return;
      busy = true;
      void Promise.resolve().then(() => latest.current()).catch(() => {}).finally(() => { busy = false; });
    };
    const changed = (event: StorageEvent) => { if (event.key === "crm-data-changed") run(); };
    const timer = window.setInterval(run, 3_000);
    window.addEventListener("crm-data-changed", run);
    window.addEventListener("storage", changed);
    window.addEventListener("focus", run);
    document.addEventListener("visibilitychange", run);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("crm-data-changed", run);
      window.removeEventListener("storage", changed);
      window.removeEventListener("focus", run);
      document.removeEventListener("visibilitychange", run);
    };
  }, [enabled]);
}
