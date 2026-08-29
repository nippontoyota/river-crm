import { AppShell } from "@/components/app-shell";

export default function ManagerLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell role="Sales manager">{children}</AppShell>;
}
