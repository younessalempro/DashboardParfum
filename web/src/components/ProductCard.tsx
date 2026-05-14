import Image from "next/image";
import Link from "next/link";
import type { ProductListItem } from "@/lib/types";
import { formatPrice } from "@/lib/utils";
import SiteBadge from "./SiteBadge";

const GENDER_LABEL: Record<string, string> = {
  men: "Homme",
  women: "Femme",
  unisex: "Unisexe",
};

export default function ProductCard({ product }: { product: ProductListItem }) {
  return (
    <Link
      href={`/products/${product.id}`}
      className="group bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow overflow-hidden flex flex-col"
    >
      {/* Image */}
      <div className="relative aspect-square bg-gray-50 overflow-hidden">
        {product.image_url ? (
          <Image
            src={product.image_url}
            alt={product.name}
            fill
            className="object-contain p-4 group-hover:scale-105 transition-transform duration-300"
          />
        ) : (
          <div className="flex items-center justify-center h-full text-5xl">🌸</div>
        )}
        {product.gender && (
          <span className="absolute top-2 left-2 bg-white/80 backdrop-blur text-gray-600 text-xs px-2 py-0.5 rounded-full font-medium">
            {GENDER_LABEL[product.gender] ?? product.gender}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="p-4 flex flex-col gap-2 flex-1">
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">{product.brand}</p>
        <h3 className="font-semibold text-gray-900 text-sm leading-snug line-clamp-2">
          {product.name}
          {product.size_ml && (
            <span className="text-gray-400 font-normal"> · {product.size_ml} ml</span>
          )}
        </h3>
        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-lg font-bold text-gray-900">
            {formatPrice(product.cheapest_price)}
          </span>
          <SiteBadge site={product.cheapest_site} />
        </div>
      </div>
    </Link>
  );
}
