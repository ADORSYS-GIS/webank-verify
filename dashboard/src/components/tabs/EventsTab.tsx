import { useQuery } from "@tanstack/react-query";

const EVENT_ICONS: Record<string, string> = {
  document_submitted: "📄",
  liveness_checked: "👁",
  operator_approved: "✅",
  operator_rejected: "❌",
  webhook_sent: "🔔",
  face_matched: "👤",
};

async function fetchEvents(id: string) {
  const res = await fetch(`/admin/verifications/${id}`, {
    headers: { Authorization: `Bearer ${import.meta.env.VITE_ADMIN_TOKEN ?? "admin-secret-change-me"}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return [] as Array<{ event: string; payload: Record<string, unknown>; created_at: string }>;
}

interface Props { verificationId: string; }

export default function EventsTab({ verificationId }: Props) {
  const { data: events = [] } = useQuery({
    queryKey: ["events", verificationId],
    queryFn: () => fetchEvents(verificationId),
  });

  if (events.length === 0) {
    return <div className="text-gray-500 text-sm">No events recorded yet</div>;
  }

  return (
    <div className="space-y-2">
      <p className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Events</p>
      <div className="relative">
        <div className="absolute left-4 top-0 bottom-0 w-px bg-gray-800" />
        <ul className="space-y-4">
          {events.map((ev, i) => (
            <li key={i} className="flex gap-4 items-start">
              <div className="w-8 h-8 rounded-full bg-gray-800 border border-gray-700 flex items-center justify-center text-sm z-10">
                {EVENT_ICONS[ev.event] ?? "·"}
              </div>
              <div className="flex-1 bg-gray-900 border border-gray-800 rounded-lg p-3">
                <div className="flex justify-between">
                  <span className="text-sm font-mono text-gray-300">{ev.event}</span>
                  <span className="text-xs text-gray-500">
                    {new Date(ev.created_at).toLocaleString("fr-FR")}
                  </span>
                </div>
                {ev.payload && Object.keys(ev.payload).length > 0 && (
                  <pre className="text-xs text-gray-500 mt-1 overflow-x-auto">
                    {JSON.stringify(ev.payload, null, 2)}
                  </pre>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
