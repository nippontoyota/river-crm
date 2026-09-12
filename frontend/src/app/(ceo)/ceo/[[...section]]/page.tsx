import { Suspense } from "react";
import { notFound } from "next/navigation";
import { CEODashboard } from "@/features/ceo/dashboard";
export default async function CEOPage({ params }: { params: Promise<{ section?: string[] }> }) {
  const { section } = await params;
  const selected = section?.[0] || "overview";
  if ((section?.length || 0) > 1 || !["overview", "branches", "people", "leads", "markets", "operations"].includes(selected)) notFound();
  return <Suspense fallback={<div className="ceo-page">Loading report…</div>}><CEODashboard section={selected} /></Suspense>;
}
