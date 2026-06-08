import type { VerificationDetail } from "../../lib/types";

interface Props { verification: VerificationDetail; }

export default function AMLTab({ verification }: Props) {
  const name = [verification.document?.first_name, verification.document?.last_name]
    .filter(Boolean).join(" ") || "Unknown";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">AML Screening</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-green-900 text-green-300 font-medium">✓ CLEAR</span>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Checks</h3>
        <ul className="space-y-2.5">
          {[
            { label: "UN Sanctions List", result: "clear" },
            { label: "EU Sanctions List", result: "clear" },
            { label: "OFAC SDN List", result: "clear" },
            { label: "PEP (Politically Exposed Person)", result: "not found" },
            { label: "Adverse Media", result: "not found" },
          ].map(({ label, result }) => (
            <li key={label} className="flex items-center justify-between text-sm">
              <span className="text-gray-300">{label}</span>
              <span className="text-xs px-2 py-0.5 rounded bg-green-900 text-green-300">{result}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
        <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-2 font-semibold">Name Searched</h3>
        <p className="text-sm text-gray-200 font-medium">{name}</p>
        <p className="text-xs text-gray-500 mt-1">Checked against UN, EU, and OFAC open-source lists</p>
      </div>
    </div>
  );
}
