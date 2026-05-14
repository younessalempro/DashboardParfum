import type { Listing } from "@/lib/types";
import { formatPrice, SITE_LABELS, SITE_COLORS } from "@/lib/utils";
import { timeAgo } from "@/lib/utils";

export default function PriceComparisonTable({ listings }: { listings: Listing[] }) {
  const sorted = [...listings].sort((a, b) => a.latest_price - b.latest_price);
  const cheapest = sorted[0]?.id;

  return (
    <div className="overflow-x-auto rounded-2xl border border-gray-100 shadow-sm">
      <table className="min-w-full divide-y divide-gray-100 bg-white">
        <thead className="bg-gray-50">
          <tr>
            {["Site", "Prix", "Stock", "Mis à jour", ""].map((h) => (
              <th
                key={h}
                className="px-5 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {sorted.map((listing) => {
            const isCheapest = listing.id === cheapest;
            return (
              <tr
                key={listing.id}
                className={isCheapest ? "bg-green-50" : "hover:bg-gray-50 transition-colors"}
              >
                {/* Site */}
                <td className="px-5 py-4">
                  <span
                    className="inline-flex items-center gap-1.5 font-semibold text-sm"
                    style={{ color: SITE_COLORS[listing.site] }}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full inline-block flex-shrink-0"
                      style={{ backgroundColor: SITE_COLORS[listing.site] }}
                    />
                    {SITE_LABELS[listing.site]}
                  </span>
                </td>

                {/* Price */}
                <td className="px-5 py-4">
                  <span className={`text-base font-bold ${isCheapest ? "text-green-700" : "text-gray-900"}`}>
                    {formatPrice(listing.latest_price)}
                  </span>
                  {isCheapest && (
                    <span className="ml-2 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-medium">
                      Meilleur prix
                    </span>
                  )}
                </td>

                {/* Stock */}
                <td className="px-5 py-4">
                  {listing.in_stock ? (
                    <span className="inline-flex items-center gap-1 text-green-600 font-medium text-sm">
                      <span>✓</span> En stock
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-red-500 font-medium text-sm">
                      <span>✗</span> Rupture
                    </span>
                  )}
                </td>

                {/* Last seen */}
                <td className="px-5 py-4 text-sm text-gray-400">{timeAgo(listing.last_seen_at)}</td>

                {/* CTA */}
                <td className="px-5 py-4">
                  <a
                    href={listing.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-sm font-medium text-indigo-600 hover:text-indigo-800 transition-colors"
                  >
                    Voir →
                  </a>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
