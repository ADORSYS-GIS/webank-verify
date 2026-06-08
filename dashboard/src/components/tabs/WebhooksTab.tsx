import { useQuery } from "@tanstack/react-query";
import { fetchWebhooks } from "../../lib/api";

interface Props { verificationId: string; }

export default function WebhooksTab({ verificationId }: Props) {
  const { data: webhooks = [] } = useQuery({
    queryKey: ["webhooks", verificationId],
    queryFn: () => fetchWebhooks(verificationId),
  });

  if (webhooks.length === 0) {
    return <div className="text-gray-500 text-sm">No webhooks delivered yet</div>;
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Webhooks</p>
      {webhooks.map((wh) => (
        <div key={wh.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-mono text-gray-300">{wh.event_type}</span>
            <div className="flex items-center gap-2">
              <span className={`text-xs px-2 py-0.5 rounded font-mono ${
                wh.http_status && wh.http_status >= 200 && wh.http_status < 300
                  ? "bg-green-900 text-green-300"
                  : "bg-red-900 text-red-300"
              }`}>
                {wh.http_status ?? "—"}
              </span>
              <span className="text-xs text-gray-500">Attempt {wh.attempt}</span>
            </div>
          </div>
          <div className="flex justify-between text-xs text-gray-500">
            <span className="truncate max-w-xs">{wh.target_url ?? "—"}</span>
            <span>{new Date(wh.delivered_at).toLocaleString("fr-FR")}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
