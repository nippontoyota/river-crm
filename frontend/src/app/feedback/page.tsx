"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { FeedbackDesk } from "@/features/feedback/feedback-desk";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";

export default function FeedbackPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    void getCurrentUser().then(({ user }) => {
      if (["FEEDBACK", "ADMIN", "SALES_MANAGER"].includes(user.role)) setUser(user);
      else router.replace(user.role === "CEO" ? "/ceo/feedback" : "/my-leads");
    }).catch(() => router.replace("/"));
  }, [router]);
  if (!user) return null;
  return <AppShell role={user.role === "ADMIN" ? "Admin" : user.role === "SALES_MANAGER" ? "Sales manager" : "Feedback Caller"}><Suspense fallback={<p className="page">Loading feedback…</p>}><FeedbackDesk currentUser={user} /></Suspense></AppShell>;
}
