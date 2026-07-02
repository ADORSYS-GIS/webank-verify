import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ZoomIn } from "lucide-react";
import { fetchFrames } from "../../lib/api";
import type { LivenessMetrics } from "../../lib/types";
import ImageLightbox from "../ImageLightbox";

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
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const { data: frameUrls } = useQuery({
    queryKey: ["frames", verificationId],
    queryFn: () => fetchFrames(verificationId),
  });

  const lightboxImages = (frameUrls ?? []).map((url, i) => ({
    url,
    label: `Frame ${i + 1}`,
  }));

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
        {/* Main frame — clickable */}
        <div className="w-64 shrink-0">
          {frameUrls && frameUrls.length > 0 ? (
            <div className="space-y-2">
              <button
                onClick={() => setLightboxIndex(0)}
                className="relative group w-full rounded-lg overflow-hidden border border-gray-700 hover:border-brand-500 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
                title="Click to enlarge"
              >
                <img
                  src={frameUrls[0]}
                  alt="Liveness frame"
                  className="w-full object-cover group-hover:opacity-80 transition-opacity"
                />
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30">
                  <div className="bg-black/60 rounded-full p-2">
                    <ZoomIn size={20} className="text-white" />
                  </div>
                </div>
              </button>
              {/* Thumbnail strip */}
              {frameUrls.length > 1 && (
                <div className="flex gap-1.5 flex-wrap">
                  {frameUrls.slice(1).map((url, i) => (
                    <button
                      key={i}
                      onClick={() => setLightboxIndex(i + 1)}
                      className="relative group rounded border border-gray-700 hover:border-brand-500 overflow-hidden transition-colors focus:outline-none focus:ring-1 focus:ring-brand-500"
                      title={`Frame ${i + 2} — click to enlarge`}
                    >
                      <img src={url} alt={`Frame ${i + 2}`}
                        className="w-16 h-16 object-cover group-hover:opacity-70 transition-opacity" />
                      <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/30 transition-opacity">
                        <ZoomIn size={12} className="text-white" />
                      </div>
                    </button>
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

      {/* Face matches grid — all frames clickable */}
      {frameUrls && frameUrls.length > 1 && (
        <div>
          <p className="text-xs text-gray-400 mb-2 font-medium">All Frames</p>
          <div className="flex gap-3 flex-wrap">
            {frameUrls.map((url, i) => (
              <button
                key={i}
                onClick={() => setLightboxIndex(i)}
                className="relative group focus:outline-none focus:ring-2 focus:ring-brand-500 rounded-lg"
                title={`Frame ${i + 1} — click to enlarge`}
              >
                <img src={url} alt={`Frame ${i + 1}`}
                  className="w-24 h-28 rounded-lg border border-gray-700 group-hover:border-brand-500 object-cover transition-colors" />
                <div className="absolute bottom-1 left-1 right-1 bg-black/60 rounded text-center">
                  <span className="text-xs text-green-300 font-medium">
                    {liveness ? `${(liveness.score - i * 2).toFixed(1)}%` : "—"}
                  </span>
                </div>
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 bg-black/20 rounded-lg transition-opacity">
                  <ZoomIn size={16} className="text-white drop-shadow" />
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {liveness && (
        <div className="text-xs text-gray-500">
          {liveness.frames_analyzed} frame{liveness.frames_analyzed !== 1 ? "s" : ""} analyzed
        </div>
      )}

      {/* Lightbox */}
      {lightboxIndex !== null && lightboxImages.length > 0 && (
        <ImageLightbox
          images={lightboxImages}
          initialIndex={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
        />
      )}
    </div>
  );
}
