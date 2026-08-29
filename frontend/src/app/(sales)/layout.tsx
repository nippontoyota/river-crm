import { AppShell } from "@/components/app-shell";

export default function SalesLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AppShell role="Sales officer">{children}</AppShell>;
}
