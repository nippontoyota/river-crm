import { SalesWorkspace } from "@/features/leads/sales-workspace";

export default async function FollowUpsPage({ searchParams }: { searchParams: Promise<{ section?: string | string[] }> }) {
  const initialSection = (await searchParams).section === "missed" ? "missed" : "followups";
  return <SalesWorkspace followUpsOnly initialSection={initialSection} />;
}
