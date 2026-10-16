"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/crm";
import { formatDateTime } from "@/lib/dates";

type LeadNotification = {
  id: number;
  lead: number | null;
  message: string;
  read_at: string | null;
  created_at: string;
};

const query = "kind=ASSIGNMENT";
type PushState = "loading" | "prompt" | "enabled" | "denied" | "unsupported" | "unconfigured" | "error";

function applicationServerKey(value: string) {
  const padding = "=".repeat((4 - value.length % 4) % 4);
  const decoded = window.atob((value + padding).replaceAll("-", "+").replaceAll("_", "/"));
  return Uint8Array.from(decoded, character => character.charCodeAt(0));
}

export async function unsubscribePhonePush() {
  if (!("serviceWorker" in navigator)) return;
  const registration = await navigator.serviceWorker.getRegistration("/");
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) return;
  await api("/api/notifications/push-unsubscribe/", { method: "POST", body: JSON.stringify({ endpoint: subscription.endpoint }) });
  await subscription.unsubscribe();
}

export function LeadNotifications() {
  const [items, setItems] = useState<LeadNotification[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");
  const [pushState, setPushState] = useState<PushState>("loading");
  const [pushKey, setPushKey] = useState("");
  const [pushBusy, setPushBusy] = useState(false);
  const isAppleMobile = typeof navigator !== "undefined" && /iPhone|iPad|iPod/.test(navigator.userAgent);
  const isStandalone = typeof window !== "undefined" && (window.matchMedia("(display-mode: standalone)").matches || Boolean((navigator as Navigator & { standalone?: boolean }).standalone));

  useEffect(() => {
    const controller = new AbortController();
    const refresh = () => {
      if (document.hidden) return;
      void Promise.all([
        api<{ results: LeadNotification[] }>(`/api/notifications/?${query}`, { signal: controller.signal }),
        api<{ count: number }>(`/api/notifications/unread_count/?${query}`, { signal: controller.signal }),
      ]).then(([page, unread]) => {
        setItems(page.results);
        setCount(unread.count);
        setError("");
      }).catch(requestError => {
        if (requestError.name !== "AbortError") setError(requestError.message);
      });
    };
    refresh();
    const timer = window.setInterval(refresh, 30_000);
    window.addEventListener("focus", refresh);
    window.addEventListener("crm-data-changed", refresh);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
      window.removeEventListener("crm-data-changed", refresh);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const inspectPush = async () => {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        if (active) setPushState("unsupported");
        return;
      }
      try {
        const config = await api<{ enabled: boolean; public_key: string }>("/api/notifications/push-config/");
        if (!active) return;
        if (!config.enabled) {
          setPushState("unconfigured");
          return;
        }
        setPushKey(config.public_key);
        const registration = await navigator.serviceWorker.register("/push-sw.js");
        const subscription = await registration.pushManager.getSubscription();
        if (!active) return;
        if (subscription) {
          await api("/api/notifications/push-subscribe/", { method: "POST", body: JSON.stringify(subscription.toJSON()) });
          setPushState("enabled");
        } else {
          setPushState(Notification.permission === "denied" ? "denied" : "prompt");
        }
      } catch {
        if (active) setPushState("error");
      }
    };
    void inspectPush();
    return () => { active = false; };
  }, []);

  const enablePush = async () => {
    setPushBusy(true);
    setError("");
    try {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setPushState("denied");
        return;
      }
      const registration = await navigator.serviceWorker.register("/push-sw.js");
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: applicationServerKey(pushKey),
      });
      await api("/api/notifications/push-subscribe/", { method: "POST", body: JSON.stringify(subscription.toJSON()) });
      setPushState("enabled");
    } catch (requestError) {
      setPushState("error");
      setError(requestError instanceof Error ? requestError.message : "Unable to enable phone alerts.");
    } finally {
      setPushBusy(false);
    }
  };

  const disablePush = async () => {
    setPushBusy(true);
    setError("");
    try {
      await unsubscribePhonePush();
      setPushState("prompt");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to disable phone alerts.");
    } finally {
      setPushBusy(false);
    }
  };

  const markRead = async (id?: number) => {
    try {
      await api(`/api/notifications/${id ? `${id}/read/` : `mark_read/?${query}`}`, { method: "POST" });
      setItems(current => current.map(item => !id || item.id === id ? { ...item, read_at: new Date().toISOString() } : item));
      setCount(current => id ? Math.max(0, current - (items.find(item => item.id === id)?.read_at ? 0 : 1)) : 0);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update notifications.");
    }
  };

  return <details className="feedback-bell lead-notifications">
    <summary aria-label={`${count} unread lead notification${count === 1 ? "" : "s"}`}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></svg>
      <span>{count}</span>
    </summary>
    <div className="feedback-notifications">
      <header><b>New lead notifications</b><button className="filter" disabled={!count} onClick={() => void markRead()}>Mark all read</button></header>
      <section className={`phone-alerts ${pushState === "enabled" ? "enabled" : ""}`} aria-live="polite">
        <div><b>{pushState === "enabled" ? "Phone alerts are on" : "Phone notification panel"}</b>
          <small>{pushState === "enabled" ? "New lead assignments can appear even when the CRM is closed." :
            pushState === "denied" ? "Notifications are blocked. Allow them in your phone browser settings, then reload." :
            pushState === "unsupported" ? "This browser does not support phone push notifications." :
            pushState === "unconfigured" ? "Phone alerts need to be activated by your administrator." :
            isAppleMobile && !isStandalone ? "On iPhone, add this CRM to the Home Screen and open it there first." :
            pushState === "error" ? "Phone alerts could not be checked. Try again." : "Enable system notifications for every new lead assignment."}</small>
        </div>
        {pushState === "enabled" ? <button className="filter" disabled={pushBusy} onClick={() => void disablePush()}>Turn off</button> :
          ["prompt", "error"].includes(pushState) && !(isAppleMobile && !isStandalone) ? <button className="button primary" disabled={pushBusy || !pushKey} onClick={() => void enablePush()}>{pushBusy ? "Enabling…" : "Enable"}</button> : null}
      </section>
      {error && <p role="alert">{error}</p>}
      {items.length ? items.map(item => <Link className={item.read_at ? "read" : "unread"} key={item.id} href={item.lead ? `/my-leads?lead=${item.lead}` : "/my-leads"} onClick={event => {
        void markRead(item.id);
        event.currentTarget.closest("details")?.removeAttribute("open");
      }}><b>{item.message}</b><small>{formatDateTime(item.created_at)}</small></Link>) : <p>No lead notifications yet. New assignments will appear here.</p>}
    </div>
  </details>;
}
