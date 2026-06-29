import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X, CheckCircle, XCircle, Clock } from "lucide-react";
import { approveVerification, fetchVerification, rejectVerification } from "../lib/api";
import LivenessTab from "../components/tabs/LivenessTab";
import IDVerificationTab from "../components/tabs/IDVerificationTab";
import FaceMatchTab from "../components/tabs/FaceMatchTab";
import AMLTab from "../components/tabs/AMLTab";
import IPAnalysisTab from "../components/tabs/IPAnalysisTab";
import EventsTab from "../components/tabs/EventsTab";
import WebhooksTab from "../components/tabs/WebhooksTab";

const TABS = ["Overview", "ID Verification", "Liveness", "Face Match", "AML Screening", "IP Analysis", "Events", "Webhooks"] as const;
type Tab = typeof TABS[number];

const STATUS_BADGE: Record<string, JSX.Element> = {
  approved: <span className="flex items-center gap-1 text-green-400 text-sm font-medium"><CheckCircle size={14} /> APPROVED</span>,
  rejected: <span className="flex items-center gap-1 text-red-400 text-sm font-medium"><XCircle size={14} /> REJECTED</span>,
  pending: <span className="flex items-center gap-1 text-yellow-400 text-sm font-medium"><Clock size={14} /> PENDING</span>,
  manual_review: <span className="flex items-center gap-1 text-yellow-400 text-sm font-medium"><Clock size={14} /> IN REVIEW</span>,
};

interface Props {
  id: string;
  onClose: () => void;
}

