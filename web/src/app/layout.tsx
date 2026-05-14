import type { Metadata } from "next";
import { Geist } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });

export const metadata: Metadata = {
  title: { default: "Perfume Price Comparator", template: "%s | Perfume Price Comparator" },
  description: "Comparez les prix des parfums en temps réel sur Primor, Sephora et Nocibé.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className={`${geist.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-gray-50 text-gray-900">
        {/* Navbar */}
        <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center h-16 gap-6">
            <Link href="/products" className="flex items-center gap-2 font-bold text-xl tracking-tight text-gray-900 hover:text-indigo-600 transition-colors">
              <span className="text-2xl">🌸</span>
              <span>ParfumCompare</span>
            </Link>
            <nav className="flex items-center gap-4 ml-4 text-sm font-medium text-gray-600">
              <Link href="/products" className="hover:text-indigo-600 transition-colors">Parfums</Link>
              <Link href="/admin/scrape" className="hover:text-indigo-600 transition-colors">Admin</Link>
            </nav>
            <div className="ml-auto flex items-center gap-2 text-xs text-gray-400">
              <span className="inline-block w-2 h-2 rounded-full bg-green-400"></span>
              Primor · Sephora · Nocibé
            </div>
          </div>
        </header>

        {/* Main */}
        <main className="flex-1">{children}</main>

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200 mt-auto">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-sm text-gray-400">
            <span>© 2026 ParfumCompare — usage personnel uniquement</span>
            <span>Données issues de Primor, Sephora, Nocibé</span>
          </div>
        </footer>
      </body>
    </html>
  );
}
