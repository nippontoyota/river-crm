"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ComplaintDesk } from "@/features/complaints/complaint-desk";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";

export default function ComplaintsPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    void getCurrentUser().then(result => {
      const actual = result.user;
      if (actual.role === "ADMIN" || actual.role === "CRE" || actual.role === "COMPLAINTS") {
        setUser(actual);
        return;
      }
      router.replace(actual.role === "RECEPTIONIST" ? "/capture" : "/my-leads");
    }).catch(() => router.replace("/"));
  }, [router]);

  if (!user) return null;

  return (
    <AppShell role={user.role === "ADMIN" ? "Admin" : "Sales officer"}>
      <ComplaintDesk adminView={user.role === "ADMIN"} currentUser={user} />
    </AppShell>
  );
}
