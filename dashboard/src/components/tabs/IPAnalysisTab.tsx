import type { IPAnalysis } from "../../lib/types";

interface Props {
  ip: IPAnalysis | null;
  deviceInfo: Record<string, string> | null;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-gray-400">{label}</span>
      <span className="text-gray-200 font-mono text-right max-w-xs truncate">{value || "—"}</span>
    </div>
  );
}

function Flag({ value }: { value: boolean }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${
      value ? "bg-red-900 text-red-300" : "bg-gray-800 text-gray-400"
    }`}>
      {value ? "Yes" : "No"}
    </span>
  );
}

export default function IPAnalysisTab({ ip, deviceInfo }: Props) {
  if (!ip) return <div className="text-gray-500 text-sm">No IP data available</div>;

  const riskColor = ip.risk_score > 60 ? "text-red-400" : ip.risk_score > 30 ? "text-yellow-400" : "text-green-400";

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-white uppercase tracking-wider">IP Analysis</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          ip.risk_score <= 20 ? "bg-green-900 text-green-300" :
          ip.risk_score <= 50 ? "bg-yellow-900 text-yellow-300" : "bg-red-900 text-red-300"
        }`}>
          Risk: {ip.risk_score}/100
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Geo info */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Geolocation</h3>
          <Row label="IP Address" value={ip.ip} />
          <Row label="Country" value={`${ip.country_name ?? ""} (${ip.country ?? "?"})`} />
          <Row label="City" value={ip.city ?? "—"} />
          <Row label="ISP" value={ip.isp ?? "—"} />
          <div className="pt-2 border-t border-gray-800">
            <div className="flex justify-between items-center">
              <span className="text-xs text-gray-400">Risk score</span>
              <span className={`text-lg font-bold ${riskColor}`}>{ip.risk_score}</span>
            </div>
            <div className="mt-1 bg-gray-800 rounded-full h-1.5">
              <div className={`h-1.5 rounded-full ${
                ip.risk_score > 60 ? "bg-red-500" : ip.risk_score > 30 ? "bg-yellow-500" : "bg-green-500"
              }`} style={{ width: `${ip.risk_score}%` }} />
            </div>
          </div>
        </div>

        {/* Risk flags */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4 space-y-2">
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Risk Flags</h3>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">VPN detected</span>
            <Flag value={ip.is_vpn} />
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Proxy detected</span>
            <Flag value={ip.is_proxy} />
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Tor exit node</span>
            <Flag value={ip.is_tor} />
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Cameroon IP</span>
            <Flag value={ip.country === "CM"} />
          </div>

          {ip.risk_flags.length > 0 && (
            <div className="pt-2 border-t border-gray-800">
              <p className="text-xs text-gray-500 mb-1">Active flags</p>
              <div className="flex flex-wrap gap-1">
                {ip.risk_flags.map((f) => (
                  <span key={f} className="text-xs bg-red-950 text-red-300 px-1.5 py-0.5 rounded">{f}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {deviceInfo && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <h3 className="text-xs text-gray-400 uppercase tracking-wider mb-3 font-semibold">Device</h3>
          <div className="space-y-2">
            {Object.entries(deviceInfo).map(([k, v]) => (
              <Row key={k} label={k} value={String(v)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
