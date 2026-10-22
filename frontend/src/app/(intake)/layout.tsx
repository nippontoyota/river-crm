"use client";

import { AppShell } from "@/components/app-shell";
import { useEffect, useState } from "react";
import { getCurrentUser, type CurrentUser } from "@/lib/crm";

export default function IntakeLayout({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser>();
  const [role, setRole] = useState<any>(null);

  useEffect(() => {
    getCurrentUser().then(({ user }) => {
      setUser(user);
      setRole(user.role === "RECEPTIONIST" ? "Receptionist" : "Sales officer");
    }).catch(() => {
      // Fallback
      setRole("Receptionist");
    });
  }, []);

  if (!role) return null;

  return <AppShell initialUser={user} role={role}>{children}</AppShell>;
}
