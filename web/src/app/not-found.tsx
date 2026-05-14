import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-6xl mb-4">🌸</p>
      <h1 className="text-4xl font-bold text-gray-900 mb-2">404</h1>
      <p className="text-lg text-gray-500 mb-6">Cette page n'existe pas.</p>
      <Link
        href="/products"
        className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-colors"
      >
        ← Retour aux parfums
      </Link>
    </div>
  );
}
