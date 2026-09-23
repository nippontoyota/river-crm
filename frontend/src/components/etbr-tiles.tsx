import type { EtbrMetrics } from "@/lib/crm";

const tiles: [keyof EtbrMetrics, string, string, string][] = [
  ["etbr_enquired", "Enquired", "All enquiries in this period", "blue"],
  ["etbr_test_drive_completed", "Test Drive Completed", "Explicitly marked completed", "violet"],
  ["etbr_booked", "Booked", "Includes retailed bookings", "green"],
  ["etbr_retailed", "Retailed", "Completed retail sales", "mint"],
];

export function EtbrTiles({ data, embedded = false, exclude = [], actions = {}, active }: { data?: EtbrMetrics | null; embedded?: boolean; exclude?: (keyof EtbrMetrics)[]; actions?: Partial<Record<keyof EtbrMetrics, () => void>>; active?: keyof EtbrMetrics }) {
  const cards = tiles.filter(([key]) => !exclude.includes(key)).map(([key, label, description, tone]) => {
    const action = actions[key];
    const Tag = action ? "button" : "article";
    return <Tag className={`sales-metric panel${embedded ? ` ${tone}` : ""}${action && active === key ? " active" : ""}`} key={key} title={description} type={action ? "button" : undefined} onClick={action} aria-pressed={action ? active === key : undefined} style={embedded ? undefined : { padding: 20, cursor: action ? "pointer" : "default" }}>
      <span>{label}</span><strong>{data?.[key] ?? "—"}</strong>{!embedded && <small>{description}</small>}
    </Tag>;
  });
  if (embedded) return <>{cards}</>;
  return <section aria-label="ETBR: progress of enquiries in the selected period" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 190px), 1fr))", gap: 16, marginBottom: 20 }}>
    {cards}
  </section>;
}
