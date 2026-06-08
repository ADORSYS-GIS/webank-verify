import type { VerificationListItem } from "../lib/types";

interface Props {
  item: VerificationListItem;
  selected: boolean;
  onClick: () => void;
}

const STATUS_COLORS: Record<string, string> = {
  approved: "bg-green-500",
  rejected: "bg-red-500",
  pending: "bg-yellow-500",
  manual_review: "bg-yellow-400",
};

const FLAG: Record<string, string> = { CM: "🇨🇲", FR: "🇫🇷", US: "🇺🇸" };

export default function VerificationList({ item, selected, onClick }: Props) {
  const initials = item.user_id.slice(0, 2).toUpperCase();
  const flag = FLAG[item.country] ?? "🌐";
  const date = new Date(item.created_at).toLocaleDateString("fr-FR", {
    day: "numeric", month: "short", year: "numeric",
  });
  const time = new Date(item.created_at).toLocaleTimeString("fr-FR", {
    hour: "2-digit", minute: "2-digit",
  });

  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 border-b border-gray-800 transition-colors hover:bg-gray-800 ${
        selected ? "bg-gray-800 border-l-2 border-l-brand-500" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Avatar */}
        <div className="w-9 h-9 rounded-full bg-gray-700 flex items-center justify-center text-sm font-semibold text-gray-300 flex-shrink-0">
          {initials}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-white truncate">
              {item.user_id.slice(0, 20)}
            </span>
            {/* Status dot */}
            <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_COLORS[item.status] ?? "bg-gray-500"}`} />
          </div>

          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-xs text-gray-400">{flag} {item.country}</span>
            {item.doc_type && (
              <span className="text-xs text-gray-500">· {item.doc_type}</span>
            )}
          </div>

          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-gray-500">{date}</span>
            <div className="flex items-center gap-2">
              {item.warning_count > 0 && (
                <span className="text-xs text-yellow-500">⚠ {item.warning_count}</span>
              )}
              {item.risk_score !== null && (
                <span className={`text-xs font-mono ${
                  item.risk_score > 60 ? "text-red-400" :
                  item.risk_score > 30 ? "text-yellow-400" : "text-green-400"
                }`}>
                  {item.risk_score}%
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
    </button>
  );
}
