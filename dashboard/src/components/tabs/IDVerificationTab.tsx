import type { DocumentFields } from "../../lib/types";

interface Props { doc: DocumentFields | null; }

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

export default function IDVerificationTab({ doc }: Props) {
  if (!doc) {
    return <div className="text-gray-500 text-sm">No document data available</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">ID Verification</span>
        <Badge ok={!doc.is_expired && !doc.is_underage} />
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Extracted fields */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Extracted Fields</h3>
          <table className="w-full">
            <tbody>
              <Row label="Document type" value={doc.type} />
              <Row label="Last name" value={doc.last_name} />
              <Row label="First name" value={doc.first_name} />
              <Row label="Date of birth" value={doc.date_of_birth} />
              <Row label="Birth place" value={doc.birth_place} />
              <Row label="Document number" value={doc.document_number} />
              <Row label="Expiry date" value={doc.expiry_date} warn={doc.is_expired} />
              <Row label="Age" value={doc.age !== null ? String(doc.age) : null} warn={doc.is_underage} />
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
  );
}
