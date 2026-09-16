"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { ServiceDesk } from "@/features/servicing/service-desk";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";

export default function ServicesPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => { getCurrentUser().then(({ user: actual }) => {
    if (actual.role === "SO") router.replace("/my-leads");
    else if (["SERVICE", "CRE", "ADMIN", "CEO"].includes(actual.role)) setUser(actual);
    else router.replace("/");
  }).catch(() => router.replace("/")); }, [router]);
  if (!user) return null;
  return <AppShell role={user.role === "SERVICE" ? "Service Department" : user.role === "CEO" ? "CEO" : user.role === "ADMIN" ? "Admin" : "Sales officer"}><ServiceDesk user={user} /></AppShell>;
}
