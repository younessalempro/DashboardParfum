"use client";
import { useState, useEffect } from "react";

interface Props {
  onTokenChange: (token: string) => void;
}

export default function AdminTokenInput({ onTokenChange }: Props) {
  const [token, setToken] = useState("");
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("admin_token") || "";
    setToken(saved);
    onTokenChange(saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChange = (val: string) => {
    setToken(val);
    localStorage.setItem("admin_token", val);
    onTokenChange(val);
  };

  return (
    <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex flex-col gap-2">
      <div className="flex items-center gap-2 text-yellow-800 font-medium text-sm">
        <span>⚠️</span>
        <span>Token admin stocké localement — usage personnel uniquement</span>
      </div>
      <div className="flex gap-2">
        <input
          type={visible ? "text" : "password"}
          value={token}
          onChange={(e) => handleChange(e.target.value)}
          placeholder="Entrez le token admin (X-Admin-Token)"
          className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-400"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50"
        >
          {visible ? "Masquer" : "Afficher"}
        </button>
      </div>
    </div>
  );
}
