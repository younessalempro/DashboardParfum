import type { Site } from "@/lib/types";
import { SITE_COLORS, SITE_LABELS } from "@/lib/utils";

export default function SiteBadge({ site }: { site: Site }) {
  const color = SITE_COLORS[site];
  const label = SITE_LABELS[site];
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold text-white"
      style={{ backgroundColor: color }}
    >
      {label}
    </span>
  );
}
