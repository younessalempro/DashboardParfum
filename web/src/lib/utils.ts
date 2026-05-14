import type { Site } from "./types";

export const formatPrice = (price: number) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(price);

export const SITE_COLORS: Record<Site, string> = {
  primor: "#4CAF50",
  sephora: "#000000",
  nocibe: "#6B21A8",
};

export const SITE_LABELS: Record<Site, string> = {
  primor: "Primor",
  sephora: "Sephora",
  nocibe: "Nocibé",
};

export function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "À l'instant";
  if (minutes < 60) return `Il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Il y a ${hours}h`;
  const days = Math.floor(hours / 24);
  return `Il y a ${days}j`;
}
