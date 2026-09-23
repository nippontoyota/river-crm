"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app-shell";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";
import { CallCenterWorkspace } from "@/features/leads/call-center-workspace";

export default function CallCenterPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const router = useRouter();
  useEffect(() => {
    getCurrentUser().then(({ user }) => {
      if (["CRE", "ADMIN"].includes(user.role)) setUser(user);
      else router.replace("/my-leads");
    }).catch(() => router.replace("/"));
  }, [router]);
  if (!user) return null;
  return <AppShell role={user.role === "ADMIN" ? "Admin" : "Sales officer"}><CallCenterWorkspace user={user} /></AppShell>;
}
