"use client";

import { AppShell } from "@/components/app-shell";
import { useEffect, useState } from "react";
import { getCurrentUser } from "@/lib/crm";

export default function IntakeLayout({ children }: { children: React.ReactNode }) {
  const [role, setRole] = useState<any>(null);

  useEffect(() => {
    getCurrentUser().then(({ user }) => {
      setRole(user.role === "RECEPTIONIST" ? "Receptionist" : "Sales officer");
    }).catch(() => {
      // Fallback
      setRole("Receptionist");
    });
  }, []);

  if (!role) return null;

  return <AppShell role={role}>{children}</AppShell>;
}
