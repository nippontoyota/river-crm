import type { EtbrMetrics } from "@/lib/crm";

const tiles: [keyof EtbrMetrics, string, string][] = [
  ["etbr_enquired", "Enquired", "All enquiries in this period"],
  ["etbr_test_drive_completed", "Test Drive Completed", "Explicitly marked completed"],
  ["etbr_booked", "Booked", "Includes retailed bookings"],
  ["etbr_retailed", "Retailed", "Completed retail sales"],
];

export function EtbrTiles({ data }: { data?: EtbrMetrics | null }) {
  return <section aria-label="ETBR: progress of enquiries in the selected period" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 190px), 1fr))", gap: 16, marginBottom: 20 }}>
    {tiles.map(([key, label, description]) => <article className="sales-metric panel" key={key} style={{ padding: 20, cursor: "default" }}>
      <span>{label}</span><strong>{data?.[key] ?? "—"}</strong><small>{description}</small>
    </article>)}
  </section>;
}
