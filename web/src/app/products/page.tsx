"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import type { ProductListItem, Gender } from "@/lib/types";
import { getProducts, getBrands, isApiError } from "@/lib/api";
import { MOCK_PRODUCTS } from "@/lib/mockData";
import ProductCard from "@/components/ProductCard";
import SkeletonCard from "@/components/SkeletonCard";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

const SORT_OPTIONS = [
  { value: "price_asc", label: "Prix croissant" },
  { value: "price_desc", label: "Prix décroissant" },
  { value: "name", label: "Nom A → Z" },
];

const GENDER_OPTIONS: { value: Gender | ""; label: string }[] = [
  { value: "", label: "Tous" },
  { value: "men", label: "Homme" },
  { value: "women", label: "Femme" },
  { value: "unisex", label: "Unisexe" },
];

export default function ProductsPage() {
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [brands, setBrands] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 12;

  // Filters
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [brand, setBrand] = useState("");
  const [gender, setGender] = useState<Gender | "">("");
  const [sort, setSort] = useState<"price_asc" | "price_desc" | "name">("price_asc");

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  // Reset page on filter change
  useEffect(() => { setPage(1); }, [brand, gender, sort]);

  // Load brands
  useEffect(() => {
    if (USE_MOCK) {
      const b = [...new Set(MOCK_PRODUCTS.map((p) => p.brand))].sort();
      setBrands(b);
      return;
    }
    getBrands().then((res) => {
      if (!isApiError(res)) setBrands(res);
    });
  }, []);

  // Load products
  const fetchProducts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (USE_MOCK) {
        await new Promise((r) => setTimeout(r, 400));
        let filtered = [...MOCK_PRODUCTS];
        if (debouncedSearch) {
          const q = debouncedSearch.toLowerCase();
          filtered = filtered.filter(
            (p) =>
              p.name.toLowerCase().includes(q) ||
              p.brand.toLowerCase().includes(q)
          );
        }
        if (brand) filtered = filtered.filter((p) => p.brand === brand);
        if (gender) filtered = filtered.filter((p) => p.gender === gender);
        if (sort === "price_asc") filtered.sort((a, b) => a.cheapest_price - b.cheapest_price);
        if (sort === "price_desc") filtered.sort((a, b) => b.cheapest_price - a.cheapest_price);
        if (sort === "name") filtered.sort((a, b) => a.name.localeCompare(b.name));
        setTotal(filtered.length);
        const start = (page - 1) * pageSize;
        setProducts(page === 1 ? filtered.slice(0, pageSize) : (prev) => [...prev, ...filtered.slice(start, start + pageSize)]);
      } else {
        const res = await getProducts({
          q: debouncedSearch || undefined,
          brand: brand || undefined,
          gender: gender || undefined,
          sort,
          page,
          page_size: pageSize,
        });
        if (isApiError(res)) {
          setError(res.message);
        } else {
          setTotal(res.total);
          setProducts(page === 1 ? res.items : (prev) => [...prev, ...res.items]);
        }
      }
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch, brand, gender, sort, page]);

  useEffect(() => { fetchProducts(); }, [fetchProducts]);

  const hasMore = products.length < total;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Parfums</h1>
        <p className="text-gray-500 text-sm">{total > 0 ? `${total} parfum${total > 1 ? "s" : ""}` : "Recherchez parmi nos parfums"}</p>
      </div>

      {/* Filters bar */}
      <div className="flex flex-wrap gap-3 mb-8 items-center">
        {/* Search */}
        <div className="relative flex-1 min-w-[200px]">
          <span className="absolute inset-y-0 left-3 flex items-center text-gray-400">🔍</span>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un parfum ou une marque…"
            className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400 bg-white"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-gray-600"
            >✕</button>
          )}
        </div>

        {/* Brand */}
        <select
          value={brand}
          onChange={(e) => setBrand(e.target.value)}
          className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 text-gray-700"
        >
          <option value="">Toutes les marques</option>
          {brands.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </select>

        {/* Gender */}
        <div className="flex rounded-xl border border-gray-200 bg-white overflow-hidden text-sm">
          {GENDER_OPTIONS.map((g) => (
            <button
              key={g.value}
              onClick={() => setGender(g.value)}
              className={`px-3 py-2.5 font-medium transition-colors ${gender === g.value ? "bg-indigo-600 text-white" : "text-gray-600 hover:bg-gray-50"}`}
            >
              {g.label}
            </button>
          ))}
        </div>

        {/* Sort */}
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="border border-gray-200 rounded-xl px-3 py-2.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-400 text-gray-700"
        >
          {SORT_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
      </div>

      {/* Grid */}
      {error ? (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-8 text-center">
          <p className="text-red-600 font-medium">{error}</p>
          <button onClick={() => fetchProducts()} className="mt-3 text-sm text-red-500 underline">Réessayer</button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-5">
            {products.map((p) => <ProductCard key={p.id} product={p} />)}
            {loading && Array.from({ length: 8 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>

          {/* Empty state */}
          {!loading && products.length === 0 && (
            <div className="text-center py-20">
              <p className="text-5xl mb-4">🔎</p>
              <p className="text-lg font-semibold text-gray-700">Aucun parfum trouvé</p>
              <p className="text-gray-400 mt-1">Essayez d'ajuster vos filtres ou votre recherche.</p>
              <button
                onClick={() => { setSearch(""); setBrand(""); setGender(""); }}
                className="mt-4 text-indigo-600 text-sm font-medium hover:underline"
              >
                Réinitialiser les filtres
              </button>
            </div>
          )}

          {/* Load more */}
          {hasMore && !loading && (
            <div className="flex justify-center mt-10">
              <button
                onClick={() => setPage((p) => p + 1)}
                className="px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-colors"
              >
                Charger plus de parfums
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
