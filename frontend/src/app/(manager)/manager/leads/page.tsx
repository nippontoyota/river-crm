import { ManagerLeadsPage } from "@/features/leads/manager-leads-page";

const filterKeys = ["q", "source", "status", "model", "category", "cre", "ps", "date_from", "date_to", "range", "sales_outcome", "flagged", "followup", "risk", "status_group"] as const;

export default async function ManagerLeadsRoute({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const values = await searchParams;
  const query = new URLSearchParams();
  filterKeys.forEach(key => {
    const value = values[key];
    const firstValue = Array.isArray(value) ? value[0] : value;
    if (firstValue) query.set(key, firstValue);
  });
  const initialQuery = query.toString();
  return <ManagerLeadsPage key={initialQuery} initialQuery={initialQuery} />;
}
