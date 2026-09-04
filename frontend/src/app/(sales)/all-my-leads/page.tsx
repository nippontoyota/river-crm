import { SalesWorkspace } from "@/features/leads/sales-workspace";

export default async function AllMyLeadsPage({ searchParams }: { searchParams: Promise<{ section?: string | string[] }> }) {
  const requested = (await searchParams).section;
  const initialSection = requested === "walkin" || requested === "won" || requested === "lost" ? requested : "all";
  return <SalesWorkspace key={initialSection} allLeadsOnly initialSection={initialSection} />;
}
