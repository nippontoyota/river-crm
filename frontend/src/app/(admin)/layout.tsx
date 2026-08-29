import { AppShell } from "@/components/app-shell";

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell role="Admin">{children}</AppShell>;
}
