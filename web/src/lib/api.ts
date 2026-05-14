import type {
  ProductsParams,
  ProductsResponse,
  ProductDetail,
  PriceHistoryEntry,
  ScrapeJob,
  ApiError,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
  adminToken?: string
): Promise<T | ApiError> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };
  if (adminToken) headers["X-Admin-Token"] = adminToken;

  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
      next: { revalidate: 60 },
    });
    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        message = body.detail || body.message || message;
      } catch {}
      return { error: true, message, status: res.status };
    }
    return (await res.json()) as T;
  } catch (err) {
    return { error: true, message: String(err) };
  }
}

export function isApiError(val: unknown): val is ApiError {
  return typeof val === "object" && val !== null && (val as ApiError).error === true;
}

export async function getProducts(
  params: ProductsParams = {}
): Promise<ProductsResponse | ApiError> {
  const qs = new URLSearchParams();
  if (params.q) qs.set("q", params.q);
  if (params.brand) qs.set("brand", params.brand);
  if (params.gender) qs.set("gender", params.gender);
  if (params.min_price != null) qs.set("min_price", String(params.min_price));
  if (params.max_price != null) qs.set("max_price", String(params.max_price));
  if (params.sort) qs.set("sort", params.sort);
  if (params.page != null) qs.set("page", String(params.page));
  if (params.page_size != null) qs.set("page_size", String(params.page_size));
  const query = qs.toString() ? `?${qs}` : "";
  return apiFetch<ProductsResponse>(`/api/products${query}`);
}

export async function getProduct(
  id: string
): Promise<ProductDetail | ApiError> {
  return apiFetch<ProductDetail>(`/api/products/${id}`);
}

export async function getProductHistory(
  id: string
): Promise<PriceHistoryEntry[] | ApiError> {
  const res = await apiFetch<{ snapshots: PriceHistoryEntry[] } | PriceHistoryEntry[]>(
    `/api/products/${id}/history`
  );
  if (isApiError(res)) return res;
  // Unwrap the { snapshots: [...] } envelope the backend returns
  return "snapshots" in (res as object) ? (res as { snapshots: PriceHistoryEntry[] }).snapshots : (res as PriceHistoryEntry[]);
}

export async function getBrands(): Promise<string[] | ApiError> {
  const res = await apiFetch<{ items: { brand: string; count: number }[] } | string[]>(
    "/api/brands"
  );
  if (isApiError(res)) return res;
  // Unwrap the { items: [{brand, count}] } envelope the backend returns
  return "items" in (res as object)
    ? (res as { items: { brand: string; count: number }[] }).items.map((b) => b.brand)
    : (res as string[]);
}

export async function triggerScrape(
  sites: string[],
  adminToken: string
): Promise<{ job_id: string } | ApiError> {
  return apiFetch<{ job_id: string }>(
    "/api/admin/scrape",
    { method: "POST", body: JSON.stringify({ sites }) },
    adminToken
  );
}

export async function getScrapeStatus(
  jobId: string,
  adminToken: string
): Promise<ScrapeJob | ApiError> {
  return apiFetch<ScrapeJob>(`/api/admin/scrape/${jobId}`, undefined, adminToken);
}
