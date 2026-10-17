import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/api";

/**
 * Static route map. The legal pages are included on purpose: a compliance page
 * that a crawler never sees cannot do its job.
 */
const ROUTES: { path: string; priority: number }[] = [
  { path: "", priority: 1 },
  { path: "/research", priority: 0.9 },
  { path: "/schemes", priority: 0.8 },
  { path: "/dpr", priority: 0.7 },
  { path: "/advisor", priority: 0.7 },
  { path: "/about", priority: 0.5 },
  { path: "/privacy", priority: 0.5 },
  { path: "/terms", priority: 0.5 },
  { path: "/disclaimer", priority: 0.5 },
  { path: "/history", priority: 0.3 },
];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return ROUTES.map(({ path, priority }) => ({
    url: `${SITE_URL}${path}`,
    lastModified,
    changeFrequency: "weekly",
    priority,
  }));
}
