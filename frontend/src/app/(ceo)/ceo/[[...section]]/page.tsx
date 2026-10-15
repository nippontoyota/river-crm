import { Suspense } from "react";
import { notFound } from "next/navigation";
import { FeedbackDesk } from "@/features/feedback/feedback-desk";
import { CEODashboard } from "@/features/ceo/dashboard";
import { CEAnalyticsPage } from "@/features/analytics/ce-analytics-page";
export default async function CEOPage({ params }: { params: Promise<{ section?: string[] }> }) {
  const { section } = await params;
  const selected = section?.[0] || "overview";
  if ((section?.length || 0) > 1 || !["ce-analytics", "feedback", "overview", "branches", "people", "leads", "markets", "operations"].includes(selected)) notFound();
  return <Suspense fallback={<div className="ceo-page">Loading report…</div>}>{selected === "ce-analytics" ? <CEAnalyticsPage /> : selected === "feedback" ? <FeedbackDesk /> : <CEODashboard section={selected} />}</Suspense>;
}
