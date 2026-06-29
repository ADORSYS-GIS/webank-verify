import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X, Upload } from "lucide-react";
import { fetchVerifications, createVerification } from "./lib/api";
import VerificationList from "./pages/VerificationList";
import VerificationDetail from "./pages/VerificationDetail";

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [showNewModal, setShowNewModal] = useState(false);
  const qc = useQueryClient();

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
            <div className="flex items-center gap-2">
              {pendingCount > 0 && (
                <span className="text-xs bg-gray-800 border border-gray-600 text-gray-300 px-2 py-0.5 rounded-full">
                  {pendingCount} on review
                </span>
              )}
              <button
                onClick={() => setShowNewModal(true)}
                className="flex items-center gap-1 text-xs bg-brand-600 hover:bg-brand-500 text-white px-2 py-1 rounded-md transition-colors"
                title="Create verification (WhatsApp path)"
              >
                <Plus size={14} />
                New
              </button>
            </div>
          </div>
          {/* Status filter pills */}
          <div className="flex gap-1">
            {[
              { value: "", label: "All" },
              { value: "pending", label: "Pending" },
              { value: "manual_review", label: "Review" },
              { value: "approved", label: "Approved" },
              { value: "rejected", label: "Rejected" },
            ].map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setStatusFilter(value)}
                className={`text-xs px-2 py-0.5 rounded-full border transition-colors whitespace-nowrap ${
                  statusFilter === value
                    ? "bg-brand-600 border-brand-500 text-white"
                    : "border-gray-700 text-gray-400 hover:border-gray-500"
                }`}
              >
                {label}
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

      {/* New Verification Modal */}
      {showNewModal && (
        <NewVerificationModal
          onClose={() => setShowNewModal(false)}
          onSuccess={(id) => {
            setShowNewModal(false);
            setSelectedId(id);
            qc.invalidateQueries({ queryKey: ["verifications"] });
          }}
        />
      )}
    </div>
  );
}

function NewVerificationModal({
  onClose,
  onSuccess,
}: {
  onClose: () => void;
  onSuccess: (id: string) => void;
}) {
  const [userId, setUserId] = useState("");
  const [docType, setDocType] = useState<"CNI" | "PASSPORT">("CNI");
  const [frontFile, setFrontFile] = useState<File | null>(null);
  const [backFile, setBackFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!frontFile) {
      setError("Front image is required");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const result = await createVerification({
        user_id: userId,
        document_type: docType,
        front_image: frontFile,
        back_image: backFile ?? undefined,
      });
      onSuccess(result.verification_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create verification");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-[480px] max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-white font-medium">New Verification</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 p-1 rounded">
            <X size={18} />
          </button>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Create a verification record from documents collected via WhatsApp. The verification will be queued for operator review.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* User ID */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">User ID *</label>
            <input
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
              placeholder="Enter user ID"
              className="w-full bg-gray-800 border border-gray-700 rounded text-sm text-white p-2 outline-none focus:border-brand-500"
            />
          </div>

          {/* Document Type */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Document Type *</label>
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value as "CNI" | "PASSPORT")}
              className="w-full bg-gray-800 border border-gray-700 rounded text-sm text-white p-2 outline-none focus:border-brand-500"
            >
              <option value="CNI">CNI (National ID)</option>
              <option value="PASSPORT">Passport</option>
            </select>
          </div>

          {/* Front Image */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Front Image *</label>
            <div className="relative">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => setFrontFile(e.target.files?.[0] ?? null)}
                className="hidden"
                id="front-image"
              />
              <label
                htmlFor="front-image"
                className="flex items-center gap-2 w-full bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 p-2 cursor-pointer hover:border-gray-500 transition-colors"
              >
                <Upload size={16} />
                <span className="truncate">{frontFile ? frontFile.name : "Select front image…"}</span>
              </label>
            </div>
            {frontFile && (
              <p className="text-xs text-gray-500 mt-1">
                {(frontFile.size / 1024 / 1024).toFixed(2)} MB
              </p>
            )}
          </div>

          {/* Back Image (optional) */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">Back Image (optional)</label>
            <div className="relative">
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => setBackFile(e.target.files?.[0] ?? null)}
                className="hidden"
                id="back-image"
              />
              <label
                htmlFor="back-image"
                className="flex items-center gap-2 w-full bg-gray-800 border border-gray-700 rounded text-sm text-gray-300 p-2 cursor-pointer hover:border-gray-500 transition-colors"
              >
                <Upload size={16} />
                <span className="truncate">{backFile ? backFile.name : "Select back image…"}</span>
              </label>
            </div>
            {backFile && (
              <p className="text-xs text-gray-500 mt-1">
                {(backFile.size / 1024 / 1024).toFixed(2)} MB
              </p>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="text-xs text-red-400 bg-red-950 border border-red-800 rounded p-2">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-gray-400 hover:text-gray-200 px-3 py-1.5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !userId || !frontFile}
              className="bg-brand-600 disabled:opacity-40 hover:bg-brand-500 text-white text-xs px-3 py-1.5 rounded-md"
            >
              {loading ? "Creating…" : "Create Verification"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}