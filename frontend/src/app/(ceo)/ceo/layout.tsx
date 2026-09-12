import { AppShell } from "@/components/app-shell";
export default function CEOLayout({ children }: { children: React.ReactNode }) {
  return <AppShell role="CEO">{children}</AppShell>;
}
