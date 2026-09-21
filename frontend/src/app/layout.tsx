import "./intake.css";
import type { Metadata } from "next";
import "./globals.css";
import "./accessibility.css";
import "./manual-lead.css";
import "./admin-follow-up.css";
import "./sales-theme.css";
import "./call-outcome.css";
import "./responsive.css";
import "./complaint.css";
import "./ceo.css";
import "./feedback.css";
import "./service.css";
import "./uploader.css";

export const metadata: Metadata = {
  title: "Incheon Mobility ITS",
  description: "Internal Tracking System for Incheon Mobility LLP",
  applicationName: "Incheon Mobility ITS",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en-IN"><body>{children}</body></html>;
}
