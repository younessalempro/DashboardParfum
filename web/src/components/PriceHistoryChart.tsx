"use client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { PriceHistoryEntry, Site } from "@/lib/types";
import { SITE_COLORS, SITE_LABELS, formatPrice } from "@/lib/utils";

interface Props {
  history: PriceHistoryEntry[];
}

export default function PriceHistoryChart({ history }: Props) {
  if (history.length === 0) {
    return <p className="text-gray-400 text-sm">Aucun historique disponible.</p>;
  }

  // Collect all dates and build pivot data
  const dateMap: Record<string, Record<Site, number | undefined>> = {};
  for (const entry of history) {
    const d = entry.scraped_at.slice(0, 10);
    if (!dateMap[d]) dateMap[d] = {} as Record<Site, number | undefined>;
    dateMap[d][entry.site as Site] = entry.price;
  }

  const data = Object.entries(dateMap)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, prices]) => ({
      date,
      primor: prices.primor,
      sephora: prices.sephora,
      nocibe: prices.nocibe,
    }));

  const sites: Site[] = ["primor", "sephora", "nocibe"];

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#9ca3af" }} />
        <YAxis
          tick={{ fontSize: 11, fill: "#9ca3af" }}
          tickFormatter={(v) => `${v} €`}
          domain={["auto", "auto"]}
        />
        <Tooltip
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(value: any, name: any) => [typeof value === "number" ? formatPrice(value) : String(value), SITE_LABELS[name as Site] || String(name)]}
          labelStyle={{ color: "#374151", fontWeight: 600 }}
        />
        <Legend
          formatter={(value) => SITE_LABELS[value as Site] || value}
        />
        {sites.map((site) => (
          <Line
            key={site}
            type="monotone"
            dataKey={site}
            stroke={SITE_COLORS[site]}
            strokeWidth={2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
