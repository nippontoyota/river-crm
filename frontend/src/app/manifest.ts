import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Incheon Mobility ITS",
    short_name: "Incheon ITS",
    description: "Lead and customer tracking for Incheon Mobility",
    start_url: "/my-leads",
    display: "standalone",
    background_color: "#f5f7f6",
    theme_color: "#17211f",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
