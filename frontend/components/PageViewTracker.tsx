"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { track } from "@/lib/analytics";

/**
 * Fires one `page_view` per route change. Mounted once in the root layout, so
 * every page is counted without wiring anything into individual routes.
 */
export default function PageViewTracker() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname) return;
    track("page_view", { page: pathname });
  }, [pathname]);

  return null;
}
