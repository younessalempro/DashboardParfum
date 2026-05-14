export type Site = "primor" | "sephora" | "nocibe";
export type Gender = "men" | "women" | "unisex";

export interface CanonicalProduct {
  id: string;
  brand: string;
  name: string;
  size_ml: number | null;
  gender: Gender | null;
  image_url: string | null;
}

export interface Listing {
  id: string;
  site: Site;
  url: string;
  name_on_site: string;
  image_url: string | null;
  latest_price: number;
  in_stock: boolean;
  last_seen_at: string;
}

export interface ProductListItem extends CanonicalProduct {
  cheapest_price: number;
  cheapest_site: Site;
}

export interface ProductDetail extends CanonicalProduct {
  listings: Listing[];
}

export interface PriceHistoryEntry {
  listing_id: string;
  site: Site;
  price: number;
  in_stock: boolean;
  scraped_at: string;
}

export interface ScrapeJob {
  job_id: string;
  status: "running" | "done" | "failed";
  items_added: number;
  items_updated: number;
  items_errored: number;
  started_at: string;
  finished_at: string | null;
}

export interface ProductsResponse {
  items: ProductListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ProductsParams {
  q?: string;
  brand?: string;
  gender?: Gender;
  min_price?: number;
  max_price?: number;
  sort?: "price_asc" | "price_desc" | "name";
  page?: number;
  page_size?: number;
}

export interface ApiError {
  error: true;
  message: string;
  status?: number;
}
