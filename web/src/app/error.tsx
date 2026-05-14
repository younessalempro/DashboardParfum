"use client";
import { useEffect } from "react";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  useEffect(() => { console.error(error); }, [error]);
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <p className="text-6xl mb-4">⚠️</p>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">Une erreur est survenue</h2>
      <p className="text-gray-500 mb-6">{error.message}</p>
      <button
        onClick={reset}
        className="px-5 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-colors"
      >
        Réessayer
      </button>
    </div>
  );
}
