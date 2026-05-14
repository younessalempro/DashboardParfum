import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { getProduct, getProductHistory, isApiError } from "@/lib/api";
import { MOCK_PRODUCT_DETAIL, MOCK_HISTORY } from "@/lib/mockData";
import PriceComparisonTable from "@/components/PriceComparisonTable";
import PriceHistoryChart from "@/components/PriceHistoryChart";
import { formatPrice } from "@/lib/utils";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const GENDER_LABEL: Record<string, string> = {
  men: "Homme",
  women: "Femme",
  unisex: "Unisexe",
};

interface PageProps {
  params: Promise<{ id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params;
  if (USE_MOCK && id === "1") {
    return { title: `${MOCK_PRODUCT_DETAIL.brand} ${MOCK_PRODUCT_DETAIL.name}` };
  }
  const product = await getProduct(id);
  if (isApiError(product)) return { title: "Parfum introuvable" };
  return {
    title: `${product.brand} ${product.name}`,
    description: `Comparez les prix de ${product.brand} ${product.name} ${product.size_ml ? `${product.size_ml}ml` : ""} sur Primor, Sephora et Nocibé.`,
  };
}

export default async function ProductDetailPage({ params }: PageProps) {
  const { id } = await params;

  let product = USE_MOCK ? MOCK_PRODUCT_DETAIL : await getProduct(id);
  let history = USE_MOCK ? MOCK_HISTORY : await getProductHistory(id);

  if (isApiError(product)) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20 text-center">
        <p className="text-5xl mb-4">😕</p>
        <h1 className="text-2xl font-bold text-gray-800 mb-2">Parfum introuvable</h1>
        <p className="text-gray-500 mb-6">{product.message}</p>
        <Link href="/products" className="text-indigo-600 font-medium hover:underline">← Retour aux parfums</Link>
      </div>
    );
  }

  const historyData = isApiError(history) ? [] : history;
  const cheapest = product.listings.length > 0
    ? Math.min(...product.listings.map((l) => l.latest_price))
    : null;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Breadcrumb */}
      <nav className="text-sm text-gray-400 mb-6 flex items-center gap-2">
        <Link href="/products" className="hover:text-indigo-600 transition-colors">Parfums</Link>
        <span>/</span>
        <span className="text-gray-700 font-medium">{product.brand} {product.name}</span>
      </nav>

      {/* Hero */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-10 mb-12">
        {/* Image */}
        <div className="relative aspect-square rounded-2xl bg-gray-50 overflow-hidden border border-gray-100 flex items-center justify-center">
          {product.image_url ? (
            <Image
              src={product.image_url}
              alt={product.name}
              fill
              className="object-contain p-8"
              priority
            />
          ) : (
            <span className="text-8xl">🌸</span>
          )}
        </div>

        {/* Info */}
        <div className="flex flex-col justify-center gap-4">
          <div>
            <p className="text-sm font-semibold uppercase tracking-wider text-indigo-500 mb-1">{product.brand}</p>
            <h1 className="text-3xl font-bold text-gray-900 leading-tight">{product.name}</h1>
          </div>

          <div className="flex flex-wrap items-center gap-2 mt-1">
            {product.size_ml && (
              <span className="bg-gray-100 text-gray-600 text-sm px-3 py-1 rounded-full font-medium">
                {product.size_ml} ml
              </span>
            )}
            {product.gender && (
              <span className="bg-indigo-50 text-indigo-700 text-sm px-3 py-1 rounded-full font-medium">
                {GENDER_LABEL[product.gender] ?? product.gender}
              </span>
            )}
          </div>

          {cheapest !== null && (
            <div className="mt-2">
              <p className="text-sm text-gray-400">À partir de</p>
              <p className="text-4xl font-extrabold text-gray-900">{formatPrice(cheapest)}</p>
            </div>
          )}

          <p className="text-gray-500 text-sm">
            {product.listings.length} site{product.listings.length > 1 ? "s" : ""} référencé{product.listings.length > 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {/* Price comparison */}
      <section className="mb-12">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Comparaison des prix</h2>
        {product.listings.length > 0 ? (
          <PriceComparisonTable listings={product.listings} />
        ) : (
          <p className="text-gray-400">Aucune offre disponible pour ce parfum.</p>
        )}
      </section>

      {/* Price history */}
      <section>
        <h2 className="text-xl font-bold text-gray-900 mb-4">Historique des prix</h2>
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
          <PriceHistoryChart history={historyData} />
        </div>
      </section>
    </div>
  );
}
