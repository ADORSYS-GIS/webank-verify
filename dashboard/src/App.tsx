import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchVerifications } from "./lib/api";
import VerificationList from "./pages/VerificationList";
import VerificationDetail from "./pages/VerificationDetail";

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["verifications", statusFilter],
    queryFn: () => fetchVerifications({ status: statusFilter || undefined }),
    refetchInterval: 10_000,
  });

  const pendingCount = data?.items.filter((v) => v.status === "manual_review" || v.status === "pending").length ?? 0;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Left panel */}
      <aside className="w-80 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-semibold text-white">Verifications</h1>
            {pendingCount > 0 && (
              <span className="text-xs bg-gray-800 border border-gray-600 text-gray-300 px-2 py-0.5 rounded-full">
                {pendingCount} on review
              </span>
            )}
          </div>
          {/* Status filter pills */}
          <div className="flex gap-1.5 flex-wrap">
            {["", "pending", "manual_review", "approved", "rejected"].map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors ${
                  statusFilter === s
                    ? "bg-brand-600 border-brand-500 text-white"
                    : "border-gray-700 text-gray-400 hover:border-gray-500"
                }`}
              >
                {s || "All"}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading && (
            <div className="p-6 text-center text-gray-500 text-sm">Loading…</div>
          )}
          {data?.items.map((v) => (
            <VerificationList
              key={v.id}
              item={v}
              selected={v.id === selectedId}
              onClick={() => setSelectedId(v.id)}
            />
          ))}
          {data?.items.length === 0 && (
            <div className="p-6 text-center text-gray-500 text-sm">No verifications found</div>
          )}
        </div>
      </aside>

      {/* Right panel */}
      <main className="flex-1 overflow-hidden bg-gray-950">
        {selectedId ? (
          <VerificationDetail id={selectedId} onClose={() => setSelectedId(null)} />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-600 text-sm">
            Select a verification to review
          </div>
        )}
      </main>
    </div>
  );
}
