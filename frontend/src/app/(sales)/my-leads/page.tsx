import { SalesWorkspace } from "@/features/leads/sales-workspace";

export default async function MyLeadsPage({ searchParams }: { searchParams: Promise<{ lead?: string | string[] }> }) {
  const requested = (await searchParams).lead;
  const initialLeadId = typeof requested === "string" && /^\d+$/.test(requested) ? Number(requested) : undefined;
  return <SalesWorkspace initialLeadId={initialLeadId} />;
}
