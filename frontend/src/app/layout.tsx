import type { Metadata } from "next";
import "./globals.css";
import "./accessibility.css";
import "./manual-lead.css";
import "./admin-follow-up.css";
import "./sales-theme.css";
import "./call-outcome.css";
import "./responsive.css";
import "./complaint.css";

export const metadata: Metadata = {
  title: "River Lead Control",
  description: "Operations CRM for River Scooter",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en-IN"><body>{children}</body></html>;
}
