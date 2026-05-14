"use client";
import { useState, useEffect, useRef } from "react";
import { triggerScrape, getScrapeStatus, isApiError } from "@/lib/api";
import type { ScrapeJob } from "@/lib/types";
import AdminTokenInput from "@/components/AdminTokenInput";

type SiteKey = "primor" | "sephora" | "nocibe";

const SITES: { key: SiteKey; label: string; emoji: string }[] = [
  { key: "primor", label: "Primor", emoji: "🟢" },
  { key: "sephora", label: "Sephora", emoji: "⚫" },
  { key: "nocibe", label: "Nocibé", emoji: "🟣" },
];

function StatusBadge({ status }: { status: ScrapeJob["status"] }) {
  const map = {
    running: "bg-blue-100 text-blue-700",
    done: "bg-green-100 text-green-700",
    failed: "bg-red-100 text-red-700",
  };
  const labels = { running: "En cours…", done: "Terminé", failed: "Échec" };
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold ${map[status]}`}>
      {status === "running" && <span className="animate-spin inline-block">⟳</span>}
      {labels[status]}
    </span>
  );
}

function duration(start: string, end: string | null) {
  const ms = (end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function AdminScrapePage() {
  const [adminToken, setAdminToken] = useState("");
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const isRunning = jobs[0]?.status === "running";

  // Poll active job
  useEffect(() => {
    if (!activeJobId || !adminToken) return;
    pollRef.current = setInterval(async () => {
      const res = await getScrapeStatus(activeJobId, adminToken);
      if (isApiError(res)) return;
      setJobs((prev) => {
        const next = [...prev];
        const idx = next.findIndex((j) => j.job_id === res.job_id);
        if (idx >= 0) next[idx] = res;
        return next;
      });
      if (res.status !== "running") {
        clearInterval(pollRef.current!);
        setActiveJobId(null);
      }
    }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [activeJobId, adminToken]);

  const handleScrape = async (sites: SiteKey[]) => {
    if (!adminToken) {
      setError("Veuillez entrer le token admin.");
      return;
    }
    setError(null);
    setIsSubmitting(true);
    const res = await triggerScrape(sites, adminToken);
    setIsSubmitting(false);
    if (isApiError(res)) {
      setError(res.message);
      return;
    }
    const newJob: ScrapeJob = {
      job_id: res.job_id,
      status: "running",
      items_added: 0,
      items_updated: 0,
      items_errored: 0,
      started_at: new Date().toISOString(),
      finished_at: null,
    };
    setJobs((prev) => [newJob, ...prev]);
    setActiveJobId(res.job_id);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
      <h1 className="text-3xl font-bold text-gray-900 mb-2">Administration</h1>
      <p className="text-gray-500 text-sm mb-8">Déclenchez un scrape manuel pour mettre à jour les prix.</p>

      {/* Token */}
      <div className="mb-8">
        <AdminTokenInput onTokenChange={setAdminToken} />
      </div>

      {/* Scrape buttons */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 mb-8">
        <h2 className="font-semibold text-gray-800 mb-4">Déclencher un scrape</h2>
        <div className="flex flex-wrap gap-3">
          {SITES.map(({ key, label, emoji }) => (
            <button
              key={key}
              disabled={isRunning || isSubmitting || !adminToken}
              onClick={() => handleScrape([key])}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl border border-gray-200 text-sm font-medium text-gray-700 hover:border-indigo-400 hover:text-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>{emoji}</span> Scraper {label}
            </button>
          ))}
          <button
            disabled={isRunning || isSubmitting || !adminToken}
            onClick={() => handleScrape(["primor", "sephora", "nocibe"])}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            🚀 Tout scraper
          </button>
        </div>

        {error && (
          <p className="mt-3 text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">{error}</p>
        )}
      </div>

      {/* Job log */}
      {jobs.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="font-semibold text-gray-800">Journal des jobs</h2>
          </div>
          <ul className="divide-y divide-gray-50">
            {jobs.map((job) => (
              <li key={job.job_id} className="px-6 py-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-col gap-1">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={job.status} />
                    <code className="text-xs text-gray-400 font-mono">{job.job_id}</code>
                  </div>
                  <p className="text-xs text-gray-500">
                    Démarré · {new Date(job.started_at).toLocaleTimeString("fr-FR")}
                    {" · "}Durée : {duration(job.started_at, job.finished_at)}
                  </p>
                </div>
                <div className="flex gap-4 text-sm font-medium">
                  <span className="text-green-600">+{job.items_added} ajouté{job.items_added > 1 ? "s" : ""}</span>
                  <span className="text-blue-600">~{job.items_updated} maj</span>
                  <span className="text-red-500">{job.items_errored} erreur{job.items_errored > 1 ? "s" : ""}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
