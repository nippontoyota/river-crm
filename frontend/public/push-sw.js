self.addEventListener("push", event => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { body: event.data ? event.data.text() : "A new lead was assigned to you." };
  }
  event.waitUntil(self.registration.showNotification(payload.title || "New lead assigned", {
    body: payload.body || "A new lead was assigned to you.",
    icon: "/icon.svg",
    badge: "/icon.svg",
    tag: payload.tag || "lead-assignment",
    renotify: true,
    data: { url: payload.url || "/my-leads" },
  }));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/my-leads", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(clients => {
    const existing = clients.find(client => new URL(client.url).origin === self.location.origin);
    if (existing) return existing.navigate(target).then(client => client.focus());
    return self.clients.openWindow(target);
  }));
});
