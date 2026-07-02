import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ZoomIn } from "lucide-react";
import { fetchFrames } from "../../lib/api";
import type { DocumentFields } from "../../lib/types";
import ImageLightbox from "../ImageLightbox";

interface Props {
  doc: DocumentFields | null;
  verificationId: string;
}

function Badge({ ok }: { ok: boolean }) {
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${ok ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"}`}>
      {ok ? "✓" : "✗"}
    </span>
  );
}

function Row({ label, value, warn }: { label: string; value: string | null | undefined; warn?: boolean }) {
  return (
    <tr className="border-b border-gray-800">
      <td className="py-2 pr-4 text-xs text-gray-400 w-40">{label}</td>
      <td className={`py-2 text-sm ${warn ? "text-red-400" : "text-gray-200"}`}>{value ?? "—"}</td>
    </tr>
  );
}

export default function IDVerificationTab({ doc, verificationId }: Props) {
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const { data: imageUrls } = useQuery({
    queryKey: ["frames", verificationId],
    queryFn: () => fetchFrames(verificationId),
  });

  if (!doc) {
    return <div className="text-gray-500 text-sm">No document data available</div>;
  }

  const LABELS = ["Front", "Back", "Frame 3", "Frame 4"];
  const lightboxImages = (imageUrls ?? []).slice(0, 2).map((url, i) => ({
    url,
    label: LABELS[i] ?? `Image ${i + 1}`,
  }));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">ID Verification</span>
        <Badge ok={!doc.is_expired && !doc.is_underage} />
      </div>

      {/* Document images — clickable thumbnails */}
      {imageUrls && imageUrls.length > 0 && (
        <div>
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Document Images</h3>
          <div className="flex gap-4">
            {imageUrls.slice(0, 2).map((url, i) => (
              <div key={i} className="text-center">
                <button
                  onClick={() => setLightboxIndex(i)}
                  className="relative group rounded-lg overflow-hidden border border-gray-700 hover:border-brand-500 transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500"
                  title="Click to enlarge"
                >
                  <img
                    src={url}
                    alt={LABELS[i]}
                    className="w-64 h-40 object-cover group-hover:opacity-80 transition-opacity"
                  />
                  {/* Hover overlay */}
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30">
                    <div className="bg-black/60 rounded-full p-2">
                      <ZoomIn size={20} className="text-white" />
                    </div>
                  </div>
                </button>
                <p className="text-xs text-gray-400 mt-1">{LABELS[i]}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-6">
        {/* Front-side extracted fields */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Front Side</h3>
          <table className="w-full">
            <tbody>
              <Row label="Document type" value={doc.type} />
              <Row label="Last name" value={doc.last_name} />
              <Row label="First name" value={doc.first_name} />
              <Row label="Date of birth" value={doc.date_of_birth} />
              <Row label="Birthplace" value={doc.birth_place} />
              <Row label="Sex" value={doc.sex} />
              <Row label="Height" value={doc.height} />
              <Row label="Occupation" value={doc.profession} />
              <Row label="Age" value={doc.age !== null ? String(doc.age) : null} warn={doc.is_underage} />
            </tbody>
          </table>
        </div>

        {/* Back-side extracted fields + validity */}
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Back Side</h3>
            <table className="w-full">
              <tbody>
                <Row label="Document number" value={doc.document_number} />
                <Row label="Issue date" value={doc.issue_date} />
                <Row label="Expiry date" value={doc.expiry_date} warn={doc.is_expired} />
                <Row label="Father" value={doc.father} />
                <Row label="Mother" value={doc.mother} />
              </tbody>
            </table>
          </div>

          {/* Validity checks */}
          <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
            <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Validity Checks</h3>
            <ul className="space-y-2">
              {[
                { label: "Document not expired", ok: !doc.is_expired },
                { label: "Legal age (18+)", ok: !doc.is_underage },
                { label: "Name extracted", ok: !!(doc.first_name || doc.last_name) },
                { label: "Document number found", ok: !!doc.document_number },
                { label: "Date of birth found", ok: !!doc.date_of_birth },
                { label: "OCR confidence ≥ 50%", ok: doc.confidence >= 0.5 },
              ].map(({ label, ok }) => (
                <li key={label} className="flex items-center justify-between text-sm">
                  <span className={ok ? "text-gray-300" : "text-red-400"}>{label}</span>
                  <Badge ok={ok} />
                </li>
              ))}
            </ul>

            <div className="mt-4 pt-4 border-t border-gray-800">
              <div className="flex justify-between text-xs">
                <span className="text-gray-400">OCR confidence</span>
                <span className="text-gray-200 font-mono">{(doc.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="mt-1 bg-gray-800 rounded-full h-1.5">
                <div className="h-1.5 rounded-full bg-brand-600" style={{ width: `${doc.confidence * 100}%` }} />
              </div>
            </div>
          </div>
        </div>
      </div>

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
