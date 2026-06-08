import { useQuery } from "@tanstack/react-query";
import { fetchFrames } from "../../lib/api";
import type { FaceMatchResult } from "../../lib/types";

interface Props {
  faceMatch: FaceMatchResult | null;
  verificationId: string;
}

export default function FaceMatchTab({ faceMatch, verificationId }: Props) {
  const { data: frameUrls } = useQuery({
    queryKey: ["frames", verificationId],
    queryFn: () => fetchFrames(verificationId),
  });

  const similarity = faceMatch?.similarity ?? 0;
  const passed = faceMatch?.passed ?? false;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">Face Match</span>
        {faceMatch && (
          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
            passed ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
          }`}>
            {passed ? "✓ PASSED" : "✗ FAILED"}
          </span>
        )}
      </div>

      {faceMatch ? (
        <>
          {/* Side-by-side */}
          <div className="flex gap-6 items-center">
            <div className="text-center">
              {frameUrls?.[0] ? (
                <img src={frameUrls[0]} alt="ID face"
                  className="w-32 h-40 object-cover rounded-lg border border-gray-700 mx-auto" />
              ) : (
                <div className="w-32 h-40 bg-gray-800 rounded-lg border border-gray-700 flex items-center justify-center text-gray-600 text-xs mx-auto">
                  ID Photo
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">ID Document</p>
            </div>

            {/* Score in middle */}
            <div className="flex flex-col items-center gap-2">
              <div className={`text-4xl font-bold ${passed ? "text-green-400" : "text-red-400"}`}>
                {similarity.toFixed(1)}%
              </div>
              <div className="text-xs text-gray-400">similarity</div>
              <div className="w-24 bg-gray-800 rounded-full h-2">
                <div className={`h-2 rounded-full transition-all ${passed ? "bg-green-500" : "bg-red-500"}`}
                  style={{ width: `${similarity}%` }} />
              </div>
            </div>

            <div className="text-center">
              {frameUrls?.[1] ?? frameUrls?.[0] ? (
                <img src={frameUrls[1] ?? frameUrls[0]} alt="Selfie"
                  className="w-32 h-40 object-cover rounded-lg border border-gray-700 mx-auto" />
              ) : (
                <div className="w-32 h-40 bg-gray-800 rounded-lg border border-gray-700 flex items-center justify-center text-gray-600 text-xs mx-auto">
                  Selfie
                </div>
              )}
              <p className="text-xs text-gray-400 mt-1">Selfie</p>
            </div>
          </div>

          {/* Details */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
            <Row label="Model" value={faceMatch.model} />
            <Row label="Similarity" value={`${similarity.toFixed(2)}%`} />
            <Row label="Distance" value={faceMatch.distance.toFixed(4)} />
            <Row label="Threshold" value={`${(faceMatch.threshold_used * 100).toFixed(0)}%`} />
            <Row label="Result" value={passed ? "PASSED" : "FAILED"} />
          </div>
        </>
      ) : (
        <div className="text-gray-500 text-sm">No face match data available</div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-200 font-mono">{value}</span>
    </div>
  );
}
