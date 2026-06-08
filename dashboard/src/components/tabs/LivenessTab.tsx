import { useQuery } from "@tanstack/react-query";
import { fetchFrames } from "../../lib/api";
import type { LivenessMetrics } from "../../lib/types";

interface Props {
  verificationId: string;
  liveness: LivenessMetrics | null;
}

function ScoreCard({ label, value, suffix = "%" }: { label: string; value: number | null; suffix?: string }) {
  const color = value === null ? "text-gray-500" :
    value >= 80 ? "text-brand-500" : value >= 60 ? "text-yellow-400" : "text-red-400";
  const pct = value ?? 0;
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 text-center">
      <p className="text-xs text-gray-400 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value !== null ? `${value.toFixed(1)}${suffix}` : "—"}</p>
      {value !== null && (
        <div className="mt-2 bg-gray-800 rounded-full h-1.5">
          <div className="h-1.5 rounded-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  );
}

export default function LivenessTab({ verificationId, liveness }: Props) {
  const { data: frameUrls } = useQuery({
    queryKey: ["frames", verificationId],
    queryFn: () => fetchFrames(verificationId),
  });

  return (
    <div className="space-y-6">
      {/* Liveness check header */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">Liveness</span>
        {liveness && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            liveness.passed ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
          }`}>
            {liveness.passed ? "✓ PASSED" : "✗ FAILED"}
          </span>
        )}
      </div>

      <div className="flex gap-6">
        {/* Video / frames preview */}
        <div className="w-64 flex-shrink-0">
          {frameUrls && frameUrls.length > 0 ? (
            <div className="space-y-2">
              <img
                src={frameUrls[0]}
                alt="Liveness frame"
                className="w-full rounded-lg border border-gray-700 object-cover"
              />
              {frameUrls.length > 1 && (
                <div className="flex gap-1.5">
                  {frameUrls.slice(1).map((url, i) => (
                    <img key={i} src={url} alt={`Frame ${i + 2}`}
                      className="w-16 h-16 rounded border border-gray-700 object-cover" />
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="w-full h-48 bg-gray-800 rounded-lg flex items-center justify-center border border-gray-700">
              <span className="text-gray-600 text-sm">No frames</span>
            </div>
          )}
        </div>

        {/* Score metrics */}
        <div className="flex-1 grid grid-cols-2 gap-3 content-start">
          <ScoreCard label="Liveness Score" value={liveness?.score ?? null} />
          <ScoreCard label="Face Quality" value={liveness?.face_quality ?? null} />
          <ScoreCard label="Face Occlusion" value={liveness?.face_occlusion ?? null} />
          <ScoreCard label="Face Luminance" value={liveness?.face_luminance ?? null} />
        </div>
      </div>

      {/* Face matches grid (similar to Didit) */}
      {frameUrls && frameUrls.length > 1 && (
        <div>
          <p className="text-xs text-gray-400 mb-2 font-medium">Face Matches</p>
          <div className="flex gap-3">
            {frameUrls.map((url, i) => (
              <div key={i} className="relative">
                <img src={url} alt={`Frame ${i + 1}`}
                  className="w-24 h-28 rounded-lg border border-gray-700 object-cover" />
                <div className="absolute bottom-1 left-1 right-1 bg-black/60 rounded text-center">
                  <span className="text-xs text-green-300 font-medium">
                    {liveness ? `${(liveness.score - i * 2).toFixed(1)}%` : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {liveness && (
        <div className="text-xs text-gray-500">
          {liveness.frames_analyzed} frame{liveness.frames_analyzed !== 1 ? "s" : ""} analyzed
        </div>
      )}
    </div>
  );
}