export default function VerificationDetail({ id, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<Tab>("Overview");
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);
  const qc = useQueryClient();

  const { data: v, isLoading } = useQuery({
    queryKey: ["verification", id],
    queryFn: () => fetchVerification(id),
  });

  async function handleApprove() {
    await approveVerification(id);
    qc.invalidateQueries({ queryKey: ["verification", id] });
    qc.invalidateQueries({ queryKey: ["verifications"] });
  }

  async function handleReject() {
    await rejectVerification(id, rejectReason);
    setShowRejectModal(false);
    qc.invalidateQueries({ queryKey: ["verification", id] });
    qc.invalidateQueries({ queryKey: ["verifications"] });
  }

  if (isLoading || !v) {
    return <div className="flex items-center justify-center h-full text-gray-500 text-sm">Loading…</div>;
  }

  const fullName = [v.document?.first_name, v.document?.last_name].filter(Boolean).join(" ") || v.user_id;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-gray-900">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-sm font-semibold">
            {fullName.slice(0, 2).toUpperCase()}
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">{fullName}</h2>
            <p className="text-xs text-gray-500">{v.user_id}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {STATUS_BADGE[v.status] ?? <span className="text-gray-400 text-sm">{v.status.toUpperCase()}</span>}
          {v.status === "pending" || v.status === "manual_review" ? (
            <>
              <button
                onClick={handleApprove}
                className="bg-green-600 hover:bg-green-500 text-white text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
              >
                Approve
              </button>
              <button
                onClick={() => setShowRejectModal(true)}
                className="bg-red-700 hover:bg-red-600 text-white text-xs font-medium px-3 py-1.5 rounded-md transition-colors"
              >
                Reject
              </button>
            </>
          ) : null}
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 p-1 rounded">
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Warnings banner */}
      {v.warnings.some((w) => w.severity === "critical") && (
        <div className="bg-red-950 border-b border-red-800 px-6 py-2 flex gap-2 flex-wrap">
          {v.warnings.filter((w) => w.severity === "critical").map((w) => (
            <span key={w.code} className="text-xs text-red-300 bg-red-900 px-2 py-0.5 rounded">
              ⚠ {w.message}
            </span>
          ))}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-0 overflow-x-auto border-b border-gray-800 bg-gray-900 px-4">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`text-xs font-medium px-3 py-3 whitespace-nowrap border-b-2 transition-colors ${
              activeTab === tab
                ? "border-brand-500 text-white"
                : "border-transparent text-gray-500 hover:text-gray-300"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === "Overview" && <OverviewTab v={v} />}
        {activeTab === "ID Verification" && <IDVerificationTab doc={v.document} />}
        {activeTab === "Liveness" && <LivenessTab verificationId={id} liveness={v.liveness} />}
        {activeTab === "Face Match" && <FaceMatchTab faceMatch={v.face_match} verificationId={id} />}
        {activeTab === "AML Screening" && <AMLTab verification={v} />}
        {activeTab === "IP Analysis" && <IPAnalysisTab ip={v.ip_intelligence} deviceInfo={v.device_info} />}
        {activeTab === "Events" && <EventsTab verificationId={id} />}
        {activeTab === "Webhooks" && <WebhooksTab verificationId={id} />}
      </div>

      {/* Reject modal */}
      {showRejectModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6 w-96">
            <h3 className="text-white font-medium mb-3">Reject verification</h3>
            <textarea
              className="w-full bg-gray-800 border border-gray-700 rounded text-sm text-white p-2 mb-4 h-24 resize-none outline-none focus:border-brand-500"
              placeholder="Reason for rejection…"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRejectModal(false)}
                className="text-xs text-gray-400 hover:text-gray-200 px-3 py-1.5"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim()}
                className="bg-red-700 disabled:opacity-40 hover:bg-red-600 text-white text-xs px-3 py-1.5 rounded-md"
              >
                Confirm reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function OverviewTab({ v }: { v: ReturnType<typeof fetchVerification> extends Promise<infer T> ? T : never }) {
  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Contact details */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Contact Details</h3>
        <dl className="space-y-2">
          <Field label="Issuing state" value={`${v.country === "CM" ? "🇨🇲 " : ""}${v.country}`} />
          <Field label="User ID" value={v.user_id} mono />
          <Field label="Document type" value={v.doc_type ?? "—"} />
          <Field label="Status" value={v.status} />
        </dl>
      </div>

      {/* Warnings */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Warnings {v.warnings.length > 0 && <span className="text-yellow-500 ml-1">({v.warnings.length})</span>}
        </h3>
        {v.warnings.length === 0 ? (
          <p className="text-sm text-gray-600">No warnings</p>
        ) : (
          <ul className="space-y-2">
            {v.warnings.map((w) => (
              <li key={w.code} className={`text-xs px-2 py-1.5 rounded flex items-start gap-2 ${
                w.severity === "critical" ? "bg-red-950 text-red-300" :
                w.severity === "warning" ? "bg-yellow-950 text-yellow-300" :
                "bg-gray-800 text-gray-400"
              }`}>
                <span className="font-mono">{w.code}</span>
                <span className="text-gray-400">{w.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Verification metadata */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Verification</h3>
        <dl className="space-y-2">
          <Field label="Session ID" value={v.id} mono truncate />
          <Field label="Created at" value={new Date(v.created_at).toLocaleString("fr-FR")} />
          <Field label="Liveness" value={v.liveness ? "✓ Completed" : "✗ Pending"} />
          {v.reviewer && <Field label="Reviewed by" value={v.reviewer} />}
          {v.review_notes && <Field label="Notes" value={v.review_notes} />}
        </dl>
      </div>

      {/* Device info */}
      <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Device & Browser</h3>
        {v.device_info ? (
          <dl className="space-y-2">
            {Object.entries(v.device_info).map(([k, val]) => (
              <Field key={k} label={k} value={String(val)} />
            ))}
          </dl>
        ) : (
          <p className="text-sm text-gray-600">No device info</p>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, mono, truncate }: { label: string; value: string; mono?: boolean; truncate?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-xs text-gray-500 flex-shrink-0">{label}</dt>
      <dd className={`text-xs text-gray-200 text-right ${mono ? "font-mono" : ""} ${truncate ? "truncate max-w-[160px]" : ""}`}>
        {value || "—"}
      </dd>
    </div>
  );
}
