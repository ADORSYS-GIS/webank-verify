import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Loader2 } from "lucide-react";
import { fetchWebhooks, resendWebhook } from "../../lib/api";

interface Props {
  verificationId: string;
  /** Current status of the verification — used to decide if resend is available */
  verificationStatus: string;
}

export default function WebhooksTab({ verificationId, verificationStatus }: Props) {
  const qc = useQueryClient();
  const [resending, setResending] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);
  const [resendSuccess, setResendSuccess] = useState(false);

  const { data: webhooks = [] } = useQuery({
    queryKey: ["webhooks", verificationId],
    queryFn: () => fetchWebhooks(verificationId),
  });

  // The last delivery for the approval/rejection event
  const lastDelivery = webhooks.find(
    (wh) => wh.event_type === "kyc.level2.approved" || wh.event_type === "kyc.level2.rejected",
  );
  const lastDeliveryFailed =
    lastDelivery != null &&
    (lastDelivery.http_status == null ||
      lastDelivery.http_status < 200 ||
      lastDelivery.http_status >= 300);

  // Show resend button when the verification is approved/rejected AND last delivery failed
  const canResend =
    (verificationStatus === "approved" || verificationStatus === "rejected") &&
    lastDeliveryFailed;

  async function handleResend() {
    setResending(true);
    setResendError(null);
    setResendSuccess(false);
    try {
      await resendWebhook(verificationId);
      setResendSuccess(true);
      // Refresh webhooks list after a short delay to show the new attempt
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["webhooks", verificationId] });
      }, 2000);
    } catch (err) {
      setResendError(err instanceof Error ? err.message : "Failed to resend");
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <p className="text-sm font-semibold text-white uppercase tracking-wider">Webhooks</p>

        {/* Resend button — only shown when last delivery failed */}
        {canResend && (
          <button
            onClick={handleResend}
            disabled={resending}
            className="flex items-center gap-1.5 text-xs bg-yellow-700 hover:bg-yellow-600 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1.5 rounded-md transition-colors"
          >
            {resending
              ? <Loader2 size={12} className="animate-spin" />
              : <RefreshCw size={12} />}
            {resending ? "Resending…" : "Resend Webhook"}
          </button>
        )}
      </div>

      {/* Resend feedback */}
      {resendSuccess && (
        <div className="text-xs text-green-300 bg-green-950 border border-green-800 rounded px-3 py-2">
          Webhook queued for re-delivery. Check below in a few seconds.
        </div>
      )}
      {resendError && (
        <div className="text-xs text-red-300 bg-red-950 border border-red-800 rounded px-3 py-2">
          {resendError}
        </div>
      )}

      {webhooks.length === 0 ? (
        <div className="text-gray-500 text-sm">No webhooks delivered yet</div>
      ) : (
        webhooks.map((wh) => {
          const ok = wh.http_status != null && wh.http_status >= 200 && wh.http_status < 300;
          return (
            <div key={wh.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-mono text-gray-300">{wh.event_type}</span>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded font-mono ${
                    ok ? "bg-green-900 text-green-300" : "bg-red-900 text-red-300"
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
          );
        })
      )}
    </div>
  );
}
