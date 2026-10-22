"use client";

import { useEffect, useRef } from "react";

// Same-browser changes refresh immediately; other sessions are checked every
// 30 seconds while visible. Keep open editors and unsaved form state intact.
export function useCrmRefresh(refresh: () => unknown, enabled = true) {
  const latest = useRef(refresh);
  useEffect(() => { latest.current = refresh; }, [refresh]);
  useEffect(() => {
    if (!enabled) return;
    let busy = false;
    let pendingChange = false;
    let active = true;
    const run = (changed = false) => {
      if (!active || document.visibilityState !== "visible") return;
      if (busy) { pendingChange ||= changed; return; }
      busy = true;
      pendingChange = false;
      void Promise.resolve().then(() => { if (active) return latest.current(); }).catch(() => {}).finally(() => {
        busy = false;
        if (pendingChange) run();
      });
    };
    const refreshVisible = () => run();
    const refreshChanged = () => run(true);
    const changed = (event: StorageEvent) => { if (event.key === "crm-data-changed") refreshChanged(); };
    const timer = window.setInterval(refreshVisible, 30_000);
    window.addEventListener("crm-data-changed", refreshChanged);
    window.addEventListener("storage", changed);
    window.addEventListener("focus", refreshVisible);
    document.addEventListener("visibilitychange", refreshVisible);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener("crm-data-changed", refreshChanged);
      window.removeEventListener("storage", changed);
      window.removeEventListener("focus", refreshVisible);
      document.removeEventListener("visibilitychange", refreshVisible);
    };
  }, [enabled]);
}
